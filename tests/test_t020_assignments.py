"""T-020 失败测试：经典课程实验题库 + planner 命中。

需求（F-09）：

- 新建 profile/assignments.md，收录公开入门课程实验的题目骨架 + 知识点标签，首批 10~15 条；
- planner 出题**先按画像匹配题库**，命中则以该实验为骨架出任务并**注明出处课程**；
- 未命中回退 LLM 出题；
- 验收：题库中至少 3 条与当前画像匹配的任务能正确命中并注明出处；无匹配时回退正常。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.assignments import (
    Assignment,
    assignment_to_task,
    load_assignments,
    pick_assignment,
)
from src.distill import KnowledgePoint
from src.planner import GeneratedTask, PlannerError, generate_task, render_task
from src.profile import KnowledgeProfile


BANK = """---
title: 题库
---

## A-01 个人名片页

```yaml
course: 哈佛 CS50（HTML 基础单元）
tags: [HTML 文档结构（DOCTYPE/head/body）, 标题与文本格式化标签, 列表（ul/ol/li）]
level: 入门
new_skill: ""
```

**目标**：做一个单文件 card.html。

**实现要点**：
1. 用完整文档结构；
2. 姓名用 h1。

**验收方式**：浏览器打开能看到名片。

---

## A-02 课程表表格页

```yaml
course: 哈佛 CS50（HTML 基础单元）
tags: [表格（table/tr/th/td）, 标题与文本格式化标签]
level: 入门
new_skill: ""
```

**目标**：做一个 schedule.html。

**实现要点**：
1. 表头用 th；
2. 表体用 td。

**验收方式**：能数出 4 行。

---

## A-03 待办清单

```yaml
course: 哈佛 CS50P（Python 入门）
tags: [列表]
level: 入门
new_skill: ""
```

**目标**：写一个命令行待办清单。

**实现要点**：
1. 用列表存待办；
2. 循环显示菜单。

**验收方式**：添加 3 条能查看。

---

## A-04 词频统计（需要字典）

```yaml
course: MIT 6.0001
tags: [列表]
level: 进阶
new_skill: 字典
```

**目标**：统计词频。

**实现要点**：
1. split 成列表。

