"""T-033 失败测试：handoff 自动弹终端。

客户反馈：点「在 DSH 中继续」没有跳转终端。

要求：
- Windows 上用 `cmd /c start` 弹新终端，自动执行 chat 命令，**窗口保持打开**（cmd /k）；
- 路径带空格要加引号；
- 非 Windows 或**弹窗失败时不报错**，静默保持现有文字指引；
- 按钮文案改「在 DSH 中继续（弹终端）」。
"""

from __future__ import annotations

import subprocess

import pytest

from src.terminal import (
    FIRST_QUESTIONS,
    build_chat_command_line,
    build_start_argv,
    launch_chat_terminal,
    quote_for_cmd,
)


# ---------- 1. 引号：路径带空格必须加引号 ----------


def test_quote_for_cmd_wraps_when_spaces():
    assert quote_for_cmd("C:\\Program Files\\Python\\python.exe") == '"C:\\Program Files\\Python\\python.exe"'


def test_quote_for_cmd_leaves_simple_token_alone():
    assert quote_for_cmd("python") == "python"


def test_quote_for_cmd_escapes_embedded_quotes():
    # cmd 里内部引号用 "" 转义（不是 \\"）
    assert quote_for_cmd('say "hi"') == '"say ""hi""' + '"'


# ---------- 2. chat 命令行：逻辑单行 + 正确引号 ----------


def test_build_chat_command_line_has_module_and_timestamp():
    line = build_chat_command_line("C:\\py\\python.exe", "2026-09-27 10:00")

    assert "-m" in line and "src.cli" in line
    assert "chat" in line
    assert "2026-09-27 10:00" in line
    assert line.index("chat") < line.rindex("2026-09-27 10:00")


def test_build_chat_command_line_includes_first_question():
    line = build_chat_command_line("python", "2026-09-27 10:00")

    assert FIRST_QUESTIONS[0] in line
    assert "我的代码哪里不足" in line


def test_build_chat_command_line_quotes_spaced_executable():
    line = build_chat_command_line("C:\\Program Files\\Python\\python.exe", "2026-09-27 10:00")

    assert '"C:\\Program Files\\Python\\python.exe"' in line


def test_build_chat_command_line_passes_profile_dir_when_given():
    line = build_chat_command_line("python", "2026-09-27 10:00", profile_path="C:\\my dir\\profile\\knowledge.md")

    assert "--profile" in line
    assert '"C:\\my dir\\profile\\knowledge.md"' in line


# ---------- 3. start argv：cmd /c start + cmd /k ----------


def test_build_start_argv_uses_start_and_keeps_window_open():
    argv = build_start_argv("C:\\Program Files\\Python\\python.exe", "2026-09-27 10:00")

    assert argv[0].lower().endswith(("cmd", "cmd.exe"))
    assert argv[1] == "/c"
    assert argv[2].lower() == "start"
    # 空标题，避免 start 把命令当窗口标题
    assert argv[3] == ""
    assert argv[4].lower() in ("cmd", "cmd.exe")
    assert argv[5] == "/k", "窗口必须保持打开（cmd /k）"
    assert "chat" in " ".join(argv)


def test_build_start_argv_is_a_list_not_shell_string():
    argv = build_start_argv("python", "2026-09-27 10:00")

    assert isinstance(argv, list)
    assert all(isinstance(x, str) for x in argv)


# ---------- 4. 静默降级 ----------


def test_launch_returns_false_on_non_windows(monkeypatch):
    import src.terminal as terminal

    monkeypatch.setattr(terminal.os, "name", "posix")

    assert launch_chat_terminal("python", "2026-09-27 10:00") is False


def test_launch_swallows_oserror(monkeypatch):
    import src.terminal as terminal

    monkeypatch.setattr(terminal.os, "name", "nt")

    def boom(*a, **kw):
        raise OSError("no console")

    monkeypatch.setattr(terminal.subprocess, "Popen", boom)

    assert launch_chat_terminal("python", "2026-09-27 10:00") is False


def test_launch_swallows_file_not_found(monkeypatch):
    import src.terminal as terminal

    monkeypatch.setattr(terminal.os, "name", "nt")

    def boom(*a, **kw):
        raise FileNotFoundError("cmd")

    monkeypatch.setattr(terminal.subprocess, "Popen", boom)

    assert launch_chat_terminal("python", "2026-09-27 10:00") is False


def test_launch_returns_true_when_started(monkeypatch):
    import src.terminal as terminal

    monkeypatch.setattr(terminal.os, "name", "nt")
    seen = {}

    def fake_popen(argv, **kw):
        seen["argv"] = argv
        seen["kw"] = kw
        return object()

    monkeypatch.setattr(terminal.subprocess, "Popen", fake_popen)

    assert launch_chat_terminal("python", "2026-09-27 10:00") is True
    assert seen["argv"][2].lower() == "start"
    assert seen["kw"].get("shell") in (None, False), "不要走 shell"


