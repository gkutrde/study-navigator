"""T-034 失败测试：看板内嵌聊天面板（会话 + 留档 + prompt 组装）。

主方案要点：
- 历史按任务在服务端隔离；对话留档 profile/handoff/<任务>.chat.md；
- 每轮把「handoff 上下文 + 该任务对话历史 + 新消息」拼成 prompt；
- 历史超 30000 字符时**保留 handoff 全文**；T-043 起最旧轮次压成「较早对话摘要」块，
  没有摘要器（拿不到 LLM）时退回硬裁并注明「已裁剪 N 轮」——两条路径都在本文件里有测试。
"""

from __future__ import annotations

import pathlib

import pytest

from src.chat_session import (
    MAX_PROMPT_CHARS,
    ChatSessionError,
    append_turn,
    archive_path,
    build_prompt,
    load_turns,
    render_archive,
    save_archive,
)

HANDOFF = "# DSH 接力上下文\n\n## 一、任务卡\n\n- **目标**：做名片页\n" * 3


def test_archive_path_is_per_task(tmp_path):
    directory = tmp_path / "profile"
    first = archive_path(directory, "2026-09-27 10:00")
    second = archive_path(directory, "2026-09-27 11:00")

    assert first != second
    assert first.name.endswith(".chat.md")
    assert first.parent.name == "handoff"


def test_empty_turns_for_new_task(tmp_path):
    directory = tmp_path / "profile"

    assert load_turns(directory, "2026-09-27 10:00") == []


def test_append_and_reload_roundtrip(tmp_path):
    directory = tmp_path / "profile"
    append_turn(directory, "2026-09-27 10:00", role="user", text="我的代码哪里不足？")
    append_turn(directory, "2026-09-27 10:00", role="assistant", text="缺少头像占位。")

    turns = load_turns(directory, "2026-09-27 10:00")

    assert [t.role for t in turns] == ["user", "assistant"]
    assert turns[0].text == "我的代码哪里不足？"
    assert turns[1].text == "缺少头像占位。"


def test_history_is_isolated_per_task(tmp_path):
    directory = tmp_path / "profile"
    append_turn(directory, "2026-09-27 10:00", role="user", text="第一题的问题")
    append_turn(directory, "2026-09-27 11:00", role="user", text="第二题的问题")

    first = load_turns(directory, "2026-09-27 10:00")
    second = load_turns(directory, "2026-09-27 11:00")

    assert [t.text for t in first] == ["第一题的问题"]
    assert [t.text for t in second] == ["第二题的问题"]


def test_archive_file_is_human_readable(tmp_path):
    directory = tmp_path / "profile"
    append_turn(directory, "2026-09-27 10:00", role="user", text="问题一")
    append_turn(directory, "2026-09-27 10:00", role="assistant", text="回答一")

    text = archive_path(directory, "2026-09-27 10:00").read_text(encoding="utf-8")

    assert "问题一" in text and "回答一" in text
    assert "你" in text and ("助教" in text or "DSH" in text)


def test_append_is_atomic_and_leaves_no_tmp(tmp_path):
    directory = tmp_path / "profile"
    append_turn(directory, "2026-09-27 10:00", role="user", text="x")

    assert not list((directory / "handoff").glob("*.tmp"))


def test_invalid_role_rejected(tmp_path):
    directory = tmp_path / "profile"

    with pytest.raises(ChatSessionError):
        append_turn(directory, "2026-09-27 10:00", role="system", text="x")


def test_empty_timestamp_rejected(tmp_path):
    directory = tmp_path / "profile"

    with pytest.raises(ChatSessionError):
        append_turn(directory, "   ", role="user", text="x")


# ---------- prompt 组装 ----------


def test_build_prompt_includes_handoff_and_new_message():
    prompt = build_prompt(HANDOFF, [], "新问题")

    assert "DSH 接力上下文" in prompt
    assert "新问题" in prompt


