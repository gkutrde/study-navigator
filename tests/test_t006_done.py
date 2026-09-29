"""T-006 失败测试：done 命令（回写画像：状态升「做过」+ 记录产出路径）。

验收（[[04-任务与验收清单]] T-006 / A-04）：done 后状态变「做过」且附产出路径；
写文件先临时后替换（复用 T-004 的原子落盘）。

实现前编写（mark_done 尚不存在），必须全部失败。
"""

from __future__ import annotations

import pytest

from src.distill import KnowledgePoint
from src.profile import KnowledgeProfile, ProfileError, write_profile_atomic


def profile_with(*points):
    return KnowledgeProfile(points=list(points))


def make(tmp_path, *points, name="knowledge.md"):
    target = tmp_path / "profile" / name
    write_profile_atomic(target, profile_with(*points))
    return target


# --- 1. 标记「做过」 ---------------------------------------------------------


def test_mark_done_upgrades_learned_to_done():
    from src.profile import mark_done

    profile = profile_with(KnowledgePoint("列表", "学过", "来自笔记"))
    result = mark_done(profile, "列表", "tasks/reverse_list.py")

    assert result.points[0].level == "做过"
    assert "tasks/reverse_list.py" in result.points[0].evidence


def test_mark_done_keeps_existing_evidence():
    from src.profile import mark_done

    profile = profile_with(KnowledgePoint("列表", "学过", "来自笔记 A"))
    result = mark_done(profile, "列表", "out.py")

    assert "来自笔记 A" in result.points[0].evidence
    assert "out.py" in result.points[0].evidence


def test_mark_done_works_from_unsure():
    from src.profile import mark_done

    profile = profile_with(KnowledgePoint("列表", "存疑", "只提了一句"))
    assert mark_done(profile, "列表", "out.py").points[0].level == "做过"


def test_mark_done_is_idempotent_on_evidence():
    from src.profile import mark_done

    profile = profile_with(KnowledgePoint("列表", "学过", "来自笔记"))
    once = mark_done(profile, "列表", "out.py")
    twice = mark_done(once, "列表", "out.py")

    assert twice.points[0].evidence.count("out.py") == 1
    assert twice.points[0].level == "做过"


def test_mark_done_matches_name_with_topic_suffix():
    """客户可能照抄画像里的「列表（Python 基础）」来调用。"""
    from src.profile import mark_done

    profile = profile_with(KnowledgePoint("列表", "学过", "e", "Python 基础"))
    result = mark_done(profile, "列表（Python 基础）", "out.py")

    assert result.points[0].level == "做过"
    assert result.points[0].name == "列表"


def test_mark_done_unknown_point_creates_new_entry():
    """T-023 L-01 起：画像里没有的点**新增条目**，而不是报错。

    旧行为（报错并列出候选）会让核心闭环断裂——出题/讲解里遇到的新点根本没法回写。
    """
    from src.profile import mark_done

    profile = profile_with(KnowledgePoint("列表", "学过", "e"), KnowledgePoint("字典", "学过", "e"))

    updated = mark_done(profile, "并发编程", "out.py")

    assert [p.name for p in updated.points] == ["列表", "字典", "并发编程"]
    new_point = updated.points[-1]
    assert new_point.level == "做过"
    assert "out.py" in new_point.evidence


def test_mark_done_requires_product_path():
    from src.profile import mark_done

    profile = profile_with(KnowledgePoint("列表", "学过", "e"))

    with pytest.raises(ProfileError):
        mark_done(profile, "列表", "   ")


def test_mark_done_does_not_touch_other_points():
    from src.profile import mark_done

    profile = profile_with(
        KnowledgePoint("列表", "学过", "e1"), KnowledgePoint("字典", "存疑", "e2")
    )
    result = mark_done(profile, "列表", "out.py")

    assert result.points[1].level == "存疑"
    assert "out.py" not in result.points[1].evidence


# --- 2. CLI -----------------------------------------------------------------


def test_cli_done_updates_profile_and_prints_summary(tmp_path, monkeypatch, capsys):
    from src import cli

    target = make(tmp_path, KnowledgePoint("列表", "学过", "来自笔记"))
    code = cli.main(["done", "列表", "tasks/reverse_list.py"], profile_path=target)
    out = capsys.readouterr()

    assert code == 0
    reloaded = KnowledgeProfile.load(target)
    assert reloaded.points[0].level == "做过"
    assert "tasks/reverse_list.py" in reloaded.points[0].evidence
    assert "列表" in out.out + out.err


def test_cli_done_missing_args_exits_2(tmp_path, capsys):
    from src import cli

    target = make(tmp_path, KnowledgePoint("列表", "学过", "e"))
    code = cli.main(["done", "列表"], profile_path=target)
    out = capsys.readouterr()

    assert code == 2
    assert "产出" in out.err or "用法" in out.err


def test_cli_done_unknown_point_creates_entry(tmp_path, capsys):
    """T-023 L-01 起：CLI 里 done 一个画像没有的点也应成功新增。"""
    from src import cli
    from src.profile import KnowledgeProfile

    target = make(tmp_path, KnowledgePoint("列表", "学过", "e"))

    code = cli.main(["done", "并发编程", "out.py"], profile_path=target)
    out = capsys.readouterr()

    assert code == 0, out.err
    reloaded = KnowledgeProfile.load(target)
    assert any(p.name == "并发编程" for p in reloaded.points)
    assert "并发编程" in out.err


def test_cli_done_missing_profile_exits_1(tmp_path, capsys):
    from src import cli

    code = cli.main(["done", "列表", "out.py"], profile_path=tmp_path / "profile" / "knowledge.md")
    out = capsys.readouterr()

    assert code == 1
    assert "画像" in out.err


def test_cli_done_failure_leaves_no_tmp_file(tmp_path, capsys):
    from src import cli

    target = make(tmp_path, KnowledgePoint("列表", "学过", "e"))
    cli.main(["done", "并发编程", "out.py"], profile_path=target)
    capsys.readouterr()

    assert list(target.parent.glob("*.tmp")) == []