"""T-029 失败测试：出题主题过滤。

要求：
- 看板主题多选（默认全选，localStorage 记忆）；
- CLI next --topic（可重复）；
- 过滤作用于**画像知识池**与**新点选书范围**；
- **全不选明确报错不出题**。
"""

from __future__ import annotations

import re

import pytest

from src.dashboard import Dashboard, TaskBoard
from src.distill import KnowledgePoint
from src.planner import (
    PlannerError,
    filter_profile_by_topics,
    normalize_topics,
    selectable_topics,
)
from src.profile import KnowledgeProfile

HTML_TOPIC = "网页基础"
CSS_TOPIC = "样式与布局"


def make_profile():
    # 每个主题都留够 3 个「学过」的点：出题有 MIN_POINTS=3 的下限，
    # 裁剪后达不到下限会先报"知识点太少"，那样就测不出过滤本身了。
    return KnowledgeProfile(points=[
        KnowledgePoint("列表（ul/ol/li）", "学过", "e", topic=HTML_TOPIC),
        KnowledgePoint("表格（table/tr/th/td）", "学过", "e", topic=HTML_TOPIC),
        KnowledgePoint("超链接 a 标签", "学过", "e", topic=HTML_TOPIC),
        KnowledgePoint("颜色与单位", "学过", "e", topic=CSS_TOPIC),
        KnowledgePoint("盒模型", "学过", "e", topic=CSS_TOPIC),
        KnowledgePoint("字体与排版", "学过", "e", topic=CSS_TOPIC),
    ])


# ---------- 1. 基本过滤 ----------


def test_filter_keeps_only_selected_topics():
    filtered = filter_profile_by_topics(make_profile(), ["网页基础"])

    names = [p.name for p in filtered.points]
    assert names == ["列表（ul/ol/li）", "表格（table/tr/th/td）", "超链接 a 标签"]


def test_filter_with_no_topics_returns_original():
    """没给 topic 参数 = 不过滤（与旧行为一致）。"""
    profile = make_profile()

    assert filter_profile_by_topics(profile, None) is profile
    assert filter_profile_by_topics(profile, []) is profile


def test_selectable_topics_lists_all():
    assert selectable_topics(make_profile()) == [HTML_TOPIC, CSS_TOPIC]


def test_selectable_topics_puts_unclassified_last():
    profile = KnowledgeProfile(points=[
        KnowledgePoint("无主题点", "学过", "e"),
        KnowledgePoint("有主题点", "学过", "e", topic=HTML_TOPIC),
    ])

    assert selectable_topics(profile) == [HTML_TOPIC, "未分类"]


def test_normalize_topics_dedupes_and_strips():
    assert normalize_topics([" 网页基础 ", "网页基础", "", "样式与布局"]) == ["网页基础", "样式与布局"]


# ---------- 2. 全不选必须报错 ----------


def test_excluding_every_topic_raises():
    """全不选 = 没有知识池 → 明确报错，不能硬出题。"""
    from src.planner import resolve_topics

    with pytest.raises(PlannerError) as exc:
        resolve_topics(["网页基础", "样式与布局"], exclude=["网页基础", "样式与布局"])

    assert "主题" in str(exc.value)


def test_normalize_topics_rejects_empty_selection():
    from src.planner import resolve_topics

    with pytest.raises(PlannerError):
        resolve_topics(["网页基础"], exclude=["网页基础"])


def test_resolve_topics_keeps_unselected():
    from src.planner import resolve_topics

    assert resolve_topics(["网页基础", "样式与布局"], exclude=["样式与布局"]) == ["网页基础"]


def test_build_next_messages_omits_excluded_topics():
    """只选「网页基础」时，prompt 里不该出现「样式与布局」的点。

    （topics 的语义是"只在这些主题里"，不是"排除这些主题"。）
    """
    messages = build_next_messages_safe(make_profile(), ["网页基础"])

    blob = str(messages)
    assert "列表（ul/ol/li）" in blob
    assert "盒模型" not in blob, "未选中主题的知识点不该进 prompt"
    assert "颜色与单位" not in blob
    assert "字体与排版" not in blob


def build_next_messages_safe(profile, topics):
    """注意：topics 必须用关键字传——第二个位置参数是 syllabus。"""
    from src.planner import build_next_messages

    return build_next_messages(profile, topics=topics)


# ---------- 3. 出题不引用被排除主题 ----------


def test_generate_task_respects_topics():
    from src.planner import generate_task

    class Stub:
        def __init__(self):
            self.seen = []

        def complete(self, messages):
            self.seen.append(str(messages))
            return (
                '{"goal": "做一个列表页", "skills": ["列表（ul/ol/li）"], '
                '"steps": ["写 ul"], "acceptance": "能看到列表", "reason": "r"}'
            )

    stub = Stub()
    task = generate_task(make_profile(), completer=stub, topics=["网页基础"])

    assert "盒模型" not in stub.seen[0]
    assert "颜色与单位" not in stub.seen[0]
    assert "列表（ul/ol/li）" in str(task.skills) or "列表" in task.goal