def test_build_prompt_includes_history():
    from src.chat_session import ChatTurn

    turns = [ChatTurn("user", "第一轮问题"), ChatTurn("assistant", "第一轮回答")]
    prompt = build_prompt(HANDOFF, turns, "第二轮问题")

    assert "第一轮问题" in prompt
    assert "第一轮回答" in prompt
    assert prompt.index("第一轮回答") < prompt.index("第二轮问题")


def test_build_prompt_keeps_handoff_when_history_huge():
    """历史超长时要保留 handoff 全文，只能裁最旧轮次。"""
    from src.chat_session import ChatTurn

    turns = [ChatTurn("user", "旧" * 5000) for _ in range(12)]
    prompt = build_prompt(HANDOFF, turns, "最新问题")

    assert len(prompt) <= MAX_PROMPT_CHARS
    assert HANDOFF.strip() in prompt, "handoff 全文不能被裁掉"
    assert "最新问题" in prompt
    assert "已裁剪" in prompt and "轮" in prompt


def test_build_prompt_notes_how_many_turns_trimmed():
    from src.chat_session import ChatTurn

    turns = [ChatTurn("user", "旧" * 5000) for _ in range(12)]
    prompt = build_prompt(HANDOFF, turns, "最新问题")

    import re

    match = re.search(r"已裁剪\s*(\d+)\s*轮", prompt)
    assert match, prompt[-400:]
    assert int(match.group(1)) > 0


def test_build_prompt_without_history_is_single_shot(tmp_path):
    prompt = build_prompt(HANDOFF, [], "只有一问")

    assert "已裁剪" not in prompt


def test_build_prompt_rejects_blank_message():
    with pytest.raises(ChatSessionError):
        build_prompt(HANDOFF, [], "   ")


# ---------- 留档渲染 ----------


def test_render_archive_has_header_and_both_roles():
    from src.chat_session import ChatTurn

    text = render_archive("2026-09-27 10:00", [
        ChatTurn("user", "问"), ChatTurn("assistant", "答"),
    ])

    assert "2026-09-27 10:00" in text
    assert "问" in text and "答" in text


def test_save_archive_writes_file(tmp_path):
    from src.chat_session import ChatTurn

    directory = tmp_path / "profile"
    path = save_archive(directory, "2026-09-27 10:00", [ChatTurn("user", "问")])

    assert path.is_file()
    assert "问" in path.read_text(encoding="utf-8")

# ---------- 面板动作与 HTTP ----------


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


def make_board(tmp_path, directory, completer=None):
    from src import cli

    board = cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )
    return board


def test_chat_is_a_fixed_action():
    from src.dashboard import ACTION_PARAM_KEYS, FIXED_ACTIONS

    assert "chat" in FIXED_ACTIONS
    assert ACTION_PARAM_KEYS["chat"] == frozenset({"task", "message"})


def test_chat_rejects_extra_params(tmp_path):
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    result = board.run_action("chat", {"task": "2026-09-27 10:00", "message": "x", "cmd": "whoami"})

    assert not result.ok
    assert result.status == 400


def test_chat_requires_message(tmp_path):
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    result = board.run_action("chat", {"task": "2026-09-27 10:00"})

    assert not result.ok
    assert "消息" in result.output or "message" in result.output


def test_task_card_has_chat_panel(tmp_path):
    from src.dashboard import TaskBoard

    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    assert "chat-panel" in page
    assert "data-chat-task=" in page
    assert "action=\"/action/chat\"" in page or "/action/chat" in page


def test_chat_panel_has_input_and_message_list(tmp_path):
    from src.dashboard import TaskBoard

    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    assert "chat-input" in page
    assert "chat-log" in page


def test_chat_panel_js_uses_fetch_without_reload(tmp_path):
    from src.dashboard import TaskBoard

    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    assert "/action/chat" in page
    assert "location.reload" not in page


