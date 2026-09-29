"""T-025 失败测试：看板「同步」按钮联动提炼。

客户两次踩坑：点了同步，画像不变（因为 sync 只落盘笔记，不提炼）。
要求：
- 同步成功后**自动执行增量提炼**（distill 的 sha256 跳过保证只处理变更篇）；
- 结果分两段展示「同步了哪些 + 提炼了哪些」；
- 按钮文案改为「同步并提炼」；
- **命令行 sync 保持单职责不变**，只改看板联动。
"""

from __future__ import annotations

import pathlib

import pytest

from src.dashboard import ACTION_LABELS, TaskBoard
from src.distill import KnowledgePoint
from src.profile import KnowledgeProfile, write_profile_atomic


def make_notes(tmp_path, names=("a.md",)):
    notes = tmp_path / "notes"
    notes.mkdir(exist_ok=True)
    for name in names:
        (notes / name).write_text("# 笔记\n\n## 列表\n列表用方括号。\n", encoding="utf-8")
    return notes


def make_board(tmp_path, monkeypatch, *, sync_code=0, distill_code=0, sync_out="同步完成", distill_out="提炼完成"):
    from src import cli

    calls: list[str] = []

    def fake_sync(rest, env_path, notes_dir, **kw):
        calls.append("sync")
        print(sync_out)
        return sync_code

    def fake_distill(rest, env_path, **kw):
        calls.append("distill")
        print(distill_out)
        return distill_code

    monkeypatch.setattr(cli, "_run_sync", fake_sync)
    monkeypatch.setattr(cli, "_run_distill", fake_distill)

    notes = make_notes(tmp_path)
    profile = tmp_path / "profile" / "knowledge.md"
    write_profile_atomic(profile, KnowledgeProfile(points=[KnowledgePoint("列表", "学过", "e")]))
    board = cli._build_board(tmp_path / ".env", notes, profile, None, None)
    return board, calls


def test_sync_button_label_says_sync_and_distill(tmp_path, monkeypatch):
    board, _ = make_board(tmp_path, monkeypatch)

    page = board.pages()[""]

    assert ACTION_LABELS["sync"] == "同步并提炼"
    assert "同步并提炼" in page
    assert "同步飞书笔记" not in page


def test_board_sync_also_runs_distill(tmp_path, monkeypatch):
    board, calls = make_board(tmp_path, monkeypatch)

    result = board.run_action("sync")

    assert result.ok
    assert calls == ["sync", "distill"], "同步后必须接着提炼"


def test_board_sync_output_has_two_sections(tmp_path, monkeypatch):
    board, _ = make_board(tmp_path, monkeypatch, sync_out="同步了 a.md", distill_out="提炼了 a.md")

    result = board.run_action("sync")

    assert "同步了 a.md" in result.output
    assert "提炼了 a.md" in result.output
    assert "同步" in result.output and "提炼" in result.output


def test_board_sync_reports_when_sync_fails(tmp_path, monkeypatch):
    board, calls = make_board(tmp_path, monkeypatch, sync_code=1, sync_out="飞书接口失败")

    result = board.run_action("sync")

    assert not result.ok
    assert calls == ["sync"], "同步失败就不该再提炼"
    assert "飞书接口失败" in result.output


def test_board_sync_still_distills_when_no_new_content(tmp_path, monkeypatch):
    """没有新内容时也要跑提炼（增量的），并把「无新内容」如实展示出来。"""
    board, calls = make_board(
        tmp_path, monkeypatch, distill_out="批量提炼：共 1 篇，成功 0 篇，跳过 1 篇（内容未变），失败 0 篇"
    )

    result = board.run_action("sync")

    assert result.ok
    assert calls == ["sync", "distill"]
    assert "跳过 1 篇" in result.output


def test_board_sync_reports_distill_failures(tmp_path, monkeypatch):
    """提炼有失败篇目时，按钮结果要报出来（不能因为退出码非 0 就吞掉）。"""
    board, _ = make_board(
        tmp_path, monkeypatch, distill_code=1, distill_out="[失败] b.md：LLM 输出无法解析"
    )

    result = board.run_action("sync")

    assert "[失败] b.md" in result.output


def test_cli_sync_stays_single_purpose(tmp_path, monkeypatch, capsys):
    """命令行 sync 保持单职责：只同步，不提炼。"""
    from src import cli

    called: list[str] = []
    monkeypatch.setattr(cli, "_run_sync", lambda *a, **kw: called.append("sync") or 0)
    monkeypatch.setattr(cli, "_run_distill", lambda *a, **kw: called.append("distill") or 0)

    notes = make_notes(tmp_path)
    code = cli.main(["sync", "tok"], env_path=tmp_path / ".env", notes_dir=notes)
    capsys.readouterr()

    assert code == 0
    assert called == ["sync"]
