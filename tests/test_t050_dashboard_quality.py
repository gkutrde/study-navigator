"""T-050 看板：请求来源校验（新加的安全收口）+ 优化中修掉的问题。

1. 请求来源校验：Host 必须是本机回环名（挡 DNS rebinding），写请求带了 Origin/Referer
   就必须同源（挡别的网站用表单偷偷触发 chat / done / delete_task）；
2. 请求体上限与畸形 Content-Length；
3. 行内代码从来没渲染过（"\\1" 写在普通字符串里变成了 \\x01）；
4. 面板就地回答与刷新后的历史用同一个 markdown 渲染器（JSON 里带 html）；
5. 每张卡片的聊天面板不再共用 id="chat-panel"；
6. 动作结果只留最近一条（以前整段会话只增不减）。

安全边界不变：固定动作集、入参白名单、文件端点白名单都原样保留；这里只是**多一道**来源校验，
不是登录鉴权（01「明确不做」里的「不做登录鉴权」保持）。
"""

from __future__ import annotations

import http.client
import json
import threading
from urllib.parse import urlencode

import pytest

from src.dashboard import (
    MAX_REQUEST_BYTES,
    Dashboard,
    TaskBoard,
    build_server,
    markdown_to_html,
    request_guard,
)
from src.distill import KnowledgePoint
from src.profile import KnowledgeProfile, write_profile_atomic


# ---------------------------------------------------------------- request_guard（纯函数）


@pytest.mark.parametrize("host", ["127.0.0.1:8765", "localhost:8765", "[::1]:8765", "127.0.0.1", ""])
def test_guard_allows_loopback_hosts(host):
    assert request_guard("GET", host=host) is None


@pytest.mark.parametrize("host", ["evil.example:8765", "192.168.1.5:8765", "127.0.0.1.evil.example", "bad:port"])
def test_guard_rejects_foreign_host_even_for_get(host):
    """DNS rebinding：攻击者域名解析到 127.0.0.1 时，Host 头是攻击者的域名。"""
    assert request_guard("GET", host=host)


def test_guard_allows_same_origin_post():
    assert request_guard("POST", host="127.0.0.1:8765", origin="http://127.0.0.1:8765") is None
    assert request_guard("POST", host="localhost:8765", referer="http://localhost:8765/tasks#task-1") is None


def test_guard_allows_post_without_origin_or_referer():
    """命令行工具与测试不带 Origin；浏览器发跨站 POST 一定带 Origin。"""
    assert request_guard("POST", host="127.0.0.1:8765") is None


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example",
        "http://127.0.0.1:9999",  # 本机别的端口上的页面也不行
        "http://localhost:8765",  # 主机名写法不同 = 不同源
        "null",  # 沙箱 iframe / file:// 页面
    ],
)
def test_guard_rejects_cross_site_post(origin):
    assert request_guard("POST", host="127.0.0.1:8765", origin=origin)


def test_guard_checks_referer_when_origin_missing():
    assert request_guard("POST", host="127.0.0.1:8765", referer="https://evil.example/page")


# ---------------------------------------------------------------- 真 HTTP


@pytest.fixture()
def served(tmp_path):
    directory = tmp_path / "profile"
    directory.mkdir()
    write_profile_atomic(directory / "knowledge.md", KnowledgeProfile(points=[KnowledgePoint("字典", "存疑", "e")]))
    board = TaskBoard(directory)
    server = build_server(directory, port=0, board=board)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield directory, server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def _request(port, method, path, *, body=b"", headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        return response.status, response.read().decode("utf-8", "replace")
    finally:
        conn.close()


def test_cross_site_form_post_is_rejected_and_changes_nothing(served):
    directory, port = served
    body = urlencode({"name": "字典", "level": "做过"}).encode()

    status, text = _request(
        port,
        "POST",
        "/action/status",
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Origin": "https://evil.example"},
    )

    assert status == 403
    assert "跨站" in text
    assert KnowledgeProfile.load(directory / "knowledge.md").find("字典").level == "存疑", "被拒的请求不能有副作用"


def test_same_origin_form_post_still_works(served):
    directory, port = served
    body = urlencode({"name": "字典", "level": "做过"}).encode()

    status, _ = _request(
        port,
        "POST",
        "/action/status",
        body=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": f"http://127.0.0.1:{port}",
        },
    )

    assert status == 303
    assert KnowledgeProfile.load(directory / "knowledge.md").find("字典").level == "做过"


