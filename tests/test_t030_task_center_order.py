"""T-030 失败测试：任务中心排序与提交入口可见性。

客户反馈：出题后新任务在列表最下面、找不到提交按钮。

要求：
① 任务卡片按时间**倒序**，最新在最上（连续出两题，最新那张在最上方）；
② 出题/回写/提交后**页面锚点定位到该任务卡片**，不靠用户滚动找；
③ 「提交作业」改**主按钮样式**（醒目配色），卡片内位置固定在知识点 chips **下方**。
"""

from __future__ import annotations

import re

import pytest

from src.dashboard import Dashboard, TaskBoard
from src.distill import KnowledgePoint
from src.profile import KnowledgeProfile, write_profile_atomic

TASKS_MD = """# 任务记录

## 2026-09-27 09:00

## 下一步任务

**目标**：第一题

**用到的知识点**：列表

**验收方式**：a

## 2026-09-27 10:00

## 下一步任务

**目标**：第二题

**用到的知识点**：列表

**验收方式**：b

## 2026-09-27 11:00

## 下一步任务

**目标**：第三题

**用到的知识点**：列表

**验收方式**：c
"""


def make_directory(tmp_path, tasks=TASKS_MD):
    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    write_profile_atomic(
        directory / "knowledge.md",
        KnowledgeProfile(points=[KnowledgePoint("列表", "学过", "e")]),
    )
    (directory / "tasks.md").write_text(tasks, encoding="utf-8")
    return directory


def task_order(page: str) -> list[str]:
    """页面上任务卡片的出现顺序（上 → 下）。"""
    return re.findall(r'<div class="task-card"[^>]*data-task="([^"]+)"', page)


# ---------- ① 倒序 ----------


def test_cards_are_newest_first(tmp_path):
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    assert task_order(page) == ["2026-09-27 11:00", "2026-09-27 10:00", "2026-09-27 09:00"]


def test_newest_card_is_above_the_fold_marker(tmp_path):
    """最新那张必须出现在任务列表的**开头**（不是被塞在最后）。"""
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    body = page.split("<h2>任务中心</h2>", 1)[1]
    first = body.index('data-task="2026-09-27 11:00"')
    last = body.index('data-task="2026-09-27 09:00"')
    assert first < last


def test_same_timestamp_keeps_file_order(tmp_path):
    """时间戳相同时不能乱序（文件里在后的仍是"更新的"）。"""
    tasks = (
        "# 任务记录\n\n"
        "## 2026-09-27 10:00\n\n**目标**：先写的\n\n**验收方式**：a\n\n"
        "## 2026-09-27 10:00\n\n**目标**：后写的\n\n**验收方式**：b\n"
    )
    directory = make_directory(tmp_path, tasks)
    page = TaskBoard(directory).pages()["tasks"]

    body = page.split("<h2>任务中心</h2>", 1)[1]
    assert body.index("后写的") < body.index("先写的"), "同时间戳时后写入的应更靠上"


# ---------- ② 锚点定位 ----------


def test_each_card_has_anchor_id(tmp_path):
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    ids = re.findall(r'<div class="task-card"[^>]*id="([^"]+)"', page)
    assert len(ids) == 3, f"每张卡片都要有锚点 id，实际 {ids}"
    assert len(set(ids)) == 3, "锚点 id 不能重复"


def test_anchor_id_is_url_safe(tmp_path):
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    ids = re.findall(r'<div class="task-card"[^>]*id="([^"]+)"', page)
    for anchor in ids:
        assert re.fullmatch(r"[A-Za-z0-9_.-]+", anchor), f"锚点不适合放进 URL 片段：{anchor}"


def test_next_redirects_to_newest_task_anchor(tmp_path):
    """出题成功后应回跳到**最新那张卡**（浏览器自动滚动过去）。"""
    from src import cli

    directory = make_directory(tmp_path)
    board = cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )
    board._operations["next"] = lambda topics=None: "已留档"
    dash = Dashboard(directory, board=board)

    status, headers, _body = dash.handle_action("next", {"topics": ["网页基础"]})

    assert status == 303
    assert headers.get("Location", "").startswith("/tasks#task-"), headers