def test_terminal_popup_is_secondary_now(tmp_path):
    """T-033 的弹窗降级为次级入口：按钮还在，但主入口是展开面板。"""
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)

    result = board.run_action("handoff", {"task": "2026-09-27 10:00"})

    assert result.ok
    assert "面板" in result.output or "卡片下" in result.output

# ---------- 留档与三轮连贯（验收） ----------


def _stub_llm(monkeypatch, replies):
    """把 dsh 换成桩：每次调用返回下一句回答，并记录收到的 prompt。"""
    import subprocess
    import src.chat as chat

    seen = []

    def fake_run(command, **kwargs):
        seen.append(command[-1])
        reply = replies[min(len(seen) - 1, len(replies) - 1)]
        return subprocess.CompletedProcess(command, 0, reply + chr(10), "")

    monkeypatch.setattr(chat.subprocess, "run", fake_run)
    monkeypatch.setattr(chat, "find_dsh", lambda: "dsh")
    return seen


def test_chat_action_archives_both_roles(tmp_path, monkeypatch):
    directory = make_directory(tmp_path)
    seen = _stub_llm(monkeypatch, ["第一轮回答"])
    board = make_board(tmp_path, directory)

    result = board.run_action("chat", {"task": "2026-09-27 10:00", "message": "第一轮问题"})

    assert result.ok, result.output
    assert "第一轮回答" in result.output
    turns = load_turns(directory, "2026-09-27 10:00")
    assert [t.role for t in turns] == ["user", "assistant"]
    assert turns[0].text == "第一轮问题"
    assert "第一轮回答" in turns[1].text


def test_three_turns_stay_continuous(tmp_path, monkeypatch):
    """验收：连续三轮追问上下文连贯（第二轮能引用第一轮）。"""
    directory = make_directory(tmp_path)
    seen = _stub_llm(monkeypatch, ["回答一", "回答二", "回答三"])
    board = make_board(tmp_path, directory)

    for index in (1, 2, 3):
        result = board.run_action(
            "chat", {"task": "2026-09-27 10:00", "message": "问题" + str(index)}
        )
        assert result.ok, result.output

    # 第三轮的 prompt 里必须能看到前两轮问答
    third = seen[-1]
    assert "问题1" in third and "回答一" in third
    assert "问题2" in third and "回答二" in third
    assert "问题3" in third
    assert "DSH 接力上下文" in third, "handoff 每轮都要带上"
    turns = load_turns(directory, "2026-09-27 10:00")
    assert len(turns) == 6


def test_history_overflow_keeps_handoff_in_real_prompt(tmp_path, monkeypatch):
    """验收：历史超限后**不丢 handoff**，且超长部分走摘要而不是硬裁。

    T-043 起契约变了：走看板（有 LLM）时，最旧轮次会被压成「较早对话摘要」，
    不再打「已裁剪 N 轮」。硬裁只是**没有摘要器时**的兜底（见
    test_build_prompt_keeps_handoff_when_history_huge —— 那条是直调 build_prompt，
    没有 summarizer，所以那条的「已裁剪」断言仍然成立）。
    """
    from src import cli

    class SummaryCompleter:
        """摘要用的 LLM 桩：本用例要走「有摘要器」的路径，不能依赖真机有没有登录态（T-050）。"""

        def complete(self, messages):
            return "前几轮讨论的要点：学生在问名片页的结构"

    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: SummaryCompleter())
    directory = make_directory(tmp_path)
    seen = _stub_llm(monkeypatch, ["很长" * 4000])
    board = make_board(tmp_path, directory)

    for index in range(6):
        board.run_action("chat", {"task": "2026-09-27 10:00", "message": "问题" + str(index)})

    last = seen[-1]
    assert len(last) <= MAX_PROMPT_CHARS, "prompt 不能超上限"
    assert "DSH 接力上下文" in last, "handoff 全文不能被裁掉"
    assert "较早对话摘要" in last, "超长部分要压成摘要块"
    assert "已裁剪" not in last, "走摘要路径时不该再出现硬裁标记"
    # 摘要块里要有"覆盖了多少轮"的说明，便于判断丢了什么
    assert "已压缩成摘要" in last


