"""T-019 失败测试：画像第四态「输出」+ 费曼复述。

需求（F-08，见 [[04-任务与验收清单]] T-019）：

- 状态机扩展为 学过 → 做过 → 输出，存疑不变；
- done 命令与看板回写表单增加可选「复述」文本框，内容作为证据追加；
- 看板配色扩展第四色；
- distill 合并的「只升不降」规则覆盖新状态。
"""

from __future__ import annotations

import pathlib

import pytest

from src.dashboard import TaskBoard
from src.distill import KnowledgePoint
from src.profile import (
    LEVELS,
    LEVEL_RANK,
    KnowledgeProfile,
    ProfileError,
    mark_done,
    merge_points,
    set_level,
    write_profile_atomic,
)


def profile_with(*points):
    return KnowledgeProfile(points=list(points))


# --- 1. 四态定义与排序 -------------------------------------------------------


def test_output_is_the_fourth_level():
    assert "输出" in LEVELS
    assert len(LEVELS) == 4
    assert set(LEVELS) == {"学过", "做过", "输出", "存疑"}


def test_level_rank_orders_unsure_learned_done_output():
    assert LEVEL_RANK["存疑"] < LEVEL_RANK["学过"] < LEVEL_RANK["做过"] < LEVEL_RANK["输出"]


def test_rendering_keeps_four_state_counts():
    profile = profile_with(
        KnowledgePoint("A", "学过", "e"),
        KnowledgePoint("B", "做过", "e"),
        KnowledgePoint("C", "输出", "e"),
        KnowledgePoint("D", "存疑", "e"),
    )
    from src.profile import render_profile

    text = render_profile(profile)

    assert "| 输出 | 1 |" in text
    assert "| 学过 | 1 |" in text


# --- 2. merge：只升不降覆盖新状态 -------------------------------------------


def test_merge_upgrades_done_to_output():
    profile = profile_with(KnowledgePoint("列表", "做过", "old"))

    merged = merge_points(profile, [KnowledgePoint("列表", "输出", "费曼复述")])

    assert merged.points[0].level == "输出"


def test_merge_never_downgrades_output_to_done():
    profile = profile_with(KnowledgePoint("列表", "输出", "old"))

    merged = merge_points(profile, [KnowledgePoint("列表", "做过", "new")])

    assert merged.points[0].level == "输出"


def test_merge_unsure_still_overrides_everything():
    """存疑是「信息不足」信号，仍可下降提醒复核（既有规则不变）。"""
    profile = profile_with(KnowledgePoint("列表", "输出", "old"))

    merged = merge_points(profile, [KnowledgePoint("列表", "存疑", "只提一句")])

    assert merged.points[0].level == "存疑"


def test_merge_accepts_output_level_as_valid():
    merged = merge_points(KnowledgeProfile(), [KnowledgePoint("列表", "输出", "复述")])

    assert merged.points[0].level == "输出"


# --- 3. done 带复述 → 升「输出」，复述进证据 --------------------------------


def test_mark_done_with_recite_upgrades_to_output():
    profile = profile_with(KnowledgePoint("列表", "学过", "来自笔记"))

    updated = mark_done(profile, "列表", "out.py", recite="我用方括号建了一个待办列表，能增删")

    point = updated.points[0]
    assert point.level == "输出"
    assert "我用方括号建了一个待办列表" in point.evidence
    assert "out.py" in point.evidence


def test_mark_done_without_recite_stays_done():
    profile = profile_with(KnowledgePoint("列表", "学过", "来自笔记"))

    updated = mark_done(profile, "列表", "out.py")

    assert updated.points[0].level == "做过"


def test_recite_is_appended_not_replacing_evidence():
    profile = profile_with(KnowledgePoint("列表", "学过", "原证据"))

    updated = mark_done(profile, "列表", "out.py", recite="复述内容")

    evidence = updated.points[0].evidence
    assert "原证据" in evidence and "out.py" in evidence and "复述内容" in evidence


def test_mark_done_recite_is_idempotent():
    profile = profile_with(KnowledgePoint("列表", "学过", "e"))
    once = mark_done(profile, "列表", "out.py", recite="同一段复述")
    twice = mark_done(once, "列表", "out.py", recite="同一段复述")

    assert twice.points[0].evidence.count("同一段复述") == 1


def test_blank_recite_is_treated_as_absent():
    profile = profile_with(KnowledgePoint("列表", "学过", "e"))

    updated = mark_done(profile, "列表", "out.py", recite="   ")

    assert updated.points[0].level == "做过"


# --- 4. set_level 支持第四态 -------------------------------------------------


def test_set_level_accepts_output():
    profile = profile_with(KnowledgePoint("列表", "学过", "e"))

    updated = set_level(profile, "列表", "输出", note="复述一段")

    assert updated.points[0].level == "输出"
    assert "复述一段" in updated.points[0].evidence


def test_set_level_still_rejects_unknown_level():
    profile = profile_with(KnowledgePoint("列表", "学过", "e"))

    with pytest.raises(ProfileError):
        set_level(profile, "列表", "精通")


