"""T-014 失败测试：改状态的名称匹配歧义（Bug 修复，C 段流程）。

现象（可确认事实）：真实画像里同时存在
  - 「列表（ul/ol/li）」（主题 HTML 基础）
  - 「列表」（主题 Python 基础）
两条归一化后都是「列表」。POST 改「列表」时命中了 HTML 那条并报成功，目标条目没变。

要求（任务卡）：
1. 精确匹配优先（存在与输入完全同名的条目就改它）；
2. 多个候选（归一化后同名）时**返回候选列表**，让客户端带主题名重试；
3. **禁止模糊命中后报成功**。
"""

from __future__ import annotations

import pytest

from src.distill import KnowledgePoint
from src.profile import (
    KnowledgeProfile,
    ProfileError,
    mark_done,
    normalize_point_name,
    set_level,
)


def conflicting_profile():
    """已知现场：两条归一化后同名的知识点。"""
    return KnowledgeProfile(
        points=[
            KnowledgePoint("列表（ul/ol/li）", "做过", "HTML 列表笔记", "HTML 基础"),
            KnowledgePoint("列表", "学过", "Python 列表笔记", "Python 基础"),
        ]
    )


# --- 1. 精确匹配优先 -------------------------------------------------------


def test_exact_match_wins_over_fuzzy_sibling():
    """输入「列表」时，必须命中同名的「列表」，而不是归一化后同名的「列表（ul/ol/li）」。"""
    updated = set_level(conflicting_profile(), "列表", "做过")

    python_point = next(p for p in updated.points if p.name == "列表")
    html_point = next(p for p in updated.points if p.name == "列表（ul/ol/li）")
    assert python_point.level == "做过"
    assert html_point.level == "做过"  # 原本就是做过，未被这次改动影响


def test_exact_match_keeps_other_entry_untouched():
    updated = set_level(conflicting_profile(), "列表", "存疑")

    html_point = next(p for p in updated.points if p.name == "列表（ul/ol/li）")
    python_point = next(p for p in updated.points if p.name == "列表")
    assert python_point.level == "存疑"
    assert html_point.level == "做过"  # 没被改掉
    assert html_point.evidence == "HTML 列表笔记"


def test_full_name_with_topic_suffix_still_works():
    """带主题括号的完整名称是精确匹配，照旧可用。"""
    updated = set_level(conflicting_profile(), "列表（ul/ol/li）", "存疑")

    html_point = next(p for p in updated.points if p.name == "列表（ul/ol/li）")
    assert html_point.level == "存疑"


# --- 2. 歧义必须报错，不许模糊命中报成功 -----------------------------------


def test_ambiguous_normalized_name_raises_with_candidates():
    """输入既非精确同名、又能匹配多条（如只有「列表（ul/ol/li）」和「列表（Python）」时）→ 报歧义。"""
    profile = KnowledgeProfile(
        points=[
            KnowledgePoint("列表（ul/ol/li）", "做过", "e1", "HTML 基础"),
            KnowledgePoint("列表（Python）", "学过", "e2", "Python 基础"),
        ]
    )

    with pytest.raises(ProfileError) as exc:
        set_level(profile, "列表", "学过")

    message = str(exc.value)
    assert "列表（ul/ol/li）" in message
    assert "列表（Python）" in message
    assert "主题" in message or "候选" in message


def test_ambiguous_name_does_not_report_success():
    """禁止「模糊命中后报成功」：必须抛错，不能返回被改动的画像。"""
    profile = KnowledgeProfile(
        points=[
            KnowledgePoint("列表（A）", "做过", "e1", "主题A"),
            KnowledgePoint("列表（B）", "学过", "e2", "主题B"),
        ]
    )

    with pytest.raises(ProfileError):
        set_level(profile, "列表", "存疑")


def test_ambiguous_mark_done_also_refuses():
    """mark_done 有同样的歧义问题，必须一起修。"""
    profile = KnowledgeProfile(
        points=[
            KnowledgePoint("列表（A）", "学过", "e1", "主题A"),
            KnowledgePoint("列表（B）", "学过", "e2", "主题B"),
        ]
    )

    with pytest.raises(ProfileError) as exc:
        mark_done(profile, "列表", "out.py")
    assert "候选" in str(exc.value) or "主题" in str(exc.value)