def test_chat_action_reports_missing_handoff(tmp_path, monkeypatch):
    _stub_llm(monkeypatch, ["x"])
    from src import cli

    directory = tmp_path / "profile"
    directory.mkdir(parents=True)
    from src.profile import KnowledgeProfile, write_profile_atomic

    write_profile_atomic(directory / "knowledge.md", KnowledgeProfile())
    (directory / "tasks.md").write_text(
        "# 任务记录\n\n## 2026-09-27 10:00\n\n**目标**：x\n", encoding="utf-8")
    board = cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )

    result = board.run_action("chat", {"task": "2026-09-27 10:00", "message": "问题"})

    assert not result.ok
    assert "在 DSH 中继续" in result.output or "接力" in result.output


# ---------- REPL 交互模式 ----------


def test_chat_command_enters_repl_without_question(monkeypatch, capsys):
    """不带问题时进交互循环：提示符「你：」，exit 退出。"""
    import subprocess
    import src.chat as chat

    monkeypatch.setattr(chat, "find_dsh", lambda: "dsh")
    monkeypatch.setattr(
        chat.subprocess,
        "run",
        lambda command, **kw: subprocess.CompletedProcess(command, 0, "回答\n", ""),
    )

    from src import repl

    answers = []
    lines = iter(["第一个问题"])

    def reader(prompt):
        try:
            return next(lines)
        except StopIteration:
            raise EOFError

    code = repl.run_repl(
        ask=lambda text: answers.append(text) or "回答：" + text,
        read_line=reader,
        write=lambda text: None,
    )

    assert code == 0
    assert answers == ["第一个问题"]


def test_repl_exits_on_quit(monkeypatch):
    from src import repl

    lines = iter(["你好", "exit"])
    asked = []
    out = []

    def reader(prompt):
        try:
            return next(lines)
        except StopIteration:
            raise EOFError

    code = repl.run_repl(
        ask=lambda text: asked.append(text) or "答：" + text,
        read_line=reader,
        write=out.append,
    )

    assert code == 0
    assert asked == ["你好"]
    assert any("你：" in str(x) for x in out), "要有「你：」提示符"


def test_repl_handles_eof(monkeypatch):
    from src import repl

    code = repl.run_repl(
        ask=lambda text: "答",
        read_line=lambda prompt: None,
        write=lambda text: None,
    )

    assert code == 0


def test_repl_skips_blank_lines_and_quit_word():
    from src import repl

    lines = iter(["", "   ", "quit"])
    asked = []

    def reader(prompt):
        try:
            return next(lines)
        except StopIteration:
            raise EOFError

    repl.run_repl(
        ask=lambda text: asked.append(text) or "答",
        read_line=reader,
        write=lambda text: None,
    )

    assert asked == [], "空白行与 quit 都不该触发提问"


def test_repl_reports_ask_failure_without_exiting(monkeypatch):
    from src import repl

    lines = iter(["会失败", "再来", "exit"])
    calls = []
    out = []

    def reader(prompt):
        try:
            return next(lines)
        except StopIteration:
            raise EOFError

    def ask(text):
        calls.append(text)
        if len(calls) == 1:
            raise RuntimeError("dsh 挂了")
        return "第二次成功"

    code = repl.run_repl(ask=ask, read_line=reader, write=out.append)

    assert code == 0
    assert calls == ["会失败", "再来"], "一次失败不该退出循环"
    assert any("dsh 挂了" in str(x) for x in out)

