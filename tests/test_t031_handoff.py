"""T-031 失败测试：DSH 接力上下文组装（F-14）。

交付物：profile/handoff/<任务id>.md —— 一个任务一个文件，重复点击覆盖同一文件。
文件必须按固定顺序包含五段：

1. 任务卡（目标 / 验收方式 / 用到的知识点，含新知识点）
2. 本次提交的代码（超长截断并注明）
3. 画像相关点（状态 + 证据；画像里没有的点要注明）
4. 书籍出处与章节（地图里找不到要注明）
5. 提问引导（至少两条可复制提问，含「我的代码哪里不足」「我该看书的哪部分」）

硬性约束：

- 任务时间戳未知 → 明确报错（中文），不生成文件；
- 缺数据（没提交代码 / 没画像 / 没地图 / 没任务卡）→ 明确占位说明，不静默留空、不崩溃；
- 落盘原子（tmp + replace），不留 .tmp。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.distill import KnowledgePoint
from src.handoff import (
    HandoffError,
    build_handoff_markdown,
    handoff_path,
    task_file_id,
    write_handoff,
)
from src.planner import TaskRecord
from src.profile import KnowledgeProfile
from src.review import MAX_CODE_CHARS
from src.syllabus import BookMap, Chapter

WHEN = "2026-09-27 10:30"
TASK_ID = "2026-09-27-1030"

SECTIONS = (
    "## 一、任务卡",
    "## 二、本次提交的代码",
    "## 三、画像相关点",
    "## 四、书籍出处与章节",
    "## 五、提问引导",
)


def make_record(**overrides) -> TaskRecord:
    payload = dict(
        when=WHEN,
        goal="用列表做一个待办清单",
        skills=["列表", "函数"],
        new_skill="字典",
        acceptance="运行后能添加/删除待办并打印全部条目",
        steps=["先定数据结构", "再实现增删"],
        source=None,
        reviews=[],
        order=0,
    )
    payload.update(overrides)
    return TaskRecord(**payload)


def make_profile() -> KnowledgeProfile:
    return KnowledgeProfile(
        points=[
            KnowledgePoint(
                name="列表",
                level="做过",
                evidence="产出：写过一个待办清单",
                topic="Python 基础",
            ),
            KnowledgePoint(name="函数", level="学过", evidence="笔记里能解释参数与返回值"),
        ]
    )


def make_books() -> list[BookMap]:
    return [
        BookMap(
            book="Python Crash Course",
            chapters=[Chapter(chapter="第 6 章 列表", points=["列表", "字典"])],
        )
    ]


def run_write(profile_dir, **overrides) -> Path:
    payload = dict(when=WHEN, record=make_record(), code="print('hi')")
    payload.update(overrides)
    return write_handoff(profile_dir, **payload)


def code_block(markdown: str) -> str:
    match = re.search(r"```\n(?P<code>.*?)\n```", markdown, re.DOTALL)
    return match.group("code") if match else ""


# --- 文件名 / 一任务一文件 -------------------------------------------------


def test_task_file_id_is_filename_safe():
    assert task_file_id(WHEN) == TASK_ID
    assert task_file_id("2026-09-27") == "2026-09-27"
    # 路径分隔符等危险字符绝不能出现在文件名里
    unsafe = task_file_id("2026/09/27 10:30")
    assert "/" not in unsafe and "\\" not in unsafe and ":" not in unsafe


def test_task_file_id_rejects_empty_timestamp():
    with pytest.raises(HandoffError) as excinfo:
        task_file_id("")
    assert "时间戳" in str(excinfo.value)


def test_handoff_path_lives_under_profile_handoff(tmp_path):
    path = handoff_path(tmp_path / "profile", WHEN)
    assert path == tmp_path / "profile" / "handoff" / f"{TASK_ID}.md"


def test_write_creates_file_under_profile_handoff(tmp_path):
    profile_dir = tmp_path / "profile"
    path = run_write(profile_dir)
    assert path.is_file()
    assert path.name == f"{TASK_ID}.md"
    assert path.parent.name == "handoff"


def test_repeated_write_keeps_one_file_and_updates_content(tmp_path):
    profile_dir = tmp_path / "profile"
    first = run_write(profile_dir, code="print('第一次')")
    second = run_write(profile_dir, code="print('第二次')")

    assert first == second
    markdown_files = sorted((profile_dir / "handoff").glob("*.md"))
    assert len(markdown_files) == 1
    text = second.read_text(encoding="utf-8")
    assert "第二次" in text
    assert "第一次" not in text


def test_different_tasks_get_different_files(tmp_path):
    profile_dir = tmp_path / "profile"
    run_write(profile_dir, when=WHEN)
    run_write(profile_dir, when="2026-09-28 09:00", record=make_record(when="2026-09-28 09:00"))
    assert len(list((profile_dir / "handoff").glob("*.md"))) == 2


# --- 时间戳缺失 -----------------------------------------------------------


def test_write_without_timestamp_raises_and_writes_nothing(tmp_path):
    profile_dir = tmp_path / "profile"
    with pytest.raises(HandoffError) as excinfo:
        write_handoff(profile_dir, when="", record=None, code="print('hi')")
    assert "时间戳" in str(excinfo.value)
    assert not (profile_dir / "handoff").exists() or not list((profile_dir / "handoff").glob("*.md"))


# --- 五段结构 -------------------------------------------------------------


def test_markdown_has_five_sections_in_fixed_order():
    text = build_handoff_markdown(
        make_record(), code="print('hi')", profile=make_profile(), books=make_books()
    )
    positions = [text.find(heading) for heading in SECTIONS]
    assert all(position >= 0 for position in positions), positions
    assert positions == sorted(positions)


def test_written_file_contains_all_five_sections(tmp_path):
    path = run_write(tmp_path / "profile", profile=make_profile(), books=make_books())
    text = path.read_text(encoding="utf-8")
    for heading in SECTIONS:
        assert heading in text


def test_task_card_carries_goal_acceptance_and_skills():
    text = build_handoff_markdown(make_record(), code="print('hi')")
    assert "用列表做一个待办清单" in text
    assert "运行后能添加/删除待办并打印全部条目" in text
    assert "列表" in text and "函数" in text
    assert "字典" in text                      # 新知识点也要出现在任务卡里


def test_missing_task_record_gives_explicit_placeholder():
    text = build_handoff_markdown(None, when=WHEN, code="print('hi')")
    assert SECTIONS[0] in text
    assert "任务卡" in text
    assert "没有" in text or "找不到" in text    # 明确说明缺什么，而不是静默留空


# --- 代码段 ---------------------------------------------------------------


def test_missing_code_gives_explicit_placeholder():
    text = build_handoff_markdown(make_record(), code="")
    assert SECTIONS[1] in text
    assert "没有提交代码" in text or "未提交代码" in text


def test_short_code_is_not_marked_truncated():
    text = build_handoff_markdown(make_record(), code="print('hi')")
    assert "print('hi')" in text
    assert "已截断" not in text


def test_long_code_is_truncated_and_noted():
    code = "x = 1\n" * (MAX_CODE_CHARS // 3)
    assert len(code) > MAX_CODE_CHARS
    text = build_handoff_markdown(make_record(), code=code)
    assert "已截断" in text
    assert str(len(code)) in text
    assert len(code_block(text)) <= MAX_CODE_CHARS


# --- 画像段 ---------------------------------------------------------------


def test_profile_section_shows_level_and_evidence():
    text = build_handoff_markdown(make_record(), code="print('hi')", profile=make_profile())
    assert "做过" in text
    assert "产出：写过一个待办清单" in text
    assert "Python 基础" in text


def test_profile_section_marks_points_missing_from_profile():
    text = build_handoff_markdown(make_record(), code="print('hi')", profile=make_profile())
    assert "字典" in text
    assert "画像里没有" in text


def test_profile_section_survives_no_profile():
    text = build_handoff_markdown(make_record(), code="print('hi')", profile=None)
    assert SECTIONS[2] in text
    assert "画像" in text          # 有说明，不崩溃


# --- 书籍出处段 -----------------------------------------------------------


def test_book_section_shows_book_and_chapter():
    text = build_handoff_markdown(make_record(), code="print('hi')", books=make_books())
    assert "Python Crash Course" in text
    assert "第 6 章 列表" in text


def test_book_section_marks_points_missing_from_map():
    record = make_record(skills=["列表", "闭包"], new_skill=None)
    text = build_handoff_markdown(record, code="print('hi')", books=make_books())
    assert "地图里找不到" in text


def test_book_section_survives_no_map():
    text = build_handoff_markdown(make_record(), code="print('hi')", books=None)
    assert SECTIONS[3] in text
    assert "知识地图" in text      # 明确说没有地图，不崩溃


# --- 提问引导段 -----------------------------------------------------------


def test_questions_are_present_and_copyable():
    text = build_handoff_markdown(make_record(), code="print('hi')")
    assert "我的代码哪里不足" in text
    assert "我该看书的哪部分" in text
    numbered = re.findall(r"^\s*\d+[.、]\s*\S+", text.split(SECTIONS[4])[1], re.M)
    assert len(numbered) >= 2


# --- 原子写 ---------------------------------------------------------------


def test_write_leaves_no_tmp_file(tmp_path):
    profile_dir = tmp_path / "profile"
    run_write(profile_dir)
    assert list((profile_dir / "handoff").glob("*.tmp")) == []


def test_write_is_atomic_and_cleans_tmp_on_failure(tmp_path, monkeypatch):
    profile_dir = tmp_path / "profile"

    def boom(self, target):  # noqa: ANN001 - 模拟落盘失败
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(HandoffError) as excinfo:
        run_write(profile_dir)
    assert "写入" in str(excinfo.value)
    assert list((profile_dir / "handoff").glob("*.tmp")) == []