def test_generate_task_rejects_skills_outside_selected_topics():
    """LLM 硬塞被排除主题的点 → 越界校验应拦下（复用现有越界机制）。"""
    from src.planner import generate_task

    class Stub:
        def complete(self, messages):
            return (
                '{"goal": "搞盒模型", "skills": ["盒模型"], '
                '"steps": ["x"], "acceptance": "a", "reason": "r"}'
            )

    with pytest.raises(PlannerError):
        generate_task(make_profile(), completer=Stub(), topics=["网页基础"], attempts=1)


# ---------- 4. 新点选书范围也受过滤 ----------


def test_next_unmet_point_for_books_respects_topics():
    from src.planner import next_unmet_point_for_books
    from src.syllabus import BookMap, Chapter

    books = [
        BookMap(book="网页书", chapters=[Chapter("第 1 章", ["网格布局", "弹性盒"])]),
        BookMap(book="样式书", chapters=[Chapter("第 1 章", ["颜色与单位"])]),
    ]
    profile = KnowledgeProfile(points=[
        KnowledgePoint("网格布局", "存疑", "e", topic="网页基础"),
        KnowledgePoint("颜色与单位", "存疑", "e", topic="样式与布局"),
    ])

    picked = next_unmet_point_for_books(books, profile, topics=["样式与布局"])

    assert picked != "网格布局", "被排除主题的新点不该被选中"


# ---------- 5. 看板：多选 + localStorage ----------


def test_dashboard_has_topic_filter(tmp_path):
    directory = tmp_path / "profile"
    directory.mkdir(parents=True)
    from src.profile import write_profile_atomic

    write_profile_atomic(directory / "knowledge.md", make_profile())
    page = TaskBoard(directory).pages()[""]

    assert "topic-filter" in page
    assert re.search(r'name="topics?"', page), "要有主题多选控件"
    assert 'value="网页基础"' in page
    assert 'value="样式与布局"' in page


def test_dashboard_topics_default_all_checked(tmp_path):
    directory = tmp_path / "profile"
    directory.mkdir(parents=True)
    from src.profile import write_profile_atomic

    write_profile_atomic(directory / "knowledge.md", make_profile())
    page = TaskBoard(directory).pages()[""]

    boxes = re.findall(r'<input[^>]*name="topics"[^>]*>', page)
    assert len(boxes) == 2, f"应有 2 个主题复选框，实际 {len(boxes)}"
    assert all("checked" in box for box in boxes), "默认全选"


def test_dashboard_topic_filter_uses_localstorage(tmp_path):
    directory = tmp_path / "profile"
    directory.mkdir(parents=True)
    from src.profile import write_profile_atomic

    write_profile_atomic(directory / "knowledge.md", make_profile())
    page = TaskBoard(directory).pages()[""]

    assert "localStorage" in page


def test_next_action_accepts_topics_param(tmp_path):
    from src.dashboard import ACTION_PARAM_KEYS

    assert ACTION_PARAM_KEYS["next"] == frozenset({"topics"})


def test_next_action_passes_topics_through(tmp_path):
    seen = {}

    def op_next(topics=None):
        seen["topics"] = topics
        return "ok"

    directory = tmp_path / "profile"
    directory.mkdir(parents=True)
    board = TaskBoard(directory, operations={"next": op_next})

    result = board.run_action("next", {"topics": ["网页基础"]})

    assert result.ok
    assert seen["topics"] == ["网页基础"]


# ---------- 6. CLI ----------


def test_cli_next_accepts_repeated_topic(tmp_path, monkeypatch, capsys):
    from src import cli

    seen = {}

    def fake_next(rest, env_path, **kw):
        seen["rest"] = rest
        return 0

    monkeypatch.setattr(cli, "_run_next", fake_next)
    directory = tmp_path / "profile"
    directory.mkdir(parents=True)
    from src.profile import write_profile_atomic

    write_profile_atomic(directory / "knowledge.md", make_profile())

    code = cli.main(
        ["next", "--topic", "网页基础", "--topic", "样式与布局"],
        env_path=tmp_path / ".env",
        profile_path=directory / "knowledge.md",
    )
    capsys.readouterr()

    assert code == 0
    # main 把参数原样交给 _run_next 解析（--topic 可重复）；这里断言"确实传到了"
    assert seen["rest"] == ["--topic", "网页基础", "--topic", "样式与布局"], f"实际 {seen}"


def test_cli_next_without_topic_passes_none(tmp_path, monkeypatch, capsys):
    from src import cli

    seen = {}
    monkeypatch.setattr(cli, "_run_next", lambda rest, env_path, **kw: seen.update(kw) or 0)
    directory = tmp_path / "profile"
    directory.mkdir(parents=True)
    from src.profile import write_profile_atomic

    write_profile_atomic(directory / "knowledge.md", make_profile())

    cli.main(["next"], env_path=tmp_path / ".env", profile_path=directory / "knowledge.md")
    capsys.readouterr()

    assert seen.get("topics") is None