def test_cli_chat_without_question_enters_repl(tmp_path, monkeypatch, capsys):
    """T-034 备选入口：不带问题进交互循环。"""
    import subprocess
    import src.chat as chat
    from src import cli
    from src.handoff import write_handoff
    from src.planner import read_task_records
    from src.profile import KnowledgeProfile, write_profile_atomic

    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    write_profile_atomic(directory / "knowledge.md", KnowledgeProfile())
    (directory / "tasks.md").write_text(
        "# 任务记录\n\n## 2026-09-27 10:00\n\n**目标**：x\n\n**验收方式**：y\n",
        encoding="utf-8",
    )
    record = read_task_records(directory / "tasks.md")[0]
    write_handoff(directory, record=record, code="c")

    monkeypatch.setattr(chat, "find_dsh", lambda: "dsh")
    monkeypatch.setattr(
        chat.subprocess,
        "run",
        lambda command, **kw: subprocess.CompletedProcess(command, 0, "交互回答\n", ""),
    )

    lines = iter(["追问一"])

    def reader(prompt):
        try:
            return next(lines)
        except StopIteration:
            raise EOFError

    monkeypatch.setattr("builtins.input", reader)

    code = cli.main(
        ["chat", "2026-09-27 10:00"],
        env_path=tmp_path / ".env",
        profile_path=directory / "knowledge.md",
    )
    out = capsys.readouterr()

    assert code == 0, out.err
    assert "交互回答" in out.out
    assert "你：" in out.out
    # T-036 起：进 REPL 会先自动问一条引导提问，所以留档是"首问+回答，再+追问+回答"
    turns = load_turns(directory, "2026-09-27 10:00")
    assert [t.role for t in turns] == ["user", "assistant", "user", "assistant"]
    assert "我的代码哪里不足" in turns[0].text, "第一条应是引导提问"
    assert turns[2].text == "追问一"


def test_cli_chat_single_shot_also_archives(tmp_path, monkeypatch, capsys):
    """T-034：单次模式也要留档。"""
    import subprocess
    import src.chat as chat
    from src import cli
    from src.handoff import write_handoff
    from src.planner import read_task_records
    from src.profile import KnowledgeProfile, write_profile_atomic

    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    write_profile_atomic(directory / "knowledge.md", KnowledgeProfile())
    (directory / "tasks.md").write_text(
        "# 任务记录\n\n## 2026-09-27 10:00\n\n**目标**：x\n\n**验收方式**：y\n",
        encoding="utf-8",
    )
    record = read_task_records(directory / "tasks.md")[0]
    write_handoff(directory, record=record, code="c")

    monkeypatch.setattr(chat, "find_dsh", lambda: "dsh")
    monkeypatch.setattr(
        chat.subprocess,
        "run",
        lambda command, **kw: subprocess.CompletedProcess(command, 0, "单次回答\n", ""),
    )

    code = cli.main(
        ["chat", "2026-09-27 10:00", "只问一次"],
        env_path=tmp_path / ".env",
        profile_path=directory / "knowledge.md",
    )
    capsys.readouterr()

    assert code == 0
    turns = load_turns(directory, "2026-09-27 10:00")
    assert [t.role for t in turns] == ["user", "assistant"]
    assert turns[0].text == "只问一次"

def test_archive_survives_headings_inside_answers(tmp_path):
    """实测 bug：回答里带 "## 小标题" 时，读回会多切出轮次（3 轮读成 9 轮）。"""
    directory = tmp_path / "profile"
    answer = "先看这段：\n\n## 你的问题\n\n缺少头像占位。\n\n### 建议\n\n加一个 div。"
    append_turn(directory, "2026-09-27 10:00", role="user", text="问一")
    append_turn(directory, "2026-09-27 10:00", role="assistant", text=answer)
    append_turn(directory, "2026-09-27 10:00", role="user", text="问二")
    append_turn(directory, "2026-09-27 10:00", role="assistant", text="答二")

    turns = load_turns(directory, "2026-09-27 10:00")

    assert [t.role for t in turns] == ["user", "assistant", "user", "assistant"], \
        "回答里的标题不能被当成分隔符"
    assert "缺少头像占位" in turns[1].text
    assert "加一个 div" in turns[1].text


