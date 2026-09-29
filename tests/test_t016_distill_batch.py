"""T-016 失败测试：distill 批量（--all）与看板全量提炼。

现状根因（可确认）：
- CLI 的 distill 一次只接受一个文件（len(positional) != 1 直接退 2）；
- 看板 op_distill 只挑 notes/ 里 mtime 最新的一篇。

要求：
1. distill --all：提炼 notes/ 下**全部非空**笔记；
2. 幂等：重复跑一遍画像不新增重复条目；
3. 单篇失败不阻塞其余，但要**明确报出失败篇目与原因**；
4. 看板「提炼知识点」按钮改为全量，并逐篇汇报成败。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.dashboard import TaskBoard
from src.distill import DistillError, KnowledgePoint, distill_notes
from src.profile import KnowledgeProfile, write_profile_atomic


class ScriptedCompleter:
    """按笔记内容返回预置知识点；可指定某些笔记抛错。"""

    def __init__(self, per_note: dict, failures: dict | None = None):
        self.per_note = per_note
        self.failures = failures or {}
        self.calls: list[str] = []

    def complete(self, messages):
        prompt = "\n".join(m.get("content", "") for m in messages)
        for marker, error in self.failures.items():
            if marker in prompt:
                self.calls.append(marker)
                raise error
        for marker, points in self.per_note.items():
            if marker in prompt:
                self.calls.append(marker)
                return json.dumps(points, ensure_ascii=False)
        raise AssertionError("未预置的笔记内容")


def make_notes(tmp_path):
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "a.md").write_text("# 笔记A\n\n## 列表\n列表用方括号。\n", encoding="utf-8")
    (notes / "b.md").write_text("# 笔记B\n\n## 字典\n字典是键值对。\n", encoding="utf-8")
    (notes / "empty.md").write_text("   \n\n", encoding="utf-8")
    return notes


def completer_for_two():
    return ScriptedCompleter(
        {
            "笔记A": [{"name": "列表", "level": "学过", "evidence": "列表用方括号"}],
            "笔记B": [{"name": "字典", "level": "学过", "evidence": "字典是键值对"}],
        }
    )


# --- 1. discover_notes：全量发现 -------------------------------------------------


def test_discover_notes_skips_empty_files(tmp_path):
    from src.distill import discover_notes

    notes = make_notes(tmp_path)

    found = [p.name for p in discover_notes(notes)]

    assert found == ["a.md", "b.md"]


def test_discover_notes_missing_dir_returns_empty(tmp_path):
    from src.distill import discover_notes

    assert discover_notes(tmp_path / "nope") == []


def test_discover_notes_is_sorted_and_deduped(tmp_path):
    from src.distill import discover_notes

    notes = make_notes(tmp_path)
    (notes / "c.md").write_text("# C\n\n内容\n", encoding="utf-8")

    names = [p.name for p in discover_notes(notes)]

    assert names == sorted(names)


# --- 2. distill_notes：逐篇提炼并汇总 --------------------------------------------


def test_distill_notes_reports_each_file(tmp_path):
    notes = make_notes(tmp_path)

    summary = distill_notes(notes, completer=completer_for_two())

    assert len(summary.succeeded) == 2
    assert summary.failed == []
    assert {path.name for path, _points in summary.succeeded} == {"a.md", "b.md"}
    assert summary.total_points == 2


def test_total_points_counts_all_returned_points(tmp_path):
    notes = make_notes(tmp_path)
    completer = ScriptedCompleter({
        "笔记A": [
            {"name": "列表", "level": "学过", "evidence": "e1"},
            {"name": "切片", "level": "学过", "evidence": "e2"},
        ],
        "笔记B": [{"name": "字典", "level": "存疑", "evidence": "e3"}],
    })

    summary = distill_notes(notes, completer=completer)

    assert summary.total_points == 3


def test_single_failure_does_not_block_others(tmp_path):
    notes = make_notes(tmp_path)
    completer = ScriptedCompleter(
        {"笔记B": [{"name": "字典", "level": "学过", "evidence": "e"}]},
        failures={"笔记A": DistillError("LLM 输出不可解析")},
    )

    summary = distill_notes(notes, completer=completer)

    assert [path.name for path, _points in summary.succeeded] == ["b.md"]
    assert len(summary.failed) == 1
    failed_name, reason = summary.failed[0]
    assert failed_name == "a.md"
    assert "不可解析" in reason


def test_all_failures_are_reported(tmp_path):
    notes = make_notes(tmp_path)
    completer = ScriptedCompleter({}, failures={"笔记A": DistillError("x"), "笔记B": DistillError("y")})

    summary = distill_notes(notes, completer=completer)

    assert summary.succeeded == []
    assert len(summary.failed) == 2


def test_empty_directory_reports_nothing(tmp_path):
    notes = tmp_path / "notes"
    notes.mkdir()

    summary = distill_notes(notes, completer=completer_for_two())

    assert summary.succeeded == [] and summary.failed == []
    assert summary.note_count == 0


def test_summary_is_human_readable(tmp_path):
    notes = make_notes(tmp_path)

    text = distill_notes(notes, completer=completer_for_two()).render()

    assert "a.md" in text and "b.md" in text
    assert "2" in text


def test_summary_lists_failures_with_reason(tmp_path):
    notes = make_notes(tmp_path)
    completer = ScriptedCompleter(
        {"笔记B": [{"name": "字典", "level": "学过", "evidence": "e"}]},
        failures={"笔记A": DistillError("额度不足")},
    )

    text = distill_notes(notes, completer=completer).render()

    assert "a.md" in text
    assert "额度不足" in text


# --- 3. 幂等 --------------------------------------------------------------------


def test_merging_batch_twice_is_idempotent(tmp_path):
    """重复跑一遍：画像不新增重复条目（T-004 的按名称合并已保证，这里锁住端到端）。"""
    from src.profile import merge_points

    notes = make_notes(tmp_path)
    completer = completer_for_two()
    profile = KnowledgeProfile()

    first = distill_notes(notes, completer=completer)
    for _path, points in first.succeeded:
        profile = merge_points(profile, points)
    after_first = len(profile.points)

    second = distill_notes(notes, completer=completer_for_two())
    for _path, points in second.succeeded:
        profile = merge_points(profile, points)

    assert after_first == 2
    assert len(profile.points) == 2  # 没有重复条目
    assert [p.name for p in profile.points] == ["列表", "字典"]


# --- 4. CLI：distill --all ------------------------------------------------------


def test_cli_distill_all_updates_profile(tmp_path, monkeypatch, capsys):
    from src import cli

    notes = make_notes(tmp_path)
    target = tmp_path / "profile" / "knowledge.md"
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: completer_for_two())

    code = cli.main(["distill", "--all"], env_path=tmp_path / ".env", notes_dir=notes, profile_path=target)
    out = capsys.readouterr()

    assert code == 0
    profile = KnowledgeProfile.load(target)
    assert {p.name for p in profile.points} == {"列表", "字典"}
    assert "a.md" in out.err


def test_cli_distill_all_twice_is_idempotent(tmp_path, monkeypatch, capsys):
    from src import cli

    notes = make_notes(tmp_path)
    target = tmp_path / "profile" / "knowledge.md"
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: completer_for_two())

    cli.main(["distill", "--all"], env_path=tmp_path / ".env", notes_dir=notes, profile_path=target)
    cli.main(["distill", "--all"], env_path=tmp_path / ".env", notes_dir=notes, profile_path=target)
    capsys.readouterr()

    profile = KnowledgeProfile.load(target)
    assert len(profile.points) == 2
    assert len({p.name for p in profile.points}) == 2


def test_cli_distill_all_partial_failure_exits_nonzero(tmp_path, monkeypatch, capsys):
    from src import cli

    notes = make_notes(tmp_path)
    target = tmp_path / "profile" / "knowledge.md"
    completer = ScriptedCompleter(
        {"笔记B": [{"name": "字典", "level": "学过", "evidence": "e"}]},
        failures={"笔记A": DistillError("额度不足")},
    )
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: completer)

    code = cli.main(["distill", "--all"], env_path=tmp_path / ".env", notes_dir=notes, profile_path=target)
    out = capsys.readouterr()

    assert code == 1  # 有失败篇目 → 非零，但成功的仍写入
    assert "a.md" in out.err and "额度不足" in out.err
    assert {p.name for p in KnowledgeProfile.load(target).points} == {"字典"}


def test_cli_distill_all_no_notes_exits_zero_with_hint(tmp_path, monkeypatch, capsys):
    from src import cli

    notes = tmp_path / "notes"
    notes.mkdir()
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: completer_for_two())

    code = cli.main(["distill", "--all"], env_path=tmp_path / ".env", notes_dir=notes, profile_path=tmp_path / "p.md")
    out = capsys.readouterr()

    assert code == 0
    assert "没有" in out.err or "空" in out.err


def test_cli_distill_all_conflicts_with_file_argument(tmp_path, monkeypatch, capsys):
    from src import cli

    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: completer_for_two())
    code = cli.main(["distill", "--all", "notes/a.md"], env_path=tmp_path / ".env", notes_dir=tmp_path / "notes")
    out = capsys.readouterr()

    assert code == 2
    assert "用法" in out.err


# --- 5. 看板：全量提炼并逐篇汇报 -------------------------------------------------


def test_board_distill_operation_is_batch(tmp_path, monkeypatch):
    """看板按钮必须走全量，而不是只挑最新一篇。"""
    from src import cli

    notes = make_notes(tmp_path)
    target = tmp_path / "profile" / "knowledge.md"
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: completer_for_two())

    board = cli._build_board(tmp_path / ".env", notes, target, None, None)
    result = board.run_action("distill")

    assert result.ok
    profile = KnowledgeProfile.load(target)
    assert {p.name for p in profile.points} == {"列表", "字典"}
    assert "a.md" in result.output and "b.md" in result.output


def test_board_distill_reports_failures(tmp_path, monkeypatch):
    from src import cli

    notes = make_notes(tmp_path)
    target = tmp_path / "profile" / "knowledge.md"
    completer = ScriptedCompleter(
        {"笔记B": [{"name": "字典", "level": "学过", "evidence": "e"}]},
        failures={"笔记A": DistillError("额度不足")},
    )
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: completer)

    board = cli._build_board(tmp_path / ".env", notes, target, None, None)
    result = board.run_action("distill")

    assert "a.md" in result.output
    assert "额度不足" in result.output

# --- T-017 I-1：逐篇进度提示 ----------------------------------------------------


def test_progress_callback_reports_each_note(tmp_path):
    notes = make_notes(tmp_path)
    seen = []

    distill_notes(
        notes,
        completer=completer_for_two(),
        on_progress=lambda i, n, name, status: seen.append((i, n, name)),
    )

    # 每篇会回调两次：先「提炼中」（让人看到正在处理哪篇），再报终态
    assert len(seen) == 4
    assert seen[0] == (1, 2, "a.md")
    assert seen[2] == (2, 2, "b.md")
    assert [s[0] for s in seen] == [1, 1, 2, 2]


def test_progress_callback_reports_skipped_notes_too(tmp_path):
    """跳过的笔记也要报进度，否则用户以为卡住了。"""
    notes = make_notes(tmp_path)
    seen = []
    state = {"a.md": {"hash": None, "size": None}}  # 见 I-2 的状态结构

    from src.distill import file_fingerprint
    state = {"a.md": {"hash": file_fingerprint(notes / "a.md"), "size": (notes / "a.md").stat().st_size}}

    distill_notes(
        notes,
        completer=completer_for_two(),
        state=state,
        on_progress=lambda i, n, name, status: seen.append((i, n, name)),
    )

    # a.md 被跳过（终态一次），b.md 正常提炼（提炼中 + 终态）
    assert [s[2] for s in seen] == ["a.md", "b.md", "b.md"]


def test_cli_distill_all_prints_progress(tmp_path, monkeypatch, capsys):
    from src import cli

    notes = make_notes(tmp_path)
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: completer_for_two())

    cli.main(
        ["distill", "--all"],
        env_path=tmp_path / ".env",
        notes_dir=notes,
        profile_path=tmp_path / "profile" / "knowledge.md",
    )
    out = capsys.readouterr()

    assert "[1/2]" in out.err
    assert "[2/2]" in out.err
    assert "a.md" in out.err and "b.md" in out.err


# --- T-017 I-2：跳过未变更的笔记（增量） ----------------------------------------


def test_file_fingerprint_changes_with_content(tmp_path):
    from src.distill import file_fingerprint

    path = tmp_path / "n.md"
    path.write_text("内容 A", encoding="utf-8")
    first = file_fingerprint(path)
    path.write_text("内容 B", encoding="utf-8")

    assert file_fingerprint(path) != first


def test_unchanged_notes_are_skipped(tmp_path):
    """已提炼且内容未变 → 不再调用 LLM。"""
    notes = make_notes(tmp_path)
    state = {}
    first = distill_notes(notes, completer=completer_for_two(), state=state)
    assert len(first.succeeded) == 2

    second_completer = ScriptedCompleter({})  # 若被调用会抛 AssertionError
    second = distill_notes(notes, completer=second_completer, state=state)

    assert second.succeeded == []
    assert second.skipped == 2
    assert second_completer.calls == []


def test_changed_note_is_reprocessed(tmp_path):
    notes = make_notes(tmp_path)
    state = {}
    distill_notes(notes, completer=completer_for_two(), state=state)

    (notes / "a.md").write_text("# 笔记A\n\n## 列表\n列表用方括号，另外加了切片。\n", encoding="utf-8")
    completer = ScriptedCompleter({"笔记A": [{"name": "列表", "level": "学过", "evidence": "e"}]})
    result = distill_notes(notes, completer=completer, state=state)

    assert [p.name for p, _ in result.succeeded] == ["a.md"]
    assert result.skipped == 1  # b.md 未变，跳过


def test_force_ignores_state(tmp_path):
    notes = make_notes(tmp_path)
    state = {}
    distill_notes(notes, completer=completer_for_two(), state=state)

    forced = distill_notes(notes, completer=completer_for_two(), state=state, force=True)

    assert len(forced.succeeded) == 2
    assert forced.skipped == 0


def test_state_is_updated_after_success_only(tmp_path):
    notes = make_notes(tmp_path)
    state = {}
    completer = ScriptedCompleter(
        {"笔记B": [{"name": "字典", "level": "学过", "evidence": "e"}]},
        failures={"笔记A": DistillError("失败")},
    )

    distill_notes(notes, completer=completer, state=state)

    assert "b.md" in state
    assert "a.md" not in state  # 失败的笔记不进状态，下次会重试


def test_summary_reports_skipped_count(tmp_path):
    notes = make_notes(tmp_path)
    state = {}
    distill_notes(notes, completer=completer_for_two(), state=state)
    text = distill_notes(notes, completer=ScriptedCompleter({}), state=state).render()

    assert "跳过" in text


def test_cli_distill_all_skips_unchanged_second_time(tmp_path, monkeypatch, capsys):
    from src import cli

    notes = make_notes(tmp_path)
    state_file = tmp_path / "profile" / ".distill-state.json"
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: completer_for_two())

    cli.main(["distill", "--all"], env_path=tmp_path / ".env", notes_dir=notes,
             profile_path=tmp_path / "profile" / "knowledge.md")
    first_err = capsys.readouterr().err
    assert state_file.is_file()

    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: ScriptedCompleter({}))
    code = cli.main(["distill", "--all"], env_path=tmp_path / ".env", notes_dir=notes,
                    profile_path=tmp_path / "profile" / "knowledge.md")
    second_err = capsys.readouterr().err

    assert code == 0
    assert "跳过" in second_err
    assert "2 篇" in second_err or "跳过 2" in second_err


def test_cli_distill_all_force_reprocesses(tmp_path, monkeypatch, capsys):
    from src import cli

    notes = make_notes(tmp_path)
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: completer_for_two())

    cli.main(["distill", "--all"], env_path=tmp_path / ".env", notes_dir=notes,
             profile_path=tmp_path / "profile" / "knowledge.md")
    capsys.readouterr()

    cli.main(["distill", "--all", "--force"], env_path=tmp_path / ".env", notes_dir=notes,
             profile_path=tmp_path / "profile" / "knowledge.md")
    err = capsys.readouterr().err

    assert "[1/2]" in err and "[2/2]" in err
    assert "跳过（内容未变）" not in err   # --force 时不该有任何一篇被判为跳过
    assert "跳过 0 篇" in err              # 汇总行如实说明跳过了 0 篇


# --- T-017 I-3：缺前置产物退出码统一 -------------------------------------------


def test_missing_profile_exit_code_is_consistent(tmp_path, monkeypatch, capsys):
    from src import cli

    missing = tmp_path / "profile" / "knowledge.md"
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: completer_for_two())

    next_code = cli.main(["next"], env_path=tmp_path / ".env", profile_path=missing)
    done_code = cli.main(["done", "列表", "out.py"], env_path=tmp_path / ".env", profile_path=missing)
    capsys.readouterr()

    assert next_code == done_code == 1


def test_missing_profile_hint_mentions_next_step(tmp_path, monkeypatch, capsys):
    from src import cli

    missing = tmp_path / "profile" / "knowledge.md"
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: completer_for_two())

    cli.main(["done", "列表", "out.py"], env_path=tmp_path / ".env", profile_path=missing)
    err = capsys.readouterr().err

    assert "画像" in err
    assert "sync" in err and "distill" in err