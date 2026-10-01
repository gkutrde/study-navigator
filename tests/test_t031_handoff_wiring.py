"""T-031-B 失败测试：handoff 接线（看板按钮 + CLI）。

任务卡要求：提交作业后任务卡片出现「在 DSH 中继续」；固定动作集加 handoff，白名单 {task}；
白名单外参数 400；无 API 时**降级路径明确可用**。

Lead 的实测结论（见 profile/_t031_probe.md 与任务卡）：
本机 DSH 桌面版确实有 POST /api/session/create，但**需要 19387 同源的会话 cookie**，
而桌面版令牌无磁盘副本、不打印带令牌的 URL → 看板（别的端口）**拿不到**；
跨源 fetch 被 CORS 挡。所以本任务走**降级**，并且要如实告诉用户"为什么不能一键直通"。
"""

from __future__ import annotations

import re

import pytest

from src.dashboard import ACTION_PARAM_KEYS, FIXED_ACTIONS, TaskBoard
from src.distill import KnowledgePoint
from src.profile import KnowledgeProfile, write_profile_atomic

TASKS_MD = """# 任务记录

## 2026-09-27 10:00

**目标**：做一个个人名片页

**用到的知识点**：列表（ul/ol/li）

**新知识点**：表格（table/tr/th/td）（本次唯一的新点）

**验收方式**：页面能显示姓名
"""


def make_directory(tmp_path):
    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    write_profile_atomic(
        directory / "knowledge.md",
        KnowledgeProfile(points=[
            KnowledgePoint("列表（ul/ol/li）", "学过", "e"),
            KnowledgePoint("表格（table/tr/th/td）", "存疑", "e"),
        ]),
    )
    (directory / "tasks.md").write_text(TASKS_MD, encoding="utf-8")
    return directory


def make_board(tmp_path, directory):
    from src import cli

    return cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )


# ---------- 1. 白名单 ----------


def test_handoff_is_a_fixed_action():
    assert "handoff" in FIXED_ACTIONS


def test_handoff_param_whitelist_is_only_task():
    assert ACTION_PARAM_KEYS["handoff"] == frozenset({"task"})


def test_handoff_rejects_extra_params(tmp_path):
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    result = board.run_action("handoff", {"task": "2026-09-27 10:00", "cmd": "whoami"})

    assert not result.ok
    assert result.status == 400


def test_handoff_requires_task(tmp_path):
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    result = board.run_action("handoff", {})

    assert not result.ok
    assert "时间戳" in result.output or "task" in result.output


# ---------- 2. 生成上下文文件 ----------


def test_handoff_action_writes_context_file(tmp_path):
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    result = board.run_action("handoff", {"task": "2026-09-27 10:00"})

    assert result.ok, result.output
    files = list((directory / "handoff").glob("*.md"))
    assert len(files) == 1, f"应生成一个上下文文件，实际 {files}"
    text = files[0].read_text(encoding="utf-8")
    for heading in ("任务卡", "本次提交的代码", "画像相关点", "书籍出处与章节", "提问引导"):
        assert heading in text, f"缺段落：{heading}"


def test_handoff_result_mentions_the_file_path(tmp_path):
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    result = board.run_action("handoff", {"task": "2026-09-27 10:00"})

    rel = "handoff/2026-09-27-1000.md"
    assert rel.replace("/", "\\") in result.output or rel in result.output, result.output


def test_handoff_result_is_a_copyable_prompt(tmp_path):
    """降级路径必须"明确可用"：结果里要有能直接粘贴的提问。"""
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    result = board.run_action("handoff", {"task": "2026-09-27 10:00"})

    assert "我的代码哪里不足" in result.output
    assert "我该看书的哪部分" in result.output


def test_handoff_repeat_click_updates_same_file(tmp_path):
    """一任务一文件：重复点击覆盖同一个文件。"""
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    board.run_action("handoff", {"task": "2026-09-27 10:00"})
    first = list((directory / "handoff").glob("*.md"))
    board.run_action("handoff", {"task": "2026-09-27 10:00"})
    second = list((directory / "handoff").glob("*.md"))

    assert len(second) == 1
    assert [p.name for p in first] == [p.name for p in second]


