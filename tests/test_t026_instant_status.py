"""T-026 失败测试：状态切换即时化（渐进增强）。

客户要求：改状态不要保存按钮、不要跳回顶部。

实现要求：
- chips/下拉 onchange 即 fetch POST /action/status，**原地更新**该条目样式与顶部统计，
  页面不刷新不滚动；
- 状态表单里的 产出路径/复述/说明 输入框**移出**（那些归 M-01 的回写表单管）；
- **无 JS 时保留提交按钮兜底**（渐进增强，沿用 PANEL_JS 思路）；
- **失败时原地红字提示，不改界面状态**。

验收：点 chip 后 300ms 内该条目变色且统计数字更新，滚动位置不变；断网/失败时提示且不跳变。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.dashboard import Dashboard, TaskBoard
from src.distill import KnowledgePoint
from src.profile import KnowledgeProfile, write_profile_atomic


def make_board(tmp_path, *pairs):
    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    write_profile_atomic(
        directory / "knowledge.md",
        KnowledgeProfile(points=[KnowledgePoint(n, lv, "e") for n, lv in pairs]),
    )
    return directory, TaskBoard(directory)


def make_dashboard(tmp_path, *pairs):
    """HTTP 层在 Dashboard 上（TaskBoard 只管动作）。"""
    directory, board = make_board(tmp_path, *pairs)
    return directory, Dashboard(directory, board=board)


# ---------- 1. 表单精简：状态表单不再管产出路径/复述/说明 ----------


def test_status_form_only_has_level_control(tmp_path):
    directory, board = make_board(tmp_path, ("列表", "学过"))

    page = board.pages()["knowledge"]

    match = re.search(r'<form[^>]*action="/action/status"[^>]*>(?P<body>.*?)</form>', page, re.S)
    assert match, "要有 status 表单兜底"
    fields = set(re.findall(r'name="([^"]+)"', match.group("body")))
    assert fields == {"name", "level"}, f"状态表单只该有 name/level，实际 {fields}"


def test_status_form_control_is_a_select(tmp_path):
    """下拉用 onchange 触发；没有 JS 时还有提交按钮。"""
    directory, board = make_board(tmp_path, ("列表", "学过"))

    page = board.pages()["knowledge"]

    match = re.search(r'<form[^>]*action="/action/status"[^>]*>(?P<body>.*?)</form>', page, re.S)
    body = match.group("body")
    assert "<select" in body and 'name="level"' in body
    assert "<button" in body, "无 JS 时必须还能提交"


def test_status_form_has_no_text_inputs(tmp_path):
    directory, board = make_board(tmp_path, ("列表", "学过"))

    page = board.pages()["knowledge"]

    match = re.search(r'<form[^>]*action="/action/status"[^>]*>(?P<body>.*?)</form>', page, re.S)
    body = match.group("body")
    assert 'type="text"' not in body, "产出路径/复述/说明 应归回写表单管"


# ---------- 2. 原地更新所需的钩子 ----------


def test_point_card_has_stable_hook(tmp_path):
    """JS 要能定位「这个条目」并原地改样式，所以卡片要有 data 钩子。"""
    directory, board = make_board(tmp_path, ("列表", "学过"))

    page = board.pages()["knowledge"]

    assert "data-point=" in page
    assert "data-level=" in page


def test_stats_have_stable_hook(tmp_path):
    directory, board = make_board(tmp_path, ("列表", "学过"))

    page = board.pages()["knowledge"]

    assert 'data-stat="' in page


def test_panel_js_does_inline_fetch(tmp_path):
    """PANEL_JS 里要有原地提交逻辑，且只打固定动作路由。"""
    directory, board = make_board(tmp_path, ("列表", "学过"))

    page = board.pages()["knowledge"]

    assert "fetch(" in page
    assert "/action/status" in page
    assert "preventDefault" in page
    assert "location.reload" not in page, "不该整页刷新"


def test_js_failure_shows_inline_message(tmp_path):
    directory, board = make_board(tmp_path, ("列表", "学过"))

    page = board.pages()["knowledge"]

    assert "result-err" in page or "inline-error" in page, "失败要有原地提示的样式/容器"


# ---------- 3. JSON 响应：JS 用它原地更新 ----------


def test_status_accepts_json_request(tmp_path):
    directory, dash = make_dashboard(tmp_path, ("列表", "学过"))

    status, content_type, body = dash.handle_request(
        "POST", "/action/status",
        body=json.dumps({"name": "列表", "level": "做过"}).encode("utf-8"),
        content_type="application/json",
    )

    assert status == 200
    assert "json" in content_type
    payload = json.loads(body)
    assert payload["ok"] is True


def test_status_json_reports_new_level_and_counts(tmp_path):
    directory, dash = make_dashboard(tmp_path, ("列表", "学过"), ("字典", "存疑"))

    _status, _ct, body = dash.handle_request(
        "POST", "/action/status",
        body=json.dumps({"name": "列表", "level": "输出"}).encode("utf-8"),
        content_type="application/json",
    )
    payload = json.loads(body)

    assert payload["point"] == "列表"
    assert payload["level"] == "输出"
    assert payload["counts"]["输出"] == 1
    assert payload["counts"]["学过"] == 0


def test_status_json_persists_to_profile(tmp_path):
    directory, dash = make_dashboard(tmp_path, ("列表", "学过"))

    dash.handle_request(
        "POST", "/action/status",
        body=json.dumps({"name": "列表", "level": "做过"}).encode("utf-8"),
        content_type="application/json",
    )

    assert KnowledgeProfile.load(directory / "knowledge.md").points[0].level == "做过"


def test_status_json_failure_returns_400_and_message(tmp_path):
    """失败时返回 400 + 可读消息；画像不变（前端据此原地红字提示，不改界面状态）。"""
    directory, dash = make_dashboard(tmp_path, ("列表", "学过"))
    before = (directory / "knowledge.md").read_bytes()

    status, _ct, body = dash.handle_request(
        "POST", "/action/status",
        body=json.dumps({"name": "列表", "level": "精通"}).encode("utf-8"),
        content_type="application/json",
    )

    assert status == 400
    payload = json.loads(body)
    assert payload["ok"] is False
    assert "状态" in payload["message"] or "不合法" in payload["message"]
    assert (directory / "knowledge.md").read_bytes() == before


def test_status_json_rejects_extra_keys(tmp_path):
    """白名单仍然生效：多给键一律拒绝。"""
    directory, dash = make_dashboard(tmp_path, ("列表", "学过"))

    status, _ct, _body = dash.handle_request(
        "POST", "/action/status",
        body=json.dumps({"name": "列表", "level": "学过", "cmd": "whoami"}).encode("utf-8"),
        content_type="application/json",
    )

    assert status == 400


# ---------- 4. 渐进增强：无 JS 时表单仍可用（303 回跳） ----------


def test_form_post_still_redirects_without_js(tmp_path):
    directory, dash = make_dashboard(tmp_path, ("列表", "学过"))

    status, _ct, _body = dash.handle_request(
        "POST", "/action/status", body=b"name=%E5%88%97%E8%A1%A8&level=%E5%81%9A%E8%BF%87",
        content_type="application/x-www-form-urlencoded",
    )

    assert status == 303


def test_status_still_escapes_html(tmp_path):
    directory = tmp_path / "profile"
    directory.mkdir(parents=True)
    (directory / "knowledge.md").write_text(
        "# 知识画像\n\n## 主题\n\n- [学过] <script>alert(1)</script> — 证据：x\n", encoding="utf-8"
    )
    board = TaskBoard(directory)

    page = board.pages()["knowledge"]

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page

# ---------- 5. chip 必须保留（任务卡验收标准写的是"点 chip"） ----------


def test_point_card_still_has_level_chips(tmp_path):
    """T-026 的实现曾把 chips 一并删掉，但验收标准是「点 **chip** 后 300ms 内变色」。

    chips 是"点一下即改"的快捷方式；下拉作为无 JS 兜底与精确选择保留。
    """
    directory, board = make_board(tmp_path, ("列表", "学过"))

    page = board.pages()["knowledge"]

    assert 'class="chip' in page, "chips 必须还在（按 class 前缀匹配，因为它还带 js-only）"
    for level in ("学过", "做过", "输出", "存疑"):
        assert f'class="chip js-only" data-level="{level}"' in page or f'data-level="{level}"' in page


def test_chips_are_marked_as_js_enhancement(tmp_path):
    """chips 是 JS 增强：无 JS 时应隐藏（那时靠下拉 + 按钮）。"""
    directory, board = make_board(tmp_path, ("列表", "学过"))

    page = board.pages()["knowledge"]

    assert "js-only" in page, "chips 要有 js-only 标记（无 JS 时不可见）"


def test_panel_js_binds_chips_to_inline_submit(tmp_path):
    """PANEL_JS 里的 .chip 绑定不能是死代码——页面上必须有对应元素。"""
    import re

    directory, board = make_board(tmp_path, ("列表", "学过"))

    page = board.pages()["knowledge"]

    assert ".chip" in page, "JS 里绑定 .chip，页面就得有 .chip"
    assert re.search(r'class="chip[ "]', page)