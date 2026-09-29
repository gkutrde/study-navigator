"""T-023 失败测试包：使用链路逻辑修复（L-01 ~ L-05）。

L-01 新知识点回写断链：done 一个画像里没有的点会直接报错 → 核心闭环断裂。
L-02 重复出题：next 不读 tasks.md，题库确定性命中导致画像不变时永远同一题。
L-03 explain 只认地图名：接受不了画像里的知识点名。
L-04 planner.py 死代码：_mapped_unmastered_in_book 内 return 后不可达块。
L-05 看板同步按钮只拉最新一篇：.env 增 FEISHU_ROOT_DOC 后可拉全树。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.distill import KnowledgePoint
from src.profile import KnowledgeProfile, ProfileError, mark_done, write_profile_atomic


def profile_with(*pairs):
    return KnowledgeProfile(points=[KnowledgePoint(n, lv, "e") for n, lv in pairs])


# ============ L-01：done 必须能新增画像里没有的知识点 ============


def test_mark_done_creates_missing_point():
    """done 一个画像里没有的点：应当**新增条目**（状态「做过」），而不是报错。

    否则闭环断裂：出题/讲解里遇到的新点，做完没法回写。
    """
    profile = profile_with(("列表", "学过"))

    updated = mark_done(profile, "字典", "out.py")

    assert len(updated.points) == 2
    new_point = next(p for p in updated.points if p.name == "字典")
    assert new_point.level == "做过"
    assert "out.py" in new_point.evidence


def test_mark_done_creates_missing_point_with_recite():
    profile = profile_with(("列表", "学过"))

    updated = mark_done(profile, "字典", "out.py", recite="字典就是键值对表")

    new_point = next(p for p in updated.points if p.name == "字典")
    assert new_point.level == "输出"
    assert "字典就是键值对表" in new_point.evidence


def test_mark_done_new_point_keeps_existing_untouched():
    profile = profile_with(("列表", "学过"))

    updated = mark_done(profile, "字典", "out.py")

    assert updated.points[0].name == "列表"
    assert updated.points[0].level == "学过"
    assert updated.points[0].evidence == "e"


def test_mark_done_new_point_goes_to_uncategorized():
    profile = profile_with(("列表", "学过", ))

    updated = mark_done(profile, "字典", "out.py")

    new_point = next(p for p in updated.points if p.name == "字典")
    assert not new_point.topic  # 未分类


def test_mark_done_still_rejects_empty_name():
    with pytest.raises(ProfileError):
        mark_done(profile_with(("列表", "学过")), "   ", "out.py")


def test_cli_done_adds_new_point(tmp_path, capsys):
    from src import cli

    target = tmp_path / "profile" / "knowledge.md"
    write_profile_atomic(target, profile_with(("列表", "学过")))

    code = cli.main(["done", "全新的知识点", "out.py"], profile_path=target)
    out = capsys.readouterr()

    assert code == 0, out.err
    reloaded = KnowledgeProfile.load(target)
    assert any(p.name == "全新的知识点" for p in reloaded.points)
    assert next(p for p in reloaded.points if p.name == "全新的知识点").level == "做过"


def test_board_status_can_create_point(tmp_path):
    """看板手工加一个新知识点也应可用（走同一条新增逻辑）。"""
    from src.dashboard import TaskBoard

    directory = tmp_path / "profile"
    write_profile_atomic(directory / "knowledge.md", profile_with(("列表", "学过")))
    board = TaskBoard(directory)

    result = board.run_action("status", {"name": "全新点", "level": "学过", "note": "手工补"})

    assert result.ok
    reloaded = KnowledgeProfile.load(directory / "knowledge.md")
    assert any(p.name == "全新点" for p in reloaded.points)


# ============ L-02：连续两次 next 不能出同一题 ============


def test_bank_skips_ident_already_given(tmp_path):
    """题库命中的条目若已出过（tasks.md 里有 ident），就换下一条。"""
    from src.assignments import Assignment, pick_assignment

    bank = [
        Assignment(ident="A-01", title="名片页", course="CS50", tags=["列表"], goal="g1",
                   steps=[], acceptance="a", level="入门", new_skill=None),
        Assignment(ident="A-02", title="表格页", course="CS50", tags=["列表"], goal="g2",
                   steps=[], acceptance="a", level="入门", new_skill=None),
    ]
    profile = profile_with(("列表", "做过"))

    first = pick_assignment(bank, profile, already_given=set())
    second = pick_assignment(bank, profile, already_given={"A-01"})

    assert first.ident == "A-01"
    assert second.ident == "A-02"


def test_pick_assignment_returns_none_when_all_given():
    from src.assignments import Assignment, pick_assignment

    bank = [Assignment(ident="A-01", title="t", course="c", tags=["列表"], goal="g",
                       steps=[], acceptance="a", level="入门", new_skill=None)]

    assert pick_assignment(bank, profile_with(("列表", "做过")), already_given={"A-01"}) is None


def test_read_given_idents_from_tasks_md(tmp_path):
    from src.planner import read_given_idents

    tasks = tmp_path / "tasks.md"
    tasks.write_text(
        "# 任务记录\n\n## 2026-09-27 10:00\n\n**题目出处**：哈佛 CS50（A-01 个人名片页） ｜ 来自题库 [[assignments]]\n",
        encoding="utf-8",
    )

    assert read_given_idents(tasks) == {"A-01"}


def test_read_given_idents_missing_file(tmp_path):
    from src.planner import read_given_idents

    assert read_given_idents(tmp_path / "nope.md") == set()


def test_cli_next_second_time_picks_different_bank_entry(tmp_path, monkeypatch, capsys):
    from src import cli

    profile_path = tmp_path / "profile" / "knowledge.md"
    write_profile_atomic(profile_path, profile_with(("列表", "做过"), ("字典", "学过"), ("循环", "学过")))
    (tmp_path / "profile" / "assignments.md").write_text(
        "## A-01 名片页\n\n" + chr(96) * 3 + "yaml\ncourse: CS50\ntags: [列表, 字典]\nlevel: 入门\nnew_skill: \"\"\n"
        + chr(96) * 3 + "\n\n**目标**：做名片页\n\n**实现要点**：\n1. a\n\n**验收方式**：能看到\n\n"
        "## A-02 表格页\n\n" + chr(96) * 3 + "yaml\ncourse: CS50\ntags: [列表, 循环]\nlevel: 入门\nnew_skill: \"\"\n"
        + chr(96) * 3 + "\n\n**目标**：做表格页\n\n**实现要点**：\n1. a\n\n**验收方式**：能看到\n",
        encoding="utf-8",
    )
    tasks = tmp_path / "profile" / "tasks.md"

    cli.main(["next"], env_path=tmp_path / ".env", profile_path=profile_path, tasks_path=tasks)
    first = capsys.readouterr().out
    cli.main(["next"], env_path=tmp_path / ".env", profile_path=profile_path, tasks_path=tasks)
    second = capsys.readouterr().out

    assert "做名片页" in first
    assert "做表格页" in second, "第二次不该再出同一题"
    assert "做名片页" not in second


def test_llm_prompt_includes_recent_tasks(tmp_path):
    """LLM 路径也要带近期任务，避免重复出题。"""
    from src.planner import build_next_messages

    profile = profile_with(("列表", "做过"), ("字典", "学过"), ("循环", "学过"))

    messages = build_next_messages(profile, recent_goals=["做一个名片页"])
    prompt = messages[-1]["content"]

    assert "做一个名片页" in prompt
    assert "不要重复" in prompt or "避免重复" in prompt or "已经出过" in prompt


def test_build_next_messages_without_recent_has_no_repeat_section():
    from src.planner import build_next_messages

    prompt = build_next_messages(profile_with(("列表", "做过"))) [-1]["content"]

    assert "已经出过" not in prompt


# ============ L-03：explain 接受画像名 ============


def test_explain_accepts_profile_name_via_alignment(tmp_path):
    """实况：用户会拿画像里的名字去 explain，即使地图里叫别的名字。"""
    from src.alignment import Alignment, save_alignment
    from src.explain import find_explain_source
    from src.profile import KnowledgeProfile as P

    src_dir = tmp_path / "_src"
    src_dir.mkdir()
    (src_dir / "README.md").write_text(
        "| 前缀 | 书 |\n|---|---|\n| demo-book | Demo Book |\n", encoding="utf-8"
    )
    body = ["第 %d 行" % i for i in range(1, 201)]
    body[149] = "h1 到 h6 六级标题：主标题用 h1"
    (src_dir / "demo-book.txt").write_text("\n".join(body), encoding="utf-8")
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    (books_dir / "蒸馏-Demo.md").write_text(
        "---\nbook: Demo Book\nsource: demo-book\n---\n\n"
        "### 第 1 章 标题（L150–L160）\n\n正文\n",
        encoding="utf-8",
    )

    from src.syllabus import BookMap, Chapter

    books = [BookMap(book="Demo Book", chapters=[Chapter("第 1 章 标题", ["地图里的名字"])])]
    alignment_path = tmp_path / "alignment.json"
    save_alignment(alignment_path, {
        "地图里的名字": Alignment("地图里的名字", "画像里的名字", "high"),
    })
    profile = P(points=[KnowledgePoint("画像里的名字", "学过", "e")])

    # 用画像名提问：应经对齐表映射到地图点「地图里的名字」
    found = find_explain_source(
        "画像里的名字", books, profile=profile, alignment_path=alignment_path,
        books_dir=books_dir, src_dir=src_dir,
    )

    assert found.book == "Demo Book"


# ============ L-04：死代码 ============


def test_planner_has_no_unreachable_code_after_return():
    """_mapped_unmastered_in_book 里 return 之后不应还有代码。"""
    import ast

    source = Path("src/planner.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    problems = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        body = node.body
        for position, statement in enumerate(body[:-1]):
            if isinstance(statement, ast.Return):
                problems.append(f"{node.name} 第 {statement.lineno} 行 return 之后还有代码")

    assert problems == []


# ============ L-05：看板同步按钮支持全树 ============


def test_env_example_documents_feishu_root_doc():
    text = Path(".env.example").read_text(encoding="utf-8")

    assert "FEISHU_ROOT_DOC" in text


def test_board_sync_uses_root_doc_when_configured(tmp_path, monkeypatch):
    from src import cli

    env = tmp_path / ".env"
    env.write_text("FEISHU_ROOT_DOC=NMq0wmqEDiRkiAk2d8acp7mHnVd\n", encoding="utf-8")
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "old.md").write_text("# 旧笔记\n", encoding="utf-8")

    called: list[str] = []

    def fake_sync(rest, env_path, notes_dir, **kw):
        called.append(rest[0])
        print("同步完成")
        return 0

    monkeypatch.setattr(cli, "_run_sync", fake_sync)
    board = cli._build_board(env, notes, tmp_path / "profile" / "knowledge.md", None, None)

    result = board.run_action("sync")

    assert result.ok
    assert called == ["NMq0wmqEDiRkiAk2d8acp7mHnVd"], "配了 ROOT_DOC 就该同步它（全树）"


def test_board_sync_hint_when_root_doc_missing(tmp_path, monkeypatch):
    from src import cli

    env = tmp_path / ".env"
    env.write_text("LLM_PROVIDER=deepseek\n", encoding="utf-8")
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "old.md").write_text("# 旧笔记\n", encoding="utf-8")

    called: list[str] = []
    monkeypatch.setattr(cli, "_run_sync", lambda rest, *a, **kw: called.append(rest[0]) or 0)
    board = cli._build_board(env, notes, tmp_path / "profile" / "knowledge.md", None, None)

    result = board.run_action("sync")

    assert result.ok
    assert called == ["old"], "没配 ROOT_DOC 时退回同步最近一篇"
    assert "FEISHU_ROOT_DOC" in result.output, "提示语要说清怎么改成全树同步"