def test_rebinding_host_is_rejected_for_pages_and_files(served):
    _, port = served

    assert _request(port, "GET", "/", headers={"Host": "evil.example"})[0] == 403
    assert _request(port, "GET", "/file?path=profile/knowledge.md", headers={"Host": "evil.example"})[0] == 403
    assert _request(port, "GET", "/")[0] == 200


def test_oversized_body_is_rejected_without_reading_it(served):
    _, port = served
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.putrequest("POST", "/action/status")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(MAX_REQUEST_BYTES + 1))
        conn.endheaders()
        response = conn.getresponse()
        assert response.status == 413
    finally:
        conn.close()


def test_malformed_content_length_is_400(served):
    _, port = served
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.putrequest("POST", "/action/status", skip_accept_encoding=True)
        conn.putheader("Content-Length", "abc")
        conn.endheaders()
        assert conn.getresponse().status == 400
    finally:
        conn.close()


# ---------------------------------------------------------------- 渲染


def test_inline_code_is_rendered():
    html = markdown_to_html("用 `print()` 输出，**加粗** 也行")

    assert "<code>print()</code>" in html
    assert "<strong>加粗</strong>" in html


def test_inline_code_content_is_escaped():
    assert "<code>&lt;h1&gt;</code>" in markdown_to_html("写 `<h1>` 标签")


TASKS = (
    "# 任务记录\n\n## 2026-09-27 10:00\n\n**目标**：做名片页\n\n**验收方式**：能显示\n"
    "\n## 2026-09-27 11:00\n\n**目标**：做课程表\n\n**验收方式**：4 行\n"
)


def _board_with_tasks(tmp_path, operations=None):
    directory = tmp_path / "profile"
    directory.mkdir()
    write_profile_atomic(directory / "knowledge.md", KnowledgeProfile())
    (directory / "tasks.md").write_text(TASKS, encoding="utf-8")
    return directory, TaskBoard(directory, operations=operations)


def test_chat_panels_do_not_share_an_id(tmp_path):
    _, board = _board_with_tasks(tmp_path)
    page = board.pages()["tasks"]

    assert page.count('class="chat-panel"') == 2
    assert 'id="chat-panel"' not in page


def test_chat_json_carries_rendered_markdown(tmp_path):
    """就地回答也渲染 markdown（与刷新后看到的历史一致），且服务端先转义再渲染。"""
    directory, board = _board_with_tasks(
        tmp_path, operations={"chat": lambda task, message: "## 要点\n\n用 `ul` 包 `li`\n\n<script>x</script>"}
    )
    dash = Dashboard(directory, board=board)

    status, _, body = dash.handle_request(
        "POST",
        "/action/chat",
        body=json.dumps({"task": "2026-09-27 10:00", "message": "怎么写列表"}).encode("utf-8"),
        content_type="application/json",
    )
    payload = json.loads(body)

    assert status == 200 and payload["ok"]
    assert "<h2>要点</h2>" in payload["html"]
    assert "<code>ul</code>" in payload["html"]
    assert "<script>" not in payload["html"], "回答里的 HTML 必须被转义"
    assert payload["output"].startswith("## 要点"), "output 仍是原文（留给不渲染的调用方）"


def test_panel_js_renders_server_markup_only_for_assistant():
    from src.dashboard import PANEL_JS

    assert "chatSay(log, \"DSH\", data.output || \"(空回答)\", data.html)" in PANEL_JS
    assert "chatSay(log, \"你\", message)" in PANEL_JS, "用户输入不能走 markup 分支"


def test_panel_js_uses_one_request_helper():
    """所有原地动作走同一个 postAction：非 JSON 响应也能给出中文原因。"""
    from src.dashboard import PANEL_JS

    assert PANEL_JS.count("fetch(") == 1
    for url in ("/action/status", "/action/chat", "/action/explain", "/action/delete_task"):
        assert f'postAction("{url}"' in PANEL_JS


def test_board_keeps_only_the_latest_result(tmp_path):
    _, board = _board_with_tasks(tmp_path)
    for _ in range(5):
        board.run_action("bogus")

    assert board.last_result().action_id == 5
    assert not hasattr(board, "_results"), "以前整段会话的结果都攒在列表里"


def test_missing_required_param_message_is_not_double_prefixed(tmp_path):
    _, board = _board_with_tasks(tmp_path, operations={"explain": lambda name: name})

    result = board.run_action("explain", {"name": "  "})

    assert not result.ok and result.status == 400
    assert result.output == "讲解需要一个知识点名称"
