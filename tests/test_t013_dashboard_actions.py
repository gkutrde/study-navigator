"""T-013 失败测试：看板交互化（固定动作集 + 手工改状态）。

验收（[[04-任务与验收清单]] T-013 / A-07）：

- 页面按钮能触发 sync / distill / next / done 并展示结果；
- 知识点状态可手工改成 学过/做过/存疑 并落盘 knowledge.md；
- **只有固定动作集，无自由命令入口**（不存在"给我执行任意命令"的能力）；
- 仍然标准库 http.server + localhost + 零新依赖。

实现前编写（TaskBoard / ActionError 尚不存在），必须全部失败。
"""

from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path
from urllib.parse import urlencode

import pytest

from src.dashboard import (
    ACTION_PARAM_KEYS,
    FIXED_ACTIONS,
    ActionError,
    Dashboard,
    TaskBoard,
    build_server,
)
from src.distill import KnowledgePoint
from src.profile import KnowledgeProfile, write_profile_atomic


def make_profile(tmp_path):
    directory = tmp_path / "profile"
    write_profile_atomic(
        directory / "knowledge.md",
        KnowledgeProfile(
            points=[
                KnowledgePoint("列表", "学过", "笔记：列表用方括号", "Python 基础"),
                KnowledgePoint("字典", "存疑", "只提了一句", "Python 基础"),
            ]
        ),
    )
    return directory


class Recorder:
    """记录被调用的固定动作，避免测试真的跑 sync/LLM。"""

    def __init__(self, result: str = "已执行"):
        self.calls: list[tuple[str, tuple, dict]] = []
        self.result = result

    def __call__(self, *args, **kwargs):
        self.calls.append(("call", args, kwargs))
        return self.result


@pytest.fixture
def board(tmp_path):
    directory = make_profile(tmp_path)
    recorders = {
        "sync": Recorder("已同步"),
        "distill": Recorder("已提炼"),
        "next": Recorder("已出题"),
        "done": Recorder("已回写"),
    }
    return directory, TaskBoard(directory, operations=recorders), recorders


# --- 1. 固定动作集 ---------------------------------------------------------


def test_action_set_is_fixed(board):
    _, tb, _ = board

    # 从实现派生，避免每加一个固定动作都要改测试；同时锁住"只有固定动作集"
    assert tb.allowed_actions() == FIXED_ACTIONS
    assert set(tb.allowed_actions()) <= set(ACTION_PARAM_KEYS)


def test_known_action_dispatches_to_operation(board):
    _, tb, recorders = board

    result = tb.run_action("next")

    assert result.ok
    assert len(recorders["next"].calls) == 1
    assert "已出题" in result.output


def test_unknown_action_rejected(board):
    _, tb, recorders = board

    result = tb.run_action("rm -rf /")

    assert not result.ok
    assert result.status == 400
    assert all(recorder.calls == [] for recorder in recorders.values())


def test_no_free_command_entry_point_exists(board):
    """边界：不存在"传任意命令字符串去执行"的能力。"""
    _, tb, recorders = board

    for payload in ("sh -c whoami", "python -m http.server", "sync; rm -rf notes", "../etc/passwd"):
        result = tb.run_action(payload)
        assert not result.ok, payload
    assert all(recorder.calls == [] for recorder in recorders.values())


def test_action_accepts_only_fixed_parameters(board):
    _, tb, recorders = board

    # done 只允许「知识点 + 产出路径」，多给的可执行类参数一律拒绝
    result = tb.run_action("done", {"name": "列表", "path": "out.py", "cmd": "whoami"})

    assert not result.ok
    assert recorders["done"].calls == []


def test_bad_action_returns_failed_result_not_exception():
    """看板面向人操作，坏输入要变成可展示的结果，而不是把请求打崩。"""
    result = TaskBoard("profile").run_action("nope")

    assert not result.ok
    assert result.status == 400
    assert "固定动作" in result.output or "未知动作" in result.output


# --- 2. 手工改状态 ---------------------------------------------------------


def test_set_status_persists_to_knowledge_md(board):
    directory, tb, _ = board

    result = tb.run_action("status", {"name": "字典", "level": "学过", "note": "补看了示例"})

    assert result.ok
    reloaded = KnowledgeProfile.load(directory / "knowledge.md")
    point = reloaded.find("字典")
    assert point.level == "学过"
    assert "补看了示例" in point.evidence


def test_set_status_can_mark_done_with_product_path(board):
    directory, tb, _ = board

    tb.run_action("status", {"name": "列表", "level": "做过", "note": "tasks/wordcount.py"})

    point = KnowledgeProfile.load(directory / "knowledge.md").find("列表")
    assert point.level == "做过"
    assert "tasks/wordcount.py" in point.evidence


def test_set_status_keeps_other_points_untouched(board):
    directory, tb, _ = board

    tb.run_action("status", {"name": "字典", "level": "做过"})

    other = KnowledgeProfile.load(directory / "knowledge.md").find("列表")
    assert other.level == "学过"
    assert other.evidence == "笔记：列表用方括号"


def test_set_status_rejects_unknown_level(board):
    directory, tb, _ = board
    before = (directory / "knowledge.md").read_text(encoding="utf-8")

    result = tb.run_action("status", {"name": "字典", "level": "精通"})

    assert not result.ok
    assert result.status == 400
    assert (directory / "knowledge.md").read_text(encoding="utf-8") == before


def test_set_status_creates_unknown_point(board):
    """T-023 L-01 起：看板手工改状态也可以**新增**画像里没有的知识点。"""
    from src.profile import KnowledgeProfile

    directory, tb, _ = board

    result = tb.run_action("status", {"name": "不存在的点", "level": "学过"})

    assert result.ok
    reloaded = KnowledgeProfile.load(directory / "knowledge.md")
    assert any(p.name == "不存在的点" for p in reloaded.points)