def test_handoff_reports_unknown_task(tmp_path):
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    result = board.run_action("handoff", {"task": "1999-01-01 00:00"})

    assert not result.ok
    assert "1999-01-01" in result.output or "没有" in result.output


def test_handoff_includes_submitted_code_when_present(tmp_path):
    """提交过作业时，上下文要带上那份代码。"""
    from src.planner import append_review

    directory = make_directory(tmp_path)
    append_review(directory / "tasks.md", "2026-09-27 10:00", code="<h1>张三</h1>",
                  feedback="还行", suggestion="加头像")
    board = make_board(tmp_path, directory)

    board.run_action("handoff", {"task": "2026-09-27 10:00"})

    text = next((directory / "handoff").glob("*.md")).read_text(encoding="utf-8")
    assert "<h1>张三</h1>" in text


# ---------- 3. 看板按钮 ----------


def test_task_card_has_handoff_button(tmp_path):
    """T-049 后：按钮**默认不显示**，但仍要有「去 DSH 讨论」的指引。

    原断言（默认就能看到按钮）已按新契约更新——不是把测试删掉，
    而是把「按钮在」换成「指引在」，并另开一条测开关打开后的按钮。
    """
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    assert 'action="/action/handoff"' not in page, "默认不该有弹终端表单"
    assert "去 DSH 讨论" in page, "要有指向插件面板的指引"


def test_task_card_has_handoff_button_when_enabled(tmp_path, monkeypatch):
    """开了 DSH_TERMINAL_POPUP=1，T-031 原来的行为要完整回来。"""
    monkeypatch.setenv("DSH_TERMINAL_POPUP", "1")
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    assert 'action="/action/handoff"' in page
    assert "在 DSH 中继续" in page
    assert 'name="task"' in page


def test_handoff_button_sits_near_submit(tmp_path, monkeypatch):
    """按钮要出现在任务卡片里（提交作业附近），不是在顶部动作区。

    T-049 起按钮默认收起，所以这里显式打开开关再验位置。
    """
    monkeypatch.setenv("DSH_TERMINAL_POPUP", "1")
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    card = page.split('data-task="2026-09-27 10:00"', 1)[1].split("task-card", 1)[0]
    assert 'action="/action/handoff"' in card


def test_handoff_button_not_in_top_toolbar(tmp_path):
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    toolbar = page.split("<h2>任务中心</h2>", 1)[0]
    assert 'action="/action/handoff"' not in toolbar


def test_handoff_redirects_to_that_task_anchor(tmp_path):
    from src.dashboard import Dashboard

    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)
    dash = Dashboard(directory, board=board)

    status, headers, _body = dash.handle_action("handoff", {"task": "2026-09-27 10:00"})

    assert status == 303
    assert headers.get("Location", "").startswith("/tasks#task-"), headers


# ---------- 4. 降级说明要如实 ----------


def test_handoff_result_explains_why_manual(tmp_path):
    """不能只说"请手动"，要说明本机为什么不支持一键直通。"""
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    result = board.run_action("handoff", {"task": "2026-09-27 10:00"})

    assert "手动" in result.output or "粘贴" in result.output
    assert "令牌" in result.output or "同源" in result.output or "cookie" in result.output.lower()


def test_handoff_mentions_headless_alternative(tmp_path):
    """给出命令行替代方案（本机真实可用的一条路）。"""
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    result = board.run_action("handoff", {"task": "2026-09-27 10:00"})

    assert "--profile headless" in result.output

def test_handoff_path_in_result_is_copyable(tmp_path, monkeypatch):
    """结果里那条路径必须**能直接照抄**去执行。

    实测抓到的坑：曾经按 profile 目录的上一级算相对路径，把 profile/ 前缀吃掉了，
    结果给出 profile/_xxx/handoff/....md —— 照抄去跑命令是找不到文件的。
    """
    import os

    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)
    monkeypatch.chdir(tmp_path)

    result = board.run_action("handoff", {"task": "2026-09-27 10:00"})

    match = re.search(r"\uff1a(\S+\.md)", result.output)
    assert match, result.output
    shown = match.group(1)
    assert os.path.isfile(shown), f"结果里的路径照抄找不到文件：{shown}"