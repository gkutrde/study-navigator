"""T-049 失败测试：入口收敛。

客户反馈：看板上的「在 DSH 中继续（弹终端）」是个**会弹黑框**的次级入口，
现在讨论已经收敛到插件面板 + 原生会话（T-040/T-046），弹终端这条路该收起来了。

要求：
1. 弹终端按钮**默认不显示**；只有环境变量 `DSH_TERMINAL_POPUP=1` 才启用；
2. 任务卡片加一条**「去 DSH 讨论」指引文案**（指向插件面板）；
3. 聊天面板**保持不变**（不因为收入口把它动坏）。

注：本卡与另一张「T-047 接力上下文书籍出处对齐」编号撞车，暂用 T-049。
"""
from __future__ import annotations

import pytest


def make_directory(tmp_path):
    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    from src.distill import KnowledgePoint
    from src.profile import KnowledgeProfile, write_profile_atomic

    write_profile_atomic(
        directory / "knowledge.md",
        KnowledgeProfile(points=[KnowledgePoint("列表", "学过", "e")]),
    )
    (directory / "tasks.md").write_text(
        "# 任务记录\n\n## 2026-09-27 10:00\n\n**目标**：做名片页\n\n**验收方式**：能看到姓名\n",
        encoding="utf-8",
    )
    from src.handoff import write_handoff
    from src.planner import read_task_records

    record = read_task_records(directory / "tasks.md")[0]
    write_handoff(directory, record=record, code="<h1>张三</h1>")
    return directory


def make_board(tmp_path, directory):
    from src import cli

    return cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )


def tasks_page(board) -> str:
    return board.pages()["tasks"]


def home_page(board) -> str:
    return board.pages()[""]


# ---------- 1. 弹终端按钮默认不显示 ----------


def test_terminal_button_hidden_by_default(tmp_path, monkeypatch):
    """默认（没有 DSH_TERMINAL_POPUP）不该出现弹终端按钮。"""
    monkeypatch.delenv("DSH_TERMINAL_POPUP", raising=False)
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    page = tasks_page(board)

    assert "在 DSH 中继续（弹终端）" not in page, "弹终端按钮默认不该显示"
    assert "/action/handoff" not in page, "整个 handoff 表单都不该渲染"


def test_terminal_button_hidden_when_flag_is_zero(tmp_path, monkeypatch):
    """只有 =1 才启用；=0 / 空串都算关。"""
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    for value in ("0", "", "no", "false", " ", "off"):
        monkeypatch.setenv("DSH_TERMINAL_POPUP", value)
        page = tasks_page(board)
        assert "在 DSH 中继续（弹终端）" not in page, f"{value!r} 不该启用"


def test_terminal_button_shown_when_flag_is_one(tmp_path, monkeypatch):
    """DSH_TERMINAL_POPUP=1 时按钮回来（想用的人还能用）。"""
    monkeypatch.setenv("DSH_TERMINAL_POPUP", "1")
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    page = tasks_page(board)

    assert "在 DSH 中继续（弹终端）" in page
    assert "/action/handoff" in page


def test_terminal_popup_env_helper():
    """单独的判定函数，便于别处复用与测试。"""
    from src.dashboard import terminal_popup_enabled

    assert terminal_popup_enabled({}) is False
    for value in ("1", "on", "true", "TRUE", " 1 "):
        assert terminal_popup_enabled({"DSH_TERMINAL_POPUP": value}) is True, value
    for value in ("0", "", "yes", "2", " ", "off", "false"):
        assert terminal_popup_enabled({"DSH_TERMINAL_POPUP": value}) is False, value


def test_handoff_action_still_available_via_cli_path(tmp_path):
    """收的是**按钮**，不是能力——动作本身仍要能跑（环境变量开了才点得到）。"""
    from src.dashboard import ACTION_LABELS, ACTION_PARAM_KEYS, FIXED_ACTIONS

    assert "handoff" in FIXED_ACTIONS
    assert ACTION_PARAM_KEYS["handoff"] == frozenset({"task"})
    assert "handoff" in ACTION_LABELS