**验收方式**：前 5 名正确。
"""


def write_bank(tmp_path) -> Path:
    path = tmp_path / "assignments.md"
    path.write_text(BANK, encoding="utf-8")
    return path


def profile_with(*pairs):
    return KnowledgeProfile(points=[KnowledgePoint(name, level, "e") for name, level in pairs])


HTML_PROFILE = profile_with(
    ("HTML 文档结构（DOCTYPE/head/body）", "做过"),
    ("标题与文本格式化标签", "做过"),
    ("列表（ul/ol/li）", "做过"),
    ("表格（table/tr/th/td）", "做过"),
)


# --- 1. 解析 -----------------------------------------------------------------


def test_load_assignments_parses_all_entries(tmp_path):
    items = load_assignments(write_bank(tmp_path))

    assert len(items) == 4
    assert [a.ident for a in items] == ["A-01", "A-02", "A-03", "A-04"]


def test_assignment_fields_are_parsed(tmp_path):
    first = load_assignments(write_bank(tmp_path))[0]

    assert first.title == "个人名片页"
    assert "CS50" in first.course
    assert first.goal.startswith("做一个单文件")
    assert len(first.steps) == 2
    assert "浏览器打开" in first.acceptance
    assert first.tags[0] == "HTML 文档结构（DOCTYPE/head/body）"


def test_missing_file_returns_empty_list(tmp_path):
    assert load_assignments(tmp_path / "nope.md") == []


def test_broken_entry_is_skipped_not_fatal(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("## A-99 缺元信息\n\n**目标**：没有 yaml 块\n", encoding="utf-8")

    assert load_assignments(path) == []


# --- 2. 匹配 -----------------------------------------------------------------


def test_pick_prefers_most_mastered_tags(tmp_path):
    items = load_assignments(write_bank(tmp_path))

    picked = pick_assignment(items, HTML_PROFILE)

    assert picked is not None
    # A-01 命中 3 个已掌握标签，A-02 命中 2 个
    assert picked.ident == "A-01"


def test_pick_returns_none_when_nothing_matches():
    items = [Assignment(ident="A-04", title="词频", course="MIT", tags=["完全不存在的东西"],
                        goal="g", steps=[], acceptance="a", level="入门", new_skill=None)]

    assert pick_assignment(items, HTML_PROFILE) is None


def test_pick_requires_at_least_one_mastered_tag():
    items = [Assignment(ident="A-01", title="t", course="c", tags=["字典", "循环"],
                        goal="g", steps=[], acceptance="a", level="入门", new_skill=None)]

    assert pick_assignment(items, HTML_PROFILE) is None


def test_pick_prefers_fewer_new_skills():
    """两条都命中时，优先选不需要新知识点的。"""
    items = [
        Assignment(ident="A-10", title="要新点", course="c", tags=["列表（ul/ol/li）"],
                   goal="g", steps=[], acceptance="a", level="进阶", new_skill="字典"),
        Assignment(ident="A-11", title="不要新点", course="c", tags=["列表（ul/ol/li）"],
                   goal="g", steps=[], acceptance="a", level="入门", new_skill=None),
    ]

    picked = pick_assignment(items, HTML_PROFILE)

    assert picked.ident == "A-11"


# --- 3. 转成任务 -------------------------------------------------------------


def test_assignment_to_task_notes_course(tmp_path):
    item = load_assignments(write_bank(tmp_path))[0]

    task = assignment_to_task(item, HTML_PROFILE)

    assert isinstance(task, GeneratedTask)
    assert task.source and "CS50" in task.source
    assert set(task.skills) <= {p.name for p in HTML_PROFILE.points}
    assert task.goal == item.goal


def test_assignment_to_task_records_new_skill(tmp_path):
    item = [a for a in load_assignments(write_bank(tmp_path)) if a.ident == "A-04"][0]
    profile = profile_with(("列表", "做过"))

    task = assignment_to_task(item, profile)

    assert task.new_skill == "字典"


def test_render_task_shows_source():
    task = GeneratedTask(goal="做一个名片页", skills=["列表（ul/ol/li）"], acceptance="能看到",
                         steps=["a"], source="哈佛 CS50（HTML 基础单元）")

    text = render_task(task)

    assert "哈佛 CS50" in text
    assert "题库" in text or "出处" in text


def test_render_task_without_source_has_no_source_line():
    task = GeneratedTask(goal="g", skills=["列表"], acceptance="a")

    assert "出处" not in render_task(task)


# --- 4. generate_task：命中题库就不调 LLM ------------------------------------


class ExplodingCompleter:
    """被调用就失败：用来证明命中题库时没有调用 LLM。"""

    def __init__(self):
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        raise AssertionError("命中题库时不应调用 LLM")


def test_generate_task_uses_bank_without_llm(tmp_path):
    completer = ExplodingCompleter()

    task = generate_task(
        HTML_PROFILE, completer=completer, assignments=load_assignments(write_bank(tmp_path))
    )

    assert completer.calls == 0
    assert task.source and "CS50" in task.source


def test_generate_task_falls_back_to_llm_when_no_match(tmp_path):
    bank = [Assignment(ident="A-01", title="t", course="c", tags=["字典"],
                       goal="g", steps=[], acceptance="a", level="入门", new_skill=None)]

    class Stub:
        def __init__(self):
            self.calls = 0

        def complete(self, messages):
            self.calls += 1
            return json.dumps({
                "goal": "写个通讯录", "skills": ["列表（ul/ol/li）"],
                "acceptance": "能存盘", "steps": ["a"],
            }, ensure_ascii=False)

    stub = Stub()
    task = generate_task(HTML_PROFILE, completer=stub, assignments=bank)

    assert stub.calls == 1
    assert task.goal == "写个通讯录"
    assert not task.source  # 回退出题没有出处


def test_generate_task_without_bank_still_works(tmp_path):
    class Stub:
        def complete(self, messages):
            return json.dumps({"goal": "g", "skills": ["列表（ul/ol/li）"],
                               "acceptance": "a", "steps": []}, ensure_ascii=False)

    task = generate_task(HTML_PROFILE, completer=Stub(), assignments=None)

    assert task.goal == "g"


def test_generate_task_still_enforces_mastered_gate(tmp_path):
    thin = profile_with(("列表", "存疑"))

    with pytest.raises(PlannerError):
        generate_task(thin, completer=ExplodingCompleter(),
                      assignments=load_assignments(write_bank(tmp_path)))


# --- 5. 仓库里的真实题库 ------------------------------------------------------


def test_shipped_bank_has_10_to_15_entries():
    items = load_assignments(Path("profile/assignments.md"))

    assert 10 <= len(items) <= 15


def test_shipped_bank_entries_all_have_course_and_tags():
    for item in load_assignments(Path("profile/assignments.md")):
        assert item.course, f"{item.ident} 缺出处课程"
        assert item.tags, f"{item.ident} 缺知识点标签"
        assert item.goal and item.acceptance, f"{item.ident} 缺目标或验收方式"


def test_shipped_bank_only_uses_profile_known_tags():
    """标签必须是画像里真实存在的知识点名，否则匹配永远命中不了。"""
    profile = KnowledgeProfile.load("profile/knowledge.md")
    known = {p.name for p in profile.points}
    unknown = {
        f"{item.ident}:{tag}"
        for item in load_assignments(Path("profile/assignments.md"))
        for tag in item.tags
        if tag not in known
    }

    assert unknown == set()


def test_shipped_bank_matches_current_profile_at_least_three():
    """验收：题库中至少 3 条能与当前画像匹配。"""
    profile = KnowledgeProfile.load("profile/knowledge.md")
    items = load_assignments(Path("profile/assignments.md"))

    matched = [a for a in items if pick_assignment([a], profile) is not None]

    assert len(matched) >= 3


def test_shipped_bank_has_no_private_note_content():
    """题库只放公开课程的题目骨架，不得混入个人笔记内容。"""
    text = Path("profile/assignments.md").read_text(encoding="utf-8")

    assert "笔记：" not in text
    assert "复述：" not in text

# --- 6. A-06：命中题库也必须服从「新点来自地图按书序的下一个未掌握点」 ----------------


def syllabus_with(*points):
    """构造一个单章的地图（书序 = 参数顺序）。"""
    return {"book": "某书", "chapters": [{"chapter": "第 1 章", "points": list(points)}]}


def test_next_unmet_point_returns_first_unmastered_in_book_order():
    from src.planner import next_unmet_point

    profile = profile_with(("A", "学过"), ("B", "存疑"))

    assert next_unmet_point(syllabus_with("A", "B", "C"), profile) == "B"


def test_bank_hit_with_wrong_new_skill_falls_back_to_llm():
    """A-06：有地图时，任务的新点必须是地图里按书序的下一个未掌握点。

    题库条目自带 new_skill（A-04 是「字典」），但地图要求的可能是别的点 ——
    这种情况下不能直接采用题库条目，必须回退 LLM 出题。
    """
    bank = [Assignment(ident="A-01", title="t", course="c", tags=["列表（ul/ol/li）"],
                       goal="题库目标", steps=[], acceptance="a", level="入门",
                       new_skill="字典")]

    class Stub:
        def __init__(self):
            self.calls = 0

        def complete(self, messages):
            self.calls += 1
            return json.dumps({"goal": "LLM 目标", "skills": ["列表（ul/ol/li）"],
                               "new_skill": "循环", "acceptance": "a", "steps": []},
                              ensure_ascii=False)

    stub = Stub()
    task = generate_task(
        HTML_PROFILE, completer=stub, assignments=bank,
        syllabus=syllabus_with("循环", "函数"),
    )

    assert stub.calls == 1
    assert task.goal == "LLM 目标"
    assert task.source is None


def test_bank_hit_matching_syllabus_new_skill_is_used():
    """新点与地图要求一致时，题库条目照常采用（不走 LLM）。"""
    bank = [Assignment(ident="A-01", title="t", course="c", tags=["列表（ul/ol/li）"],
                       goal="题库目标", steps=[], acceptance="a", level="入门",
                       new_skill="循环")]

    task = generate_task(
        HTML_PROFILE, completer=ExplodingCompleter(), assignments=bank,
        syllabus=syllabus_with("循环", "函数"),
    )

    assert task.goal == "题库目标"
    assert task.new_skill == "循环"


def test_bank_hit_without_new_skill_is_allowed_even_with_syllabus():
    """题库条目不引入新点时，不违反 A-06（A-06 管的是"新点从哪来"）。"""
    bank = [Assignment(ident="A-01", title="t", course="c", tags=["列表（ul/ol/li）"],
                       goal="题库目标", steps=[], acceptance="a", level="入门", new_skill=None)]

    task = generate_task(
        HTML_PROFILE, completer=ExplodingCompleter(), assignments=bank,
        syllabus=syllabus_with("循环"),
    )

    assert task.goal == "题库目标"
