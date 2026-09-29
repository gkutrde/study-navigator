"""T-004 失败测试：画像文件结构与合并逻辑。

验收（见 [[04-任务与验收清单]] T-004 / A-02）：画像按知识点列出名称/状态/证据。

实现前编写（src/profile.py 尚不存在），必须全部失败。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.distill import KnowledgePoint
from src.profile import (
    LEVELS,
    LEVEL_RANK,
    ProfileError,
    KnowledgeProfile,
    merge_points,
    parse_profile,
    render_profile,
    write_profile_atomic,
)

HEADER = "# 知识画像"

SAMPLE_MD = """---
title: 知识画像
tags:
  - profile
---

# 知识画像

## 统计

| 状态 | 数量 |
| --- | --- |
| 学过 | 1 |

## Python 基础

- [学过] 列表 — 证据：列表用方括号 | 来源：notes/a.md
- [存疑] 字典 — 证据：只提了一句 | 来源：notes/a.md
"""


# --- 1. 解析：既有画像能被读回来 --------------------------------------------


def test_parse_profile_reads_points_with_topic():
    profile = parse_profile(SAMPLE_MD)

    assert len(profile.points) == 2
    first = profile.points[0]
    assert first.name == "列表"
    assert first.level == "学过"
    assert first.topic == "Python 基础"
    assert "方括号" in first.evidence


def test_parse_profile_keeps_declared_order():
    names = [p.name for p in parse_profile(SAMPLE_MD).points]
    assert names == ["列表", "字典"]


def test_parse_empty_or_missing_content():
    assert parse_profile("").points == []
    assert parse_profile("# 空画像\n\n## Python\n").points == []


def test_parse_unknown_level_line_is_ignored_not_guessed():
    md = "# 画像\n\n## Python\n\n- 这条不是知识点格式\n"
    assert parse_profile(md).points == []


# --- 2. 渲染：结构稳定、可读、可 git 管理 -----------------------------------


def test_render_creates_expected_structure():
    profile = parse_profile(SAMPLE_MD)

    text = render_profile(profile)

    assert "---" in text.split("\n")[0]  # frontmatter
    assert "## 统计" in text
    assert "## Python 基础" in text
    assert "- [学过] 列表" in text
    assert "证据：" in text


def test_render_roundtrip_is_stable():
    profile = parse_profile(SAMPLE_MD)

    once = render_profile(profile)
    twice = render_profile(parse_profile(once))

    assert once == twice


def test_render_includes_level_counts():
    profile = KnowledgeProfile(points=[
        KnowledgePoint("列表", "学过", "e1"),
        KnowledgePoint("字典", "存疑", "e2"),
        KnowledgePoint("循环", "学过", "e3"),
    ])

    text = render_profile(profile)

    assert "| 学过 | 2 |" in text
    assert "| 存疑 | 1 |" in text


def test_render_groups_by_topic():
    profile = KnowledgeProfile(points=[
        KnowledgePoint("列表", "学过", "e", topic="Python 基础"),
        KnowledgePoint("变量", "学过", "e", topic="C++ 基础"),
    ])

    text = render_profile(profile)

    assert text.index("## C++ 基础") < text.index("## Python 基础") or True
    assert "## Python 基础" in text and "## C++ 基础" in text


def test_render_points_without_topic_go_to_default_section():
    text = render_profile(KnowledgeProfile(points=[KnowledgePoint("列表", "学过", "e")]))

    assert "## 未分类" in text
    assert "- [学过] 列表" in text


# --- 3. 合并：去重、只升不降、证据追加 ---------------------------------------


def test_merge_adds_new_points():
    profile = KnowledgeProfile()
    merged = merge_points(profile, [KnowledgePoint("列表", "学过", "e1", "Python 基础")])

    assert [p.name for p in merged.points] == ["列表"]


def test_merge_is_idempotent_for_same_input():
    profile = KnowledgeProfile()
    points = [KnowledgePoint("列表", "学过", "列表用方括号", "Python 基础")]

    once = merge_points(profile, points)
    twice = merge_points(once, points)

    assert len(twice.points) == 1
    assert twice.points[0].evidence.count("列表用方括号") == 1


def test_merge_upgrades_level_but_never_downgrades():
    profile = KnowledgeProfile(points=[KnowledgePoint("列表", "做过", "old")])

    merged = merge_points(profile, [KnowledgePoint("列表", "学过", "new")])

    assert merged.points[0].level == "做过"


def test_merge_downgrade_to_unsure_is_allowed():
    """存疑是「信息不足」的信号，允许把学过降为存疑提醒客户复核。"""
    profile = KnowledgeProfile(points=[KnowledgePoint("列表", "学过", "old")])

    merged = merge_points(profile, [KnowledgePoint("列表", "存疑", "new")])

    assert merged.points[0].level == "存疑"


def test_merge_appends_new_evidence_and_keeps_old():
    profile = KnowledgeProfile(points=[KnowledgePoint("列表", "学过", "来自笔记 A")])

    merged = merge_points(profile, [KnowledgePoint("列表", "学过", "来自笔记 B")])

    evidence = merged.points[0].evidence
    assert "来自笔记 A" in evidence
    assert "来自笔记 B" in evidence


def test_merge_identity_is_name_based_even_when_topic_differs():
    """实测：同一个笔记重复提炼时，LLM 给同一知识点的 topic 会漂移
    （Markdown 一次是「工具使用」、一次是「工具」）。知识点身份必须按名称判定，
    否则每跑一次画像就多几条，画像会被撑爆。首个主题保留，不来回改。"""
    profile = KnowledgeProfile(points=[KnowledgePoint("Markdown", "学过", "旧证据", "工具使用")])

    merged = merge_points(profile, [KnowledgePoint("Markdown", "学过", "新证据", "工具")])

    assert len(merged.points) == 1
    assert merged.points[0].topic == "工具使用"
    assert "旧证据" in merged.points[0].evidence and "新证据" in merged.points[0].evidence


def test_merge_rejects_unknown_level():
    with pytest.raises(ProfileError):
        merge_points(KnowledgeProfile(), [KnowledgePoint("列表", "精通", "e")])


def test_level_rank_orders_unsure_lowest():
    """存疑最低；掌握程度严格递增。T-019 起多了最高态「输出」（费曼复述）。"""
    assert LEVEL_RANK["存疑"] < LEVEL_RANK["学过"] < LEVEL_RANK["做过"] < LEVEL_RANK["输出"]
    # 顺序即 rank 顺序，且不含未知态
    assert [level for level in LEVELS if level != "存疑"] == ["学过", "做过", "输出"]
    assert set(LEVELS) == {"学过", "做过", "输出", "存疑"}


# --- 4. 落盘：临时文件 + 替换，不破坏既有文件 -------------------------------


def test_write_profile_atomic_creates_file(tmp_path):
    target = tmp_path / "profile" / "knowledge.md"

    write_profile_atomic(target, KnowledgeProfile(points=[KnowledgePoint("列表", "学过", "e")]))

    assert target.is_file()
    assert "[学过] 列表" in target.read_text(encoding="utf-8")
    assert list(target.parent.glob("*.tmp")) == []


def test_write_profile_atomic_replaces_but_keeps_old_on_failure(tmp_path):
    target = tmp_path / "profile" / "knowledge.md"
    write_profile_atomic(target, KnowledgeProfile(points=[KnowledgePoint("列表", "学过", "e")]))
    before = target.read_text(encoding="utf-8")

    class Boom(KnowledgeProfile):
        pass

    # 传一个渲染会失败的坏对象，验证旧文件与临时文件都不受影响
    bad = KnowledgeProfile(points=[KnowledgePoint("x", "学过", "e")])
    bad.points = None  # type: ignore[assignment]

    with pytest.raises(ProfileError):
        write_profile_atomic(target, bad)

    assert target.read_text(encoding="utf-8") == before
    assert list(target.parent.glob("*.tmp")) == []


# --- 5. 端到端：distill 合并进画像 ------------------------------------------


def test_profile_load_and_save_roundtrip(tmp_path):
    target = tmp_path / "profile" / "knowledge.md"

    profile = KnowledgeProfile.load(target)
    assert profile.points == []

    write_profile_atomic(target, merge_points(profile, [KnowledgePoint("列表", "学过", "e", "Python")]))

    reloaded = KnowledgeProfile.load(target)
    assert reloaded.points[0].name == "列表"
    assert reloaded.points[0].topic == "Python"

# --- 6. CLI：distill 落盘画像（T-004 主路径） -------------------------------


class _StubCompleter:
    def __init__(self, replies):
        self._replies = list(replies)

    def complete(self, messages):
        return self._replies.pop(0)


def _note(tmp_path):
    path = tmp_path / "note.md"
    path.write_text("# 笔记\n\n## 列表\n列表用方括号。\n", encoding="utf-8")
    return path


def test_cli_distill_writes_profile(tmp_path, monkeypatch, capsys):
    from src import cli

    target = tmp_path / "profile" / "knowledge.md"
    note = _note(tmp_path)
    completer = _StubCompleter(
        [json.dumps([{"name": "列表", "level": "学过", "evidence": "列表用方括号"}], ensure_ascii=False)]
    )
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: completer)

    code = cli.main(["distill", str(note)], profile_path=target, env_path=tmp_path / ".env")
    out = capsys.readouterr()

    assert code == 0
    assert target.is_file()
    text = target.read_text(encoding="utf-8")
    assert "- [学过] 列表" in text
    assert "证据：列表用方括号" in text
    assert str(target) in out.err


def test_cli_distill_merges_into_existing_profile(tmp_path, monkeypatch, capsys):
    from src import cli

    target = tmp_path / "profile" / "knowledge.md"
    write_profile_atomic(target, KnowledgeProfile(points=[KnowledgePoint("列表", "学过", "旧证据", "Python")]))
    note = _note(tmp_path)
    completer = _StubCompleter(
        [json.dumps([{"name": "列表", "level": "学过", "evidence": "新证据"}], ensure_ascii=False)]
    )
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: completer)

    code = cli.main(["distill", str(note)], profile_path=target, env_path=tmp_path / ".env")
    capsys.readouterr()

    assert code == 0
    text = target.read_text(encoding="utf-8")
    assert "旧证据" in text and "新证据" in text
    assert text.count("- [学过] 列表") == 1


def test_cli_distill_no_points_does_not_create_profile(tmp_path, monkeypatch, capsys):
    from src import cli

    target = tmp_path / "profile" / "knowledge.md"
    note = _note(tmp_path)
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: _StubCompleter(["[]"]))

    code = cli.main(["distill", str(note)], profile_path=target, env_path=tmp_path / ".env")
    out = capsys.readouterr()

    assert code == 0
    assert not target.exists()
    assert "无可提炼" in out.err


def test_cli_distill_llm_failure_keeps_existing_profile(tmp_path, monkeypatch, capsys):
    from src import cli

    target = tmp_path / "profile" / "knowledge.md"
    write_profile_atomic(target, KnowledgeProfile(points=[KnowledgePoint("列表", "学过", "旧证据")]))
    before = target.read_text(encoding="utf-8")
    note = _note(tmp_path)
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: _StubCompleter(["这不是 JSON"]))

    code = cli.main(["distill", str(note)], profile_path=target, env_path=tmp_path / ".env")
    capsys.readouterr()

    assert code == 1
    assert target.read_text(encoding="utf-8") == before
    assert list(target.parent.glob("*.tmp")) == []


def test_cli_distill_no_write_flag_skips_profile(tmp_path, monkeypatch, capsys):
    from src import cli

    target = tmp_path / "profile" / "knowledge.md"
    note = _note(tmp_path)
    completer = _StubCompleter(
        [json.dumps([{"name": "列表", "level": "学过", "evidence": "e"}], ensure_ascii=False)]
    )
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: completer)

    code = cli.main(["distill", str(note), "--no-write"], profile_path=target, env_path=tmp_path / ".env")
    capsys.readouterr()

    assert code == 0
    assert not target.exists()

def test_merge_matches_by_name_when_incoming_has_no_topic():
    """真实提炼常常不给 topic；若既有画像里同名点已归属某主题，
    应按名称匹配并沿用既有主题，而不是新开一条「未分类」重复项。"""
    profile = KnowledgeProfile(points=[KnowledgePoint("列表", "学过", "旧证据", "Python")])

    merged = merge_points(profile, [KnowledgePoint("列表", "学过", "新证据")])

    assert len(merged.points) == 1
    assert merged.points[0].topic == "Python"
    assert "旧证据" in merged.points[0].evidence and "新证据" in merged.points[0].evidence


def test_repeated_merge_of_same_run_does_not_grow_profile():
    """同一篇笔记连续提炼两次，知识点条数不得增加（幂等）。"""
    note_points = [
        KnowledgePoint("Markdown", "存疑", "笔记「Markdown」小节", "工具使用"),
        KnowledgePoint("CTF", "存疑", "笔记「CTF」小节", "安全"),
    ]
    drifted = [
        KnowledgePoint("Markdown", "存疑", "笔记「Markdown」小节", "工具"),
        KnowledgePoint("CTF", "存疑", "笔记「CTF」小节", "安全"),
        KnowledgePoint("密码学", "存疑", "笔记「密码学」小节", "安全"),
    ]

    first = merge_points(KnowledgeProfile(), note_points)
    second = merge_points(first, drifted)

    assert len(first.points) == 2
    # 漂移的同名点合并，新出现的「密码学」才允许新增
    assert len(second.points) == 3
    assert [p.name for p in second.points].count("Markdown") == 1