def test_handoff_action_does_not_popup_unless_enabled(tmp_path, monkeypatch):
    """没开开关时，就算直接 POST /action/handoff 也不弹终端。"""
    monkeypatch.delenv("DSH_TERMINAL_POPUP", raising=False)
    import src.terminal as terminal
    from src import cli

    calls = []
    monkeypatch.setattr(
        terminal, "launch_chat_terminal", lambda *a, **kw: calls.append(a) or True
    )
    monkeypatch.setattr(
        cli, "_terminal_launcher", lambda: terminal.launch_chat_terminal, raising=False
    )
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    result = board.run_action("handoff", {"task": "2026-09-27 10:00"})

    assert result.ok, "生成接力上下文本身要成功"
    assert not calls, "没开开关就不该起终端"


# ---------- 2. 任务卡加「去 DSH 讨论」指引 ----------


def test_task_card_has_dsh_discussion_guidance(tmp_path, monkeypatch):
    monkeypatch.delenv("DSH_TERMINAL_POPUP", raising=False)
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    page = tasks_page(board)

    assert "去 DSH 讨论" in page, "任务卡要有「去 DSH 讨论」指引"
    assert "学习" in page and "面板" in page, "指引要指向插件面板"


def test_guidance_names_the_plugin_panel():
    """指引文案是单一来源常量，别在多处硬编码。"""
    from src.dashboard import DSH_DISCUSS_HINT

    assert "去 DSH 讨论" in DSH_DISCUSS_HINT
    assert "面板" in DSH_DISCUSS_HINT


def test_guidance_shown_even_when_terminal_enabled(tmp_path, monkeypatch):
    """开了终端开关，指引也还在（两个入口不互斥）。"""
    monkeypatch.setenv("DSH_TERMINAL_POPUP", "1")
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    page = tasks_page(board)

    assert "去 DSH 讨论" in page
    assert "在 DSH 中继续（弹终端）" in page


def test_guidance_is_not_a_form(tmp_path, monkeypatch):
    """指引只是文案 + 指向，不该多出一个会发请求的表单。"""
    monkeypatch.delenv("DSH_TERMINAL_POPUP", raising=False)
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    page = tasks_page(board)

    start = page.find("去 DSH 讨论")
    assert start > 0
    # 只看指引**自己**那一段（前面的 200 字窗口会把上方聊天表单也框进来——本测试第一版就这么假红过）
    chunk = page[start - 40 : start + 200]
    assert "<form" not in chunk, "指引不该带表单"


# ---------- 3. 聊天面板保持不变 ----------


def test_chat_panel_untouched(tmp_path, monkeypatch):
    """收入口不许把主入口（面板）动坏。"""
    monkeypatch.delenv("DSH_TERMINAL_POPUP", raising=False)
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    page = tasks_page(board)

    assert "/action/chat" in page, "面板表单还在"
    # 看板面板的容器类名是 chat-panel（dsh-learning-panel 是 DSH 插件那边的，不在这里）
    assert 'class="chat-panel"' in page, "面板容器还在"
    assert "chat-form" in page, "面板输入表单还在"


def test_chat_action_still_registered(tmp_path, monkeypatch):
    monkeypatch.delenv("DSH_TERMINAL_POPUP", raising=False)
    from src.dashboard import ACTION_PARAM_KEYS, FIXED_ACTIONS

    assert "chat" in FIXED_ACTIONS
    assert ACTION_PARAM_KEYS["chat"] == frozenset({"task", "message"})


def test_home_page_also_hides_terminal_button(tmp_path, monkeypatch):
    """首页「最近任务」卡片同样不该出现弹终端按钮。"""
    monkeypatch.delenv("DSH_TERMINAL_POPUP", raising=False)
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    page = home_page(board)

    assert "在 DSH 中继续（弹终端）" not in page
    assert "去 DSH 讨论" in page