def test_set_status_rejects_shell_like_level(board):
    """level 必须来自白名单，不能变成可注入的任意字符串。"""
    _, tb, _ = board

    result = tb.run_action("status", {"name": "字典", "level": "学过; rm -rf notes"})

    assert not result.ok


def test_set_status_requires_name(board):
    _, tb, _ = board

    assert not tb.run_action("status", {"level": "学过"}).ok


# --- 3. 页面：按钮与结果展示 ------------------------------------------------


def test_page_shows_fixed_action_buttons(board):
    directory, tb, _ = board
    pages = tb.pages()

    home = pages[""]
    for action in ("sync", "distill", "next", "done"):  # 这四个不需要入参的动作
        assert f'action="/action/{action}"' in home
    assert "<form" in home


def test_page_has_no_command_input_box(board):
    """无自由命令入口：页面里不应出现任意命令输入框。"""
    _, tb, _ = board
    home = tb.pages()[""]

    assert 'name="cmd"' not in home
    assert 'name="command"' not in home
    assert "<textarea" not in home


def test_status_form_offers_exactly_three_levels(board):
    _, tb, _ = board
    knowledge = tb.pages()["knowledge"]

    for level in ("学过", "做过", "存疑"):
        assert level in knowledge
    assert 'action="/action/status"' in knowledge


def test_last_result_is_shown_on_pages(board):
    _, tb, _ = board

    tb.run_action("distill")
    page = tb.pages()[""]

    assert "已提炼" in page


def test_next_result_appears_on_tasks_page(board):
    _, tb, _ = board

    tb.run_action("next")
    tasks = tb.pages()["tasks"]

    assert "已出题" in tasks


# --- 4. Dashboard 接线（POST） ---------------------------------------------


def test_dashboard_post_action_runs_and_redirects(board):
    directory, tb, recorders = board
    dash = Dashboard(directory, board=tb)

    status, headers, body = dash.handle_action("next", {})

    assert status == 303
    # T-030 起：写任务的动作会带锚点回跳到任务中心（浏览器自动滚到新卡片），
    # 所以这里不再写死 "/"，只校验"回到了本站页面"。
    assert headers.get("Location", "").startswith("/")
    assert len(recorders["next"].calls) == 1


def test_dashboard_post_unknown_action_is_400(board):
    directory, tb, _ = board
    dash = Dashboard(directory, board=tb)

    status, _, body = dash.handle_action("whatever", {})

    assert status == 400
    assert "固定动作" in body or "未知动作" in body


def test_dashboard_post_status_persists(board):
    directory, tb, _ = board
    dash = Dashboard(directory, board=tb)

    status, _, _ = dash.handle_action("status", {"name": "字典", "level": "做过"})

    assert status == 303
    assert KnowledgeProfile.load(directory / "knowledge.md").find("字典").level == "做过"


def test_dashboard_get_still_read_only(board):
    directory, tb, _ = board
    dash = Dashboard(directory, board=tb)

    assert dash.handle_request("GET", "/")[0] == 200
    assert dash.handle_request("PUT", "/")[0] == 405


# --- 5. 真 HTTP 端到端 -----------------------------------------------------


def test_http_post_form_triggers_action(board):
    directory, tb, recorders = board
    server = build_server(directory, port=0, board=tb)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = urlencode({"name": "字典", "level": "学过"}).encode()
        conn.request(
            "POST", "/action/status", body=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response = conn.getresponse()
        response.read()
        conn.close()

        assert response.status == 303
        assert KnowledgeProfile.load(directory / "knowledge.md").find("字典").level == "学过"
    finally:
        server.shutdown()
        server.server_close()


def test_http_post_unknown_action_rejected(board):
    directory, tb, recorders = board
    server = build_server(directory, port=0, board=tb)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("POST", "/action/drop_database", body=b"", headers={"Content-Type": "text/plain"})
        response = conn.getresponse()
        payload = response.read().decode("utf-8")
        conn.close()

        assert response.status == 400
        assert all(recorder.calls == [] for recorder in recorders.values())
        assert payload
    finally:
        server.shutdown()
        server.server_close()


def test_http_get_does_not_mutate(board):
    directory, tb, _ = board
    before = (directory / "knowledge.md").read_text(encoding="utf-8")
    server = build_server(directory, port=0, board=tb)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        for path in ("/", "/knowledge", "/tasks", "/action/next", "/action/status"):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", path)
            r = conn.getresponse()
            r.read()
            conn.close()
            assert r.status in (200, 404, 405), path
        assert (directory / "knowledge.md").read_text(encoding="utf-8") == before
    finally:
        server.shutdown()
        server.server_close()


def test_cli_serve_wires_real_operations(tmp_path, monkeypatch, capsys):
    """serve 必须把真实命令挂上（不是空的动作表）。"""
    from src import cli
    from src.dashboard import TaskBoard as TB

    captured = {}

    class FakeServer:
        server_address = ("127.0.0.1", 8765)

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            pass

    def fake_build_server(profile_dir, *, port=8765, board=None, host="127.0.0.1"):
        captured["board"] = board
        return FakeServer()

    monkeypatch.setattr("src.dashboard.build_server", fake_build_server)

    code = cli.main(["serve", "--port", "0", "--no-browser"], profile_path=tmp_path / "p" / "knowledge.md")

    assert code == 0
    assert isinstance(captured.get("board"), TB)
    assert captured["board"].allowed_actions() == FIXED_ACTIONS