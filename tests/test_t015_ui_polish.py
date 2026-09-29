"""T-015 失败测试：看板 UI 美化。

验收（[[04-任务与验收清单]] T-015）：

- 卡片式布局、知识点按 学过/做过/存疑 色彩区分、任务卡片、响应式；
- **内联 CSS + 原生 JS**，不引 CDN、零新运行时依赖；
- localhost 与固定动作集约束不变（既有 283 项测试保持全绿）。

首轮按"客户目检"验收，测试只能锁定可机检的部分（色彩/响应式/无外链/行为不变）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.dashboard import Dashboard, TaskBoard, build_server
from src.distill import KnowledgePoint
from src.profile import KnowledgeProfile, write_profile_atomic


def make_board(tmp_path):
    directory = tmp_path / "profile"
    write_profile_atomic(
        directory / "knowledge.md",
        KnowledgeProfile(points=[
            KnowledgePoint("列表", "学过", "笔记：列表用方括号", "Python 基础"),
            KnowledgePoint("字典", "做过", "产出：out.py", "Python 基础"),
            KnowledgePoint("装饰器", "存疑", "只提了一句", "Python 基础"),
        ]),
    )
    (directory / "tasks.md").write_text(
        "# 任务记录\n\n## 2026-09-26 10:00\n\n## 下一步任务\n\n**目标**：写通讯录\n\n**验收方式**：能存盘\n",
        encoding="utf-8",
    )
    return directory, TaskBoard(directory)


# --- 1. 卡片式布局与响应式 -------------------------------------------------


def test_page_uses_card_layout(tmp_path):
    _, tb = make_board(tmp_path)

    page = tb.pages()[""]

    assert "border-radius" in page
    assert "card" in page
    assert "<style>" in page


def test_page_is_responsive(tmp_path):
    _, tb = make_board(tmp_path)

    page = tb.pages()[""]

    assert "@media" in page
    assert "grid-template-columns" in page or "flex" in page


def test_page_has_no_external_resources(tmp_path):
    """零外部依赖：不引 CDN、不外链字体/图标/脚本。"""
    _, tb = make_board(tmp_path)

    page = tb.pages()[""]

    assert "http://" not in page.replace("http://127.0.0.1", "")
    assert "https://" not in page
    assert "<script src" not in page
    assert "<link" not in page


# --- 2. 三态色彩区分 -------------------------------------------------------


@pytest.mark.parametrize("level", ["学过", "做过", "存疑"])
def test_each_level_has_its_own_color_style(tmp_path, level):
    _, tb = make_board(tmp_path)

    page = tb.pages()[""]

    assert f"level-{level}" in page
    assert f".level-{level}" in page


def test_level_styles_use_distinct_colors(tmp_path):
    _, tb = make_board(tmp_path)
    page = tb.pages()[""]

    colors = {
        level: re.search(rf"\.level-{level}\s*\{{[^}}]*?(#[0-9a-fA-F]{{3,6}})", page)
        for level in ("学过", "做过", "存疑")
    }
    found = {level: (m.group(1).lower() if m else None) for level, m in colors.items()}
    assert all(found.values()), found
    assert len(set(found.values())) == 3, found


def test_points_render_as_cards_with_level_class(tmp_path):
    _, tb = make_board(tmp_path)

    page = tb.pages()["knowledge"]

    assert page.count('class="point') >= 3
    assert 'class="level level-做过"' in page or "level level-做过" in page


# --- 3. 任务卡片 -----------------------------------------------------------


def test_tasks_render_as_cards(tmp_path):
    _, tb = make_board(tmp_path)

    page = tb.pages()[""]

    assert 'class="task-card"' in page or "task-card" in page
    assert "写通讯录" in page


# --- 4. 原生 JS 只做渐进增强，不越界 ---------------------------------------


def test_uses_inline_vanilla_js_without_framework(tmp_path):
    _, tb = make_board(tmp_path)

    page = tb.pages()[""]

    assert "<script>" in page
    assert "addEventListener" in page
    for banned in ("react", "vue", "jquery", "cdn", "unpkg", "jsdelivr"):
        assert banned not in page.lower()


def test_js_does_not_introduce_free_command_entry(tmp_path):
    """美化不能把边界改掉：仍然没有任意命令输入框。"""
    _, tb = make_board(tmp_path)

    page = tb.pages()[""]

    assert 'name="cmd"' not in page
    assert 'name="command"' not in page
    assert "eval(" not in page
    assert "fetch(" not in page or "/action/" in page  # 若用了 fetch，也必须打到固定动作路由


def test_js_only_targets_fixed_actions(tmp_path):
    _, tb = make_board(tmp_path)

    page = tb.pages()[""]

    for action in ("sync", "distill", "next", "done", "status"):
        assert f"/action/{action}" in page


# --- 5. 边界与既有行为不变 -------------------------------------------------


def test_action_forms_still_fixed_set_only(tmp_path):
    _, tb = make_board(tmp_path)

    page = tb.pages()[""]

    from src.dashboard import ACTION_PARAM_KEYS

    found = set(re.findall(r'action="/action/([a-z_]+)"', page))
    # 页面上的动作必须都在入参白名单内（不能出现白名单外的动作）
    assert found <= set(ACTION_PARAM_KEYS)


def test_status_still_offers_exactly_three_levels(tmp_path):
    _, tb = make_board(tmp_path)

    page = tb.pages()["knowledge"]

    for level in ("学过", "做过", "存疑"):
        assert f'value="{level}"' in page


def test_unknown_action_still_rejected(tmp_path):
    directory, tb = make_board(tmp_path)
    dash = Dashboard(directory, board=tb)

    status, _, _ = dash.handle_action("rm_everything", {})

    assert status == 400


def test_dashboard_still_bound_to_localhost(tmp_path):
    directory, tb = make_board(tmp_path)
    server = build_server(directory, port=0, board=tb)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_page_still_escapes_profile_content(tmp_path):
    """美化不能放松转义：画像里的 HTML 必须被转义。"""
    directory = tmp_path / "profile"
    directory.mkdir(parents=True)
    (directory / "knowledge.md").write_text(
        "# 知识画像\n\n## 主题\n\n- [学过] <script>alert(1)</script> — 证据：x\n", encoding="utf-8"
    )
    tb = TaskBoard(directory)

    page = tb.pages()["knowledge"]

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page