def test_archive_roundtrip_keeps_long_multiline_answer(tmp_path):
    directory = tmp_path / "profile"
    body = "第一段。\n\n## 小节一\n\n- 要点一\n- 要点二\n\n## 小节二\n\n结尾。"
    append_turn(directory, "2026-09-27 10:00", role="assistant", text=body)

    turns = load_turns(directory, "2026-09-27 10:00")

    assert len(turns) == 1
    assert "小节二" in turns[0].text

# ---------- A 方案：展开面板不得自动启动子进程 ----------


def test_expanding_panel_does_not_auto_send() -> None:
    """A 方案（安全收口）：展开面板只显示输入框，**不自动调 dsh**。

    原因：dsh headless 是有工具权限的子进程、工作区是本仓库，
    会读项目文件（实测看到过它引用仓库里的 card.html），也可能写文件。
    所以第一次调用必须由用户按「发送」显式触发。
    """
    from src.dashboard import PANEL_JS

    # 精确定位 toggle 的 click 回调：从 addEventListener("click" 起配对花括号
    start = PANEL_JS.index('toggle.addEventListener("click"')
    open_brace = PANEL_JS.index("{", start)
    depth = 0
    end = open_brace
    for index in range(open_brace, len(PANEL_JS)):
        if PANEL_JS[index] == "{":
            depth += 1
        elif PANEL_JS[index] == "}":
            depth -= 1
            if depth == 0:
                end = index
                break
    handler = PANEL_JS[start:end]

    assert "chatSend(" not in handler, "展开回调里不能调用 chatSend 自动提问"


def test_panel_js_has_no_autostart_first_question() -> None:
    from src.dashboard import PANEL_JS

    compact = PANEL_JS.replace(" ", "")
    assert "chatStarted" not in compact, "不再需要自动首问标记"
    assert "我的代码哪里不足" not in PANEL_JS, "面板 JS 不应内置首问文案"


def test_panel_still_allows_manual_send() -> None:
    from src.dashboard import PANEL_JS

    assert "/action/chat" in PANEL_JS
    assert "chatSend(panel, text)" in PANEL_JS, "发送按钮仍要能触发一轮"


def test_panel_warns_about_subprocess_permissions(tmp_path) -> None:
    """面板上要如实写明：这会启动一个能读写本项目目录的 dsh 进程。"""
    from src.dashboard import TaskBoard

    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    assert "发送" in page
    assert "读写" in page or "权限" in page or "会启动" in page


def test_single_shot_cli_still_works(tmp_path, monkeypatch, capsys) -> None:
    """A 方案只改看板面板；CLI 的显式调用不受影响。"""
    import subprocess
    import src.chat as chat
    from src import cli
    from src.handoff import write_handoff
    from src.planner import read_task_records
    from src.profile import KnowledgeProfile, write_profile_atomic

    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    write_profile_atomic(directory / "knowledge.md", KnowledgeProfile())
    (directory / "tasks.md").write_text(
        "# 任务记录\n\n## 2026-09-27 10:00\n\n**目标**：x\n\n**验收方式**：y\n",
        encoding="utf-8",
    )
    record = read_task_records(directory / "tasks.md")[0]
    write_handoff(directory, record=record, code="c")
    monkeypatch.setattr(chat, "find_dsh", lambda: "dsh")
    monkeypatch.setattr(
        chat.subprocess, "run",
        lambda command, **kw: subprocess.CompletedProcess(command, 0, "答\n", ""),
    )

    code = cli.main(["chat", "2026-09-27 10:00", "显式提问"],
                    env_path=tmp_path / ".env", profile_path=directory / "knowledge.md")
    capsys.readouterr()

    assert code == 0