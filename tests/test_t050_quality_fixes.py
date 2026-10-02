"""T-050 代码质量优化：收敛后的公共实现 + 顺手修掉的真问题，每条都有回归用例。

修掉的问题（都在优化过程中实测确认过，不是推测）：

1. planner 的「已掌握」口径漏了「输出」：复述过的点在出题 prompt 里被列成「仍存疑」；
2. planner.count_new_tasks 出过一次复习题后恒为 0：之后再也不出复习题；
3. planner 的 JSON 围栏正则写成普通字符串 "\\\\s"，围栏分支从未生效；
4. weaknesses 读回时把「最近」日期切掉：last_seen 每读一次丢一次；
5. profile.set_level（看板手工改状态）抹掉 last_touched；
6. cli._run_chat 引用了未定义的 home：REPL 的摘要器因 NameError 被吞而从未建成；
7. 看板「提交作业」不进错题本（只有命令行 review 会记），违反 T-035 ②；
8. explain 缓存读用用户输入、写用地图点名：换个叫法提问永远命不中缓存。
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from src.distill import KnowledgePoint
from src.profile import MASTERED_LEVELS, KnowledgeProfile, write_profile_atomic


# ---------------------------------------------------------------- fileio


def test_write_text_atomic_creates_parents_and_leaves_no_tmp(tmp_path):
    from src.fileio import write_text_atomic

    target = tmp_path / "a" / "b" / "out.md"
    write_text_atomic(target, "内容")

    assert target.read_text(encoding="utf-8") == "内容"
    assert not list(target.parent.glob("*.tmp"))


def test_write_text_atomic_keeps_old_file_and_cleans_tmp_on_failure(tmp_path, monkeypatch):
    from src.fileio import write_text_atomic

    target = tmp_path / "out.md"
    target.write_text("旧内容", encoding="utf-8")

    def boom(self, other):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(OSError):
        write_text_atomic(target, "新内容")

    monkeypatch.undo()
    assert target.read_text(encoding="utf-8") == "旧内容"
    assert not list(tmp_path.glob("*.tmp"))


def test_read_text_or_none(tmp_path):
    from src.fileio import read_text_or_none

    assert read_text_or_none(tmp_path / "missing.md") is None
    assert read_text_or_none(tmp_path) is None  # 目录也当"没有"
    (tmp_path / "x.md").write_bytes("好\n".encode("utf-8") + b"\xff")
    assert read_text_or_none(tmp_path / "x.md").startswith("好")


def test_every_module_uses_the_shared_atomic_writer():
    """原子写只能有一份实现：src/ 里除了 fileio.py 不许再手写 tmp + replace。"""
    offenders = []
    for path in Path("src").glob("*.py"):
        if path.name == "fileio.py":
            continue
        text = path.read_text(encoding="utf-8")
        if '+ ".tmp"' in text or "os.replace(" in text:
            offenders.append(path.name)
    assert offenders == [], "这些模块又手写了原子写：" + ", ".join(offenders)


# ---------------------------------------------------------------- llm.extract_json


@pytest.mark.parametrize(
    "raw, expected",
    [
        ('[{"a": 1}]', [{"a": 1}]),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('好的，结果如下：{"a": 1} 希望有帮助', {"a": 1}),
        ('```\n[1, 2]\n```\n以上。', [1, 2]),
        # 围栏前的说明文字里有花括号：必须先看围栏（旧 planner 的围栏正则从未生效，这里会解析失败）
        ('说明 {不是 JSON} 如下\n```json\n{"a": 1}\n```', {"a": 1}),
    ],
)
def test_extract_json_tolerates_real_model_output(raw, expected):
    from src.llm import extract_json

    assert extract_json(raw) == expected


@pytest.mark.parametrize("raw, reason", [("", "empty"), ("   ", "empty"), ("没有任何 JSON", "missing"), ("{oops", "invalid")])
def test_extract_json_reports_reason(raw, reason):
    from src.llm import JSONExtractionError, extract_json

    with pytest.raises(JSONExtractionError) as exc:
        extract_json(raw)
    assert exc.value.reason == reason


def test_parse_task_reads_fenced_json_after_prose_with_braces():
    from src.planner import parse_task

    raw = '我先想一下 {思路} 然后给出：\n```json\n{"goal": "做名片", "skills": ["列表"], "acceptance": "能显示"}\n```'
    task = parse_task(raw)

    assert task.goal == "做名片"
    assert task.skills == ["列表"]


# ---------------------------------------------------------------- 已掌握口径


def test_mastered_levels_include_output():
    assert set(MASTERED_LEVELS) == {"学过", "做过", "输出"}


def test_output_points_are_mastered_in_task_prompt():
    from src.planner import build_next_messages

    profile = KnowledgeProfile(
        points=[
            KnowledgePoint("列表", "输出", "复述过"),
            KnowledgePoint("字典", "学过", "e"),
            KnowledgePoint("闭包", "存疑", "e"),
        ]
    )
    user = build_next_messages(profile)[1]["content"]
    mastered, uncertain = user.split("仍存疑的知识点")

    assert "列表" in mastered, "「输出」是最高态，必须算已掌握"
    assert "列表" not in uncertain
    assert "闭包" in uncertain


def test_output_point_is_not_proposed_as_next_new_point():
    from src.planner import next_unmet_point

    profile = KnowledgeProfile(points=[KnowledgePoint("列表", "输出", "e")])
    syllabus = {"chapters": [{"chapter": "第 1 章", "points": ["列表", "字典"]}]}

    assert next_unmet_point(syllabus, profile) == "字典"


def test_handoff_and_report_share_the_same_mastered_levels():
    from src import handoff, planner

    assert planner.MASTERED_LEVELS is MASTERED_LEVELS
    assert handoff.MASTERED_LEVELS is MASTERED_LEVELS


# ---------------------------------------------------------------- 复习节奏


TASK = "\n## {when}\n\n## 下一步任务\n\n**目标**：{goal}\n{flag}\n**用到的知识点**：列表\n\n**验收方式**：x\n"


def _tasks(tmp_path, items) -> Path:
    path = tmp_path / "tasks.md"
    body = "# 任务记录\n"
    for index, (goal, review) in enumerate(items):
        body += TASK.format(
            when=f"2026-09-2{index} 10:00", goal=goal, flag="\n**复习**：是\n" if review else ""
        )
    path.write_text(body, encoding="utf-8")
    return path


def test_count_new_tasks_counts_after_the_latest_review(tmp_path):
    from src.planner import count_new_tasks

    path = _tasks(tmp_path, [("A", False), ("复习：列表", True), ("B", False), ("C", False), ("D", False)])

    assert count_new_tasks(path) == 3, "以前只要出现过复习题就恒为 0"


def test_review_is_due_again_in_the_second_cycle(tmp_path):
    from src.planner import review_due

    path = _tasks(
        tmp_path,
        [("A", False), ("B", False), ("C", False), ("复习：列表", True), ("D", False), ("E", False), ("F", False)],
    )
    profile = KnowledgeProfile(points=[KnowledgePoint("字典", "学过", "e", last_touched="2020-01-01")])

    assert review_due(path, profile=profile), "第二轮出满 3 道新题后应该再出复习题"


def test_count_new_tasks_without_any_review(tmp_path):
    from src.planner import count_new_tasks

    assert count_new_tasks(_tasks(tmp_path, [("A", False), ("B", False)])) == 2


# ---------------------------------------------------------------- 时间戳不被抹掉


def test_set_level_keeps_last_touched():
    from src.profile import set_level

    profile = KnowledgeProfile(points=[KnowledgePoint("列表", "学过", "e", last_touched="2026-09-01")])
    updated = set_level(profile, "列表", "做过", note="看板改的")

    assert updated.points[0].level == "做过"
    assert updated.points[0].last_touched == "2026-09-01"


def test_weaknesses_keep_both_dates_across_reload(tmp_path):
    from src.weaknesses import Weakness, load_weaknesses, merge_weaknesses, save_weaknesses

    save_weaknesses(tmp_path, [Weakness("缩进混乱", "2026-09-20", "2026-09-29"), Weakness("a — b", "", "2026-09-28")])
    loaded = load_weaknesses(tmp_path)

    assert loaded[0] == Weakness("缩进混乱", "2026-09-20", "2026-09-29")
    assert loaded[1] == Weakness("a — b", "", "2026-09-28"), "正文里带破折号也不能被当成时间戳段"

    # 合并别的条目后再读一遍：老条目的「最近」仍在
    merge_weaknesses(tmp_path, ["忘记空格"], when="2026-09-30")
    assert load_weaknesses(tmp_path)[0].last_seen == "2026-09-29"


def test_weaknesses_window_uses_last_seen(tmp_path):
    """周报的「窗口内新增/复现」靠 last_seen：首次很早、最近在窗口内的要算进去。"""
    from src.report import collect_stats
    from src.weaknesses import Weakness, save_weaknesses

    directory = tmp_path / "profile"
    directory.mkdir()
    write_profile_atomic(directory / "knowledge.md", KnowledgeProfile())
    save_weaknesses(directory, [Weakness("缩进混乱", "2026-08-01", "2026-09-29")])

    stats = collect_stats(directory, days=7, today=datetime.date(2026, 9, 30), repo_root=directory)
    assert [item.text for item in stats["fresh_weaknesses"]] == ["缩进混乱"]


# ---------------------------------------------------------------- CLI


def test_cli_parse_args_values_flags_and_repeats():
    from src.cli import _parse_args

    options, positional = _parse_args(
        ["x", "--topic", "A", "--json", "--profile", "p.md", "--topic", "B", "y"],
        values=("--profile",),
        flags=("--json",),
        repeat=("--topic",),
    )
    assert positional == ["x", "y"]
    assert options == {"--profile": "p.md", "--topic": ["A", "B"], "--json": True}


def test_cli_parse_args_missing_value_names_the_option():
    from src.cli import _UsageError, _parse_args

    with pytest.raises(_UsageError) as exc:
        _parse_args(["--profile"], values=("--profile",))
    assert "--profile 后面要跟画像文件路径" in str(exc.value)


def test_usage_has_no_duplicate_lines():
    from src.cli import USAGE

    lines = [line for line in USAGE.splitlines() if line.strip()]
    assert len(lines) == len(set(lines))


def _handoff_dir(tmp_path) -> Path:
    from src.handoff import write_handoff
    from src.planner import read_task_records

    directory = tmp_path / "profile"
    directory.mkdir()
    write_profile_atomic(directory / "knowledge.md", KnowledgeProfile(points=[KnowledgePoint("列表", "学过", "e")]))
    (directory / "tasks.md").write_text(
        "# 任务记录\n\n## 2026-09-27 10:00\n\n**目标**：做名片页\n\n**验收方式**：能显示\n", encoding="utf-8"
    )
    write_handoff(directory, record=read_task_records(directory / "tasks.md")[0], code="<h1>x</h1>")
    return directory


def test_repl_chat_builds_summarizer_with_home(tmp_path, monkeypatch):
    """以前 _run_chat 没有 home 参数：REPL 分支里的 home 是 NameError，摘要器永远建不成。"""
    from src import chat, cli, repl

    directory = _handoff_dir(tmp_path)
    seen: dict = {}

    class Completer:
        def complete(self, messages):
            return "摘要"

    def fake_completer(**kwargs):
        seen.update(kwargs)
        return Completer()

    monkeypatch.setattr(cli, "make_llm_completer", fake_completer)
    monkeypatch.setattr(chat, "find_dsh", lambda: "dsh")
    monkeypatch.setattr(repl, "run_repl", lambda **kwargs: 0)

    code = cli.main(["chat", "2026-09-27 10:00"], profile_path=directory / "knowledge.md", home=tmp_path / "home")

    assert code == 0
    assert seen.get("home") == tmp_path / "home", "REPL 的摘要器要用调用方给的 home 建出来"


def test_board_review_feeds_weaknesses(tmp_path, monkeypatch):
    """T-035 ②：看板「提交作业」与 CLI review 一样，把问题点并进错题本。"""
    from src import cli
    from src.weaknesses import weaknesses_text

    directory = _handoff_dir(tmp_path)

    class Reviewer:
        def complete(self, messages):
            return "【评价】基本达标。【建议】补上头像。\n【问题点】缩进混乱、忘记闭合标签"

    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: Reviewer())
    board = cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )

    result = board.run_action("review", {"task": "2026-09-27 10:00", "code": "<h1>张三</h1>"})

    assert result.ok, result.output
    assert weaknesses_text(directory) == ["缩进混乱", "忘记闭合标签"]
    assert "提交时间" in (directory / "tasks.md").read_text(encoding="utf-8")


def test_board_review_reports_llm_config_error_in_chinese(tmp_path, monkeypatch):
    from src import cli
    from src.llm import LLMError

    directory = _handoff_dir(tmp_path)

    def broken(**kwargs):
        raise LLMError("LLM 凭证缺失：三选一")

    monkeypatch.setattr(cli, "make_llm_completer", broken)
    board = cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )

    result = board.run_action("review", {"task": "2026-09-27 10:00", "code": "x"})

    assert not result.ok
    assert "凭证缺失" in result.output, "以前这里会变成只有异常类名的 500"


# ---------------------------------------------------------------- explain 缓存键


def test_explain_cache_hits_when_asked_by_another_name(tmp_path):
    from src.explain import explain_point
    from src.syllabus import BookMap, Chapter

    books = [BookMap(book="Demo", chapters=[Chapter("第 1 章 A", ["列表（list）"])])]
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    (books_dir / "蒸馏-Demo.md").write_text(
        "---\nbook: Demo\n---\n\n### 第 1 章 A（L1–L10）\n\n正文内容\n", encoding="utf-8"
    )

    class Counting:
        calls = 0

        def complete(self, messages):
            Counting.calls += 1
            return "讲解正文"

    kwargs = dict(books_dir=books_dir, src_dir=tmp_path / "nope", cache_dir=tmp_path / "cache")
    explain_point("列表（list）", books, completer=Counting(), **kwargs)
    second = explain_point("列表", books, completer=Counting(), **kwargs)

    assert Counting.calls == 1, "同一个地图点换个叫法提问也该命中缓存"
    assert second.from_cache