def test_mark_done_exact_match_wins():
    updated = mark_done(conflicting_profile(), "列表", "tasks/wordcount.py")

    python_point = next(p for p in updated.points if p.name == "列表")
    html_point = next(p for p in updated.points if p.name == "列表（ul/ol/li）")
    assert python_point.level == "做过"
    assert "tasks/wordcount.py" in python_point.evidence
    assert "tasks/wordcount.py" not in html_point.evidence


# --- 3. 候选提示要可操作 ---------------------------------------------------


def test_ambiguous_error_lists_topic_for_retry():
    profile = KnowledgeProfile(
        points=[
            KnowledgePoint("列表（ul/ol/li）", "做过", "e1", "HTML 基础"),
            KnowledgePoint("列表（Python）", "学过", "e2", "Python 基础"),
        ]
    )

    with pytest.raises(ProfileError) as exc:
        set_level(profile, "列表", "学过")

    message = str(exc.value)
    # 候选要带上主题，客户才知道该重试哪个完整名称
    assert "HTML 基础" in message
    assert "Python 基础" in message


def test_single_normalized_match_still_works():
    """只有一个归一化匹配时不该报歧义（保持原有便利）。"""
    profile = KnowledgeProfile(points=[KnowledgePoint("列表（Python 基础）", "学过", "e", "Python 基础")])

    updated = set_level(profile, "列表", "做过")

    assert updated.points[0].level == "做过"


def test_no_match_creates_new_point():
    """T-023 L-01 起：完全匹配不到就**新增条目**（旧行为是报错并列出候选）。

    注意与「歧义」区分：归一化后撞名仍然报错（那需要人工判断），只是"没有这个点"不再报错。
    """
    profile = KnowledgeProfile(points=[KnowledgePoint("字典", "学过", "e")])

    updated = set_level(profile, "列表", "学过")

    assert [p.name for p in updated.points] == ["字典", "列表"]
    assert updated.points[1].level == "学过"


def test_ambiguous_match_still_raises():
    """歧义（归一化后撞名）仍必须报错，让调用方带完整名称重试。"""
    profile = KnowledgeProfile(points=[
        KnowledgePoint("列表（A）", "学过", "e", "主题A"),
        KnowledgePoint("列表（B）", "学过", "e", "主题B"),
    ])

    with pytest.raises(ProfileError) as exc:
        set_level(profile, "列表", "学过")

    assert "候选" in str(exc.value) or "主题" in str(exc.value)


# --- 4. 看板层：歧义要变成可展示的失败，且不写文件 -------------------------


def test_board_ambiguous_status_reports_failure(tmp_path):
    import pathlib
    from src.dashboard import TaskBoard

    directory = tmp_path / "profile"
    from src.profile import write_profile_atomic

    write_profile_atomic(directory / "knowledge.md", KnowledgeProfile(points=[
        KnowledgePoint("列表（A）", "做过", "e1", "主题A"),
        KnowledgePoint("列表（B）", "学过", "e2", "主题B"),
    ]))
    before = (directory / "knowledge.md").read_bytes()
    board = TaskBoard(directory)

    result = board.run_action("status", {"name": "列表", "level": "存疑"})

    assert not result.ok
    assert result.status == 400
    assert "列表（A）" in result.output or "列表（B）" in result.output
    assert (directory / "knowledge.md").read_bytes() == before


def test_board_exact_name_change_succeeds(tmp_path):
    import pathlib
    from src.dashboard import TaskBoard
    from src.profile import write_profile_atomic

    directory = tmp_path / "profile"
    write_profile_atomic(directory / "knowledge.md", conflicting_profile())
    board = TaskBoard(directory)

    result = board.run_action("status", {"name": "列表", "level": "做过"})

    assert result.ok
    reloaded = KnowledgeProfile.load(directory / "knowledge.md")
    assert next(p for p in reloaded.points if p.name == "列表").level == "做过"
    assert next(p for p in reloaded.points if p.name == "列表（ul/ol/li）").level == "做过"