def test_launch_never_raises(monkeypatch):
    """任何异常都要被吞掉——弹窗失败绝不能把页面动作搞成报错。"""
    import src.terminal as terminal

    monkeypatch.setattr(terminal.os, "name", "nt")

    def boom(*a, **kw):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(terminal.subprocess, "Popen", boom)

    assert launch_chat_terminal("python", "2026-09-27 10:00") is False

# ---------- 5. 接线：handoff 动作里弹终端 ----------


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
        "# 任务记录\n\n## 2026-09-27 10:00\n\n**目标**：做名片页\n\n**验收方式**：能看到\n",
        encoding="utf-8",
    )
    return directory


def make_board(tmp_path, directory):
    from src import cli

    return cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )


def test_handoff_button_says_terminal(tmp_path):
    """按钮文案改成「在 DSH 中继续（弹终端）」。"""
    from src.dashboard import TaskBoard

    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    assert "在 DSH 中继续（弹终端）" in page


def test_handoff_action_tries_to_launch_terminal(tmp_path, monkeypatch):
    import src.cli as cli
    import src.terminal as terminal

    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)
    seen = {}

    monkeypatch.setattr(
        terminal,
        "launch_chat_terminal",
        lambda exe, when, *a, **kw: seen.update(exe=exe, when=when) or True,
    )
    monkeypatch.setattr(cli, "_terminal_launcher", lambda: terminal.launch_chat_terminal, raising=False)

    result = board.run_action("handoff", {"task": "2026-09-27 10:00"})

    assert result.ok
    assert seen.get("when") == "2026-09-27 10:00"


def test_handoff_still_ok_when_launch_fails(tmp_path, monkeypatch):
    """弹窗失败必须静默降级：动作仍然成功，文字指引仍在。"""
    import src.cli as cli
    import src.terminal as terminal

    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    monkeypatch.setattr(terminal, "launch_chat_terminal", lambda *a, **kw: False)
    monkeypatch.setattr(cli, "_terminal_launcher", lambda: terminal.launch_chat_terminal, raising=False)

    result = board.run_action("handoff", {"task": "2026-09-27 10:00"})

    assert result.ok
    assert "我的代码哪里不足" in result.output, "降级后提问指引必须还在"


def test_handoff_output_mentions_terminal_when_launched(tmp_path, monkeypatch):
    import src.cli as cli
    import src.terminal as terminal

    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    monkeypatch.setattr(terminal, "launch_chat_terminal", lambda *a, **kw: True)
    monkeypatch.setattr(cli, "_terminal_launcher", lambda: terminal.launch_chat_terminal, raising=False)

    result = board.run_action("handoff", {"task": "2026-09-27 10:00"})

    assert "终端" in result.output


def test_handoff_output_says_manual_when_not_launched(tmp_path, monkeypatch):
    import src.cli as cli
    import src.terminal as terminal

    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    monkeypatch.setattr(terminal, "launch_chat_terminal", lambda *a, **kw: False)
    monkeypatch.setattr(cli, "_terminal_launcher", lambda: terminal.launch_chat_terminal, raising=False)

    result = board.run_action("handoff", {"task": "2026-09-27 10:00"})

    assert "终端" not in result.output or "手动" in result.output or "自己" in result.output


def test_handoff_never_raises_when_launcher_explodes(tmp_path, monkeypatch):
    """连 launcher 自己抛异常也不能让动作失败。"""
    import src.cli as cli

    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    def boom(*a, **kw):
        raise RuntimeError("terminal exploded")

    monkeypatch.setattr(cli, "_terminal_launcher", lambda: boom, raising=False)

    result = board.run_action("handoff", {"task": "2026-09-27 10:00"})

    assert result.ok, result.output
    assert "我的代码哪里不足" in result.output

def test_launch_uses_popen_not_run(monkeypatch):
    """必须用 Popen（不等待）：cmd /k 的窗口不会自己退出，run 会一直挂住。

    实测：用 subprocess.run 跑这条命令会 TimeoutExpired——因为 /k 让窗口常驻。
    """
    import src.terminal as terminal

    monkeypatch.setattr(terminal.os, "name", "nt")
    calls = {}

    def fake_popen(argv, **kw):
        calls["argv"] = argv
        return object()

    def forbidden_run(*a, **kw):
        raise AssertionError("launch 不能用 subprocess.run：/k 会挂住")

    monkeypatch.setattr(terminal.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(terminal.subprocess, "run", forbidden_run, raising=False)

    assert terminal.launch_chat_terminal("python", "2026-09-27 10:00") is True
    assert calls["argv"][5] == "/k"


def test_start_argv_quotes_spaced_python_in_command_line(monkeypatch):
    """带空格的解释器路径必须在命令里加引号（任务卡要求）。"""
    argv = build_start_argv(r"C:\Program Files\Python\python.exe", "2026-09-27 10:00")

    command = argv[-1]
    assert command.startswith('"C:\\Program Files\\Python\\python.exe"'), command