def test_review_redirects_to_that_task_anchor(tmp_path):
    from src import cli

    directory = make_directory(tmp_path)
    board = cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )
    board._operations["review"] = lambda task, code: "【评价】ok"
    dash = Dashboard(directory, board=board)

    status, headers, _body = dash.handle_action("review", {"task": "2026-09-27 10:00", "code": "x"})

    assert status == 303
    assert "2026-09-27" in headers.get("Location", ""), headers


def test_done_redirects_to_latest_task_anchor(tmp_path):
    from src import cli

    directory = make_directory(tmp_path)
    board = cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )
    board._operations["done"] = lambda name, path, recite="": "已回写"
    dash = Dashboard(directory, board=board)

    status, headers, _body = dash.handle_action("done", {"name": "列表", "path": "x.html"})

    assert status == 303
    assert headers.get("Location", "").startswith("/tasks#task-"), headers


def test_failed_action_does_not_redirect(tmp_path):
    """失败仍然是原页面报错，不能假装成功去跳锚点。"""
    from src import cli

    directory = make_directory(tmp_path)
    board = cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )
    dash = Dashboard(directory, board=board)

    status, headers, _body = dash.handle_action("next", {"cmd": "whoami"})

    assert status == 400
    assert "Location" not in headers


def test_task_card_helper_exposes_anchor(tmp_path):
    from src.dashboard import task_anchor

    assert task_anchor("2026-09-27 11:00") == "task-2026-09-27-11-00"
    assert re.fullmatch(r"[A-Za-z0-9_.-]+", task_anchor("2026-9-7 1:2"))


# ---------- ③ 提交按钮：主按钮样式 + 位置 ----------


def test_submit_button_is_primary_style(tmp_path):
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    buttons = re.findall(r'<button[^>]*>提交作业</button>', page)
    assert len(buttons) == 3, f"三张卡片都要有提交按钮，实际 {len(buttons)}"
    for button in buttons:
        assert "primary" in button, f"提交作业要是主按钮样式：{button}"


def test_primary_style_has_distinct_colors(tmp_path):
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    styles = re.findall(r"\.btn-primary\{([^}]*)\}", page)
    assert styles, "缺少 .btn-primary 样式定义"
    blob = styles[0]
    assert "background" in blob and "color" in blob, "主按钮要有醒目的前景/背景色"


def test_submit_form_sits_below_point_chips(tmp_path):
    """按钮位置固定在知识点 chips **下方**。"""
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    card = page.split('data-task="2026-09-27 11:00"', 1)[1].split("task-card", 1)[0]
    assert card.index('class="chips"') < card.index('action="/action/review"')
    # 而且不能被别的东西插在中间（步骤/验收方式在 chips 之后、表单之前是允许的）
    assert card.index("验收方式") < card.index('action="/action/review"')


def test_submit_form_has_visible_label(tmp_path):
    """找不到按钮的另一个原因是它只是个 chip；要有明确的按钮文案与更大的可点区域。"""
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    assert "提交作业" in page
    assert 'name="code"' in page
    assert "textarea" in page


def test_review_form_is_not_hidden_by_javascript(tmp_path):
    """提交入口在**无 JS** 时也必须可见（渐进增强）。"""
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    match = re.search(r'<form[^>]*action="/action/review"[^>]*>', page)
    assert match
    assert "hidden" not in match.group(0), "提交表单不该默认隐藏"

# ---------- ④ 回归：HTTP 层不能吞掉跳转锚点 ----------


def test_http_layer_preserves_redirect_anchor(tmp_path):
    """真发 HTTP 表单提交：Location 必须带锚点。

    这是 T-030 实测抓到的 bug——Dashboard 明明返回了 /tasks#task-...，
    但 HTTP handler 当时写死 Location: /，把锚点丢掉，
    浏览器于是跟着 /action/... 又发一次 GET，页面直接空掉。
    之前的测试都直接调 handle_action，所以没抓到这一层。
    """
    import http.client
    import threading

    from src import cli
    from src.dashboard import build_server

    directory = make_directory(tmp_path)
    board = cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )
    board._operations["review"] = lambda task, code: "【评价】ok"

    server = build_server(directory, port=0, board=board)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
        conn.request(
            "POST",
            "/action/review",
            body="task=2026-09-27+10%3A00&code=x",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response = conn.getresponse()
        location = response.getheader("Location")
        response.read()
        conn.close()
    finally:
        server.shutdown()
        server.server_close()

    assert response.status == 303
    assert location is not None, "303 必须带 Location"
    assert location.startswith("/tasks#task-"), f"锚点被吞掉了：{location}"


def test_http_layer_preserves_plain_redirect_for_other_actions(tmp_path):
    """没有对应任务卡片时退回 /，而不是丢掉 Location。"""
    import http.client
    import threading

    from src import cli
    from src.dashboard import build_server

    directory = make_directory(tmp_path)
    (directory / "tasks.md").unlink()
    board = cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )
    board._operations["distill"] = lambda *a, **kw: "已提炼"

    server = build_server(directory, port=0, board=board)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
        conn.request("POST", "/action/distill", body="",
                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        response = conn.getresponse()
        location = response.getheader("Location")
        response.read()
        conn.close()
    finally:
        server.shutdown()
        server.server_close()

    assert response.status == 303
    assert location == "/", f"提炼这类全局动作仍回首页，实际 {location}"

def test_anchor_ids_are_unique_within_same_minute(tmp_path):
    """同一分钟内出两题：时间戳相同，但锚点 id **必须唯一**。

    实测抓到：两题都在 15:05 时，同一张卡片的 id 撞在一起（HTML 非法、
    锚点定位会跳到第一张），Playwright 也因此报 strict mode violation。
    """
    tasks = (
        "# 任务记录\n\n"
        "## 2026-09-27 15:05\n\n**目标**：第 2 题\n\n**验收方式**：a\n\n"
        "## 2026-09-27 15:05\n\n**目标**：第 3 题\n\n**验收方式**：b\n"
    )
    directory = make_directory(tmp_path, tasks)
    page = TaskBoard(directory).pages()["tasks"]

    ids = re.findall(r'<div class="task-card"[^>]*id="([^"]+)"', page)
    assert len(ids) == 2
    assert len(set(ids)) == 2, f"锚点 id 撞了：{ids}"
    for anchor in ids:
        assert re.fullmatch(r"[A-Za-z0-9_.-]+", anchor)


def test_same_minute_newest_is_reachable_by_its_anchor(tmp_path):
    """同分钟两题时，重定向目标要落在**最新那张**上（不是第一张）。"""
    from src import cli

    tasks = (
        "# 任务记录\n\n"
        "## 2026-09-27 15:05\n\n**目标**：第 2 题\n\n**验收方式**：a\n\n"
        "## 2026-09-27 15:05\n\n**目标**：第 3 题\n\n**验收方式**：b\n"
    )
    directory = make_directory(tmp_path, tasks)
    board = cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )
    board._operations["done"] = lambda name, path, recite="": "已回写"
    dash = Dashboard(directory, board=board)

    _status, headers, _body = dash.handle_action("done", {"name": "列表", "path": "x.html"})
    page = board.pages()["tasks"]

    target = headers["Location"].split("#", 1)[1]
    assert f'id="{target}"' in page, f"重定向锚点 {target} 不在页面里"
    # 该锚点所在的卡片应当是"第 3 题"（最新）
    card = page.split(f'id="{target}"', 1)[1].split("task-card", 1)[0]
    assert "第 3 题" in card, "锚点应指向最新那条任务"