# --- 5. CLI：done 支持 --recite ---------------------------------------------


def test_cli_done_recite_flag(tmp_path, capsys):
    from src import cli

    target = tmp_path / "profile" / "knowledge.md"
    write_profile_atomic(target, profile_with(KnowledgePoint("列表", "学过", "e")))

    code = cli.main(
        ["done", "列表", "out.py", "--recite", "我用列表做了待办清单"],
        profile_path=target,
    )
    capsys.readouterr()

    assert code == 0
    point = KnowledgeProfile.load(target).points[0]
    assert point.level == "输出"
    assert "我用列表做了待办清单" in point.evidence


def test_cli_done_recite_without_value_exits_2(tmp_path, capsys):
    from src import cli

    target = tmp_path / "profile" / "knowledge.md"
    write_profile_atomic(target, profile_with(KnowledgePoint("列表", "学过", "e")))

    code = cli.main(["done", "列表", "out.py", "--recite"], profile_path=target)
    out = capsys.readouterr()

    assert code == 2
    assert "--recite" in out.err


# --- 6. 看板：第四色 + 复述框 -----------------------------------------------


def test_board_status_offers_four_levels(tmp_path):
    directory = tmp_path / "profile"
    write_profile_atomic(directory / "knowledge.md", profile_with(KnowledgePoint("列表", "学过", "e")))
    page = TaskBoard(directory).pages()["knowledge"]

    for level in ("学过", "做过", "输出", "存疑"):
        assert level in page
    assert "level-输出" in page
    assert ".level-输出" in page


def test_board_status_can_set_output_with_note(tmp_path):
    directory = tmp_path / "profile"
    write_profile_atomic(directory / "knowledge.md", profile_with(KnowledgePoint("列表", "学过", "e")))
    board = TaskBoard(directory)

    result = board.run_action("status", {"name": "列表", "level": "输出", "note": "复述：列表就是有序容器"})

    assert result.ok
    point = KnowledgeProfile.load(directory / "knowledge.md").points[0]
    assert point.level == "输出"
    assert "复述：列表就是有序容器" in point.evidence


def test_board_form_has_recite_field(tmp_path):
    """T-026 起：复述框在**回写表单**里（状态表单只管改状态）。"""
    directory = tmp_path / "profile"
    write_profile_atomic(directory / "knowledge.md", profile_with(KnowledgePoint("列表", "学过", "e")))
    page = TaskBoard(directory).pages()["knowledge"]

    assert 'name="recite"' in page
    assert "复述" in page
    # 状态表单本身不再带复述/说明输入框
    import re

    match = re.search(r'<form[^>]*action="/action/status"[^>]*>(?P<body>.*?)</form>', page, re.S)
    assert match and 'name="recite"' not in match.group("body")


def test_board_action_param_whitelist_allows_note(tmp_path):
    """note 本来就在白名单里；确认没被 T-013 收紧掉。"""
    directory = tmp_path / "profile"
    write_profile_atomic(directory / "knowledge.md", profile_with(KnowledgePoint("列表", "学过", "e")))
    board = TaskBoard(directory)

    assert board.run_action("status", {"name": "列表", "level": "输出", "note": "x"}).ok
    # 但多给别的键仍要被拒
    assert not board.run_action("status", {"name": "列表", "level": "学过", "cmd": "whoami"}).ok

# --- 7. 回归：done 不得把高状态降级（实测发现的真 bug） ----------------------


def test_done_without_recite_does_not_downgrade_output():
    """实测：知识点已是「输出」，再跑一次不带 --recite 的 done，被降回「做过」。

    done 的语义是"记录产出"，不是"改状态"；它只该升，不该降。
    """
    profile = profile_with(KnowledgePoint("列表", "输出", "复述：列表是有序容器"))

    updated = mark_done(profile, "列表", "out.py")

    assert updated.points[0].level == "输出"


def test_done_still_upgrades_learned_to_done():
    profile = profile_with(KnowledgePoint("列表", "学过", "e"))

    updated = mark_done(profile, "列表", "out.py")

    assert updated.points[0].level == "做过"


def test_done_can_pull_unsure_lowest_case():
    """存疑 rank 最低，done 后应升到「做过」（存疑不是"要保护"的高状态）。"""
    profile = profile_with(KnowledgePoint("列表", "存疑", "只提了一句"))

    updated = mark_done(profile, "列表", "out.py")

    assert updated.points[0].level == "做过"


def test_repeated_done_with_recite_keeps_output():
    profile = profile_with(KnowledgePoint("列表", "学过", "e"))
    once = mark_done(profile, "列表", "out.py", recite="我的复述")
    again = mark_done(once, "列表", "out.py", recite="我的复述")

    assert again.points[0].level == "输出"
    assert again.points[0].evidence.count("我的复述") == 1


def test_set_level_still_allows_explicit_downgrade():
    """手工改状态是显式意图，仍可下调（与 done 的"只升不降"不同）。"""
    profile = profile_with(KnowledgePoint("列表", "输出", "e"))

    updated = set_level(profile, "列表", "学过")

    assert updated.points[0].level == "学过"