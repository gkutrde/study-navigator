"""T-032 失败测试：chat 命令（终端接力）。

任务卡要求：
- `python -m src.cli chat <任务时间戳> "问题"`
- 读 profile/handoff/<对应文件>.md，组装「上下文 + 问题」为**单段 prompt**
- 用 **subprocess 列表参数**调 `dsh --profile headless`（**不走 shell**，防注入）
- **透传**其输出
- handoff 文件不存在 → 提示先去点「在 DSH 中继续」
- dsh 未安装 → 中文提示
- prompt 超 **30000** 字符 → 截断并注明
"""

from __future__ import annotations
from src.silent import silent_kwargs

import os
import subprocess
from pathlib import Path

import pytest

from src.chat import (
    MAX_PROMPT_CHARS,
    ChatError,
    assemble_prompt,
    build_dsh_command,
    chat_once,
    find_dsh,
    read_handoff,
)

CONTEXT = "# DSH 接力上下文\n\n## 一、任务卡\n\n- **目标**：做名片页\n"


def make_profile_dir(tmp_path, body=CONTEXT, when="2026-09-27 10:00"):
    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    from src.handoff import handoff_dir, task_file_id

    target = handoff_dir(directory) / (task_file_id(when) + ".md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return directory, target


# ---------- 1. 读上下文 ----------


def test_read_handoff_returns_file_text(tmp_path):
    directory, target = make_profile_dir(tmp_path)

    assert read_handoff(directory, "2026-09-27 10:00") == CONTEXT


def test_read_handoff_missing_file_raises_with_hint(tmp_path):
    """没有 handoff 文件时要明确告诉用户先去点按钮。"""
    directory = tmp_path / "profile"
    directory.mkdir(parents=True)

    with pytest.raises(ChatError) as exc:
        read_handoff(directory, "2026-09-27 10:00")

    message = str(exc.value)
    assert "在 DSH 中继续" in message
    assert "handoff" in message.lower()


def test_read_handoff_empty_timestamp_raises(tmp_path):
    directory, _ = make_profile_dir(tmp_path)

    with pytest.raises(ChatError):
        read_handoff(directory, "")


# ---------- 2. 组装单段 prompt ----------


def test_assemble_prompt_is_single_string_with_both_parts():
    prompt = assemble_prompt(CONTEXT, "我的代码哪里不足？")

    assert isinstance(prompt, str)
    assert CONTEXT.strip() in prompt
    assert "我的代码哪里不足？" in prompt


def test_assemble_prompt_puts_question_after_context():
    prompt = assemble_prompt(CONTEXT, "问题在这里")

    assert prompt.index("目标") < prompt.index("问题在这里")


def test_assemble_prompt_rejects_blank_question():
    with pytest.raises(ChatError):
        assemble_prompt(CONTEXT, "   ")


def test_assemble_prompt_truncates_long_context_and_says_so():
    long_context = "x" * (MAX_PROMPT_CHARS + 5000)

    prompt = assemble_prompt(long_context, "问题")

    assert len(prompt) <= MAX_PROMPT_CHARS
    assert "截断" in prompt
    assert "问题" in prompt, "问题不能被截掉"


def test_assemble_prompt_keeps_short_prompt_untouched():
    prompt = assemble_prompt(CONTEXT, "短问题")

    assert "截断" not in prompt


# ---------- 3. 命令构造：列表参数，不走 shell ----------


def test_build_dsh_command_uses_list_args():
    command = build_dsh_command("/usr/bin/dsh", "一段 prompt")

    assert isinstance(command, list)
    assert command[0] == "/usr/bin/dsh"
    assert "--profile" in command and "headless" in command
    assert command[-1] == "一段 prompt"


def test_build_dsh_command_does_not_interpolate_prompt():
    """prompt 只能是一个独立参数，不能拼进别的参数里（防注入）。"""
    danger = "hello; rm -rf / && echo $(whoami) | cat"

    command = build_dsh_command("dsh", danger)

    assert any(arg == danger for arg in command), "prompt 必须是完整独立的参数"
    assert not any(danger in arg and arg != danger for arg in command)


def test_find_dsh_returns_none_when_absent(monkeypatch):
    monkeypatch.setattr("src.chat.shutil.which", lambda _name: None)

    assert find_dsh() is None


def test_find_dsh_prefers_which(monkeypatch):
    monkeypatch.setattr("src.chat.shutil.which", lambda _name: "C:/fake/dsh.exe")

    assert find_dsh() == "C:/fake/dsh.exe"


# ---------- 4. 调 dsh：列表参数 + 透传输出 ----------


def test_chat_once_uses_subprocess_without_shell(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, "答案在这里\n", "")

    monkeypatch.setattr("src.chat.subprocess.run", fake_run)

    result = chat_once("dsh", "上下文 + 问题")

    assert result == "答案在这里\n"
    assert isinstance(captured["command"], list)
    assert captured["kwargs"].get("shell") in (None, False), "绝不能走 shell"


def test_chat_once_returns_stderr_when_failed(monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, "", "出错了：模型不可用\n")

    monkeypatch.setattr("src.chat.subprocess.run", fake_run)

    with pytest.raises(ChatError) as exc:
        chat_once("dsh", "问题")

    assert "模型不可用" in str(exc.value)


def test_chat_once_missing_executable_gives_chinese_hint(monkeypatch):
    def fake_run(command, **kwargs):
        raise FileNotFoundError("dsh")

    monkeypatch.setattr("src.chat.subprocess.run", fake_run)

    with pytest.raises(ChatError) as exc:
        chat_once("dsh", "问题")

    assert "dsh" in str(exc.value)
    assert "安装" in str(exc.value) or "找不到" in str(exc.value)


def test_chat_once_timeout_is_reported(monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr("src.chat.subprocess.run", fake_run)

    with pytest.raises(ChatError) as exc:
        chat_once("dsh", "问题")

    assert "超时" in str(exc.value)


# ---------- 5. 端到端（打桩 subprocess） ----------


def test_end_to_end_answer_is_relayed(tmp_path, monkeypatch):
    directory, _ = make_profile_dir(tmp_path)
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        return subprocess.CompletedProcess(command, 0, "✓ 回答正文\n", "")

    monkeypatch.setattr("src.chat.subprocess.run", fake_run)

    answer = chat_once("dsh", assemble_prompt(read_handoff(directory, "2026-09-27 10:00"), "我哪里不足"))

    assert answer.strip() == "✓ 回答正文"
    assert "我哪里不足" in seen["command"][-1]
    assert "DSH 接力上下文" in seen["command"][-1]

# ---------- 6. CLI 层 ----------


def _make_cli_env(tmp_path, monkeypatch, answer="✓ 回答\n"):
    """准备一个带 handoff 文件的临时画像，并把 subprocess 打桩。"""
    from src import cli
    from src.profile import KnowledgeProfile, write_profile_atomic
    from src.handoff import handoff_dir, task_file_id

    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    write_profile_atomic(directory / "knowledge.md", KnowledgeProfile())
    target = handoff_dir(directory) / (task_file_id("2026-09-27 10:00") + ".md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(CONTEXT, encoding="utf-8")

    calls = {}

    def fake_run(command, **kwargs):
        calls["command"] = command
        calls["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, answer, "")

    monkeypatch.setattr("src.chat.subprocess.run", fake_run)
    monkeypatch.setattr("src.chat.find_dsh", lambda: "C:/fake/dsh.cmd")
    return cli, directory, calls


def test_cli_chat_relays_answer(tmp_path, monkeypatch, capsys):
    cli, directory, calls = _make_cli_env(tmp_path, monkeypatch)

    code = cli.main(
        ["chat", "2026-09-27 10:00", "我的代码哪里不足？"],
        env_path=tmp_path / ".env",
        profile_path=directory / "knowledge.md",
    )
    out = capsys.readouterr()

    assert code == 0
    assert "✓ 回答" in out.out
    command = calls["command"]
    # Windows 上 .cmd 必须经 cmd.exe 执行（实测 FileNotFoundError），
    # POSIX 上就是可执行文件本身。
    if command[0].lower().endswith(("cmd.exe", "cmd")):
        assert command[1] == "/c"
        assert command[2] == "C:/fake/dsh.cmd"
        head = 3
    else:
        assert command[0] == "C:/fake/dsh.cmd"
        head = 1
    assert command[head:head + 2] == ["--profile", "headless"], command
    assert "我的代码哪里不足" in command[-1]
    assert "DSH 接力上下文" in command[-1]
    assert calls["kwargs"].get("shell") in (None, False)


def test_cli_chat_arity(tmp_path, capsys):
    """T-032 时 chat 必须两个参数；T-034 起**一个参数 = 进交互模式**。"""
    from src import cli

    # 一个参数不再算"参数错"：会去找 handoff（找不到就是运行期失败，退 1）
    one = cli.main(["chat", "2026-09-27 10:00"], env_path=tmp_path / ".env")
    capsys.readouterr()
    assert one == 1, "一个参数应进交互模式（这里因缺 handoff 退 1）"

    # 三个参数仍然是用法错误
    many = cli.main(["chat", "2026-09-27 10:00", "问题", "多余的"], env_path=tmp_path / ".env")
    err = capsys.readouterr().err
    assert many == 2
    assert "chat" in err


def test_cli_chat_missing_handoff_hints_button(tmp_path, monkeypatch, capsys):
    from src import cli
    from src.profile import KnowledgeProfile, write_profile_atomic

    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    write_profile_atomic(directory / "knowledge.md", KnowledgeProfile())
    monkeypatch.setattr("src.chat.find_dsh", lambda: "dsh")

    code = cli.main(
        ["chat", "2026-09-27 10:00", "问题"],
        env_path=tmp_path / ".env",
        profile_path=directory / "knowledge.md",
    )
    err = capsys.readouterr().err

    assert code == 1
    assert "在 DSH 中继续" in err


def test_cli_chat_without_dsh_gives_chinese_hint(tmp_path, monkeypatch, capsys):
    from src import cli
    from src.profile import KnowledgeProfile, write_profile_atomic
    from src.handoff import handoff_dir, task_file_id

    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    write_profile_atomic(directory / "knowledge.md", KnowledgeProfile())
    target = handoff_dir(directory) / (task_file_id("2026-09-27 10:00") + ".md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(CONTEXT, encoding="utf-8")
    monkeypatch.setattr("src.chat.find_dsh", lambda: None)

    code = cli.main(
        ["chat", "2026-09-27 10:00", "问题"],
        env_path=tmp_path / ".env",
        profile_path=directory / "knowledge.md",
    )
    err = capsys.readouterr().err

    assert code == 1
    assert "dsh" in err
    assert "安装" in err or "找不到" in err


def test_chat_is_a_known_command(tmp_path):
    from src import cli

    assert "chat" in cli.KNOWN_COMMANDS

def test_cli_chat_accepts_profile_override(tmp_path, monkeypatch, capsys):
    """--profile 要和别的子命令一样可用（第一次实测时就踩到：chat 直接拒了它）。"""
    from src import cli
    from src.profile import KnowledgeProfile, write_profile_atomic
    from src.handoff import handoff_dir, task_file_id
    import subprocess

    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    write_profile_atomic(directory / "knowledge.md", KnowledgeProfile())
    target = handoff_dir(directory) / (task_file_id("2026-09-27 10:00") + ".md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(CONTEXT, encoding="utf-8")

    monkeypatch.setattr("src.chat.find_dsh", lambda: "dsh")
    monkeypatch.setattr(
        "src.chat.subprocess.run",
        lambda command, **kw: subprocess.CompletedProcess(command, 0, "✓ ok\n", ""),
    )

    code = cli.main(
        ["chat", "2026-09-27 10:00", "问题", "--profile", str(directory / "knowledge.md")],
        env_path=tmp_path / ".env",
    )
    out = capsys.readouterr()

    assert code == 0, out.err
    assert "✓ ok" in out.out

def test_headless_persona_override_detected(tmp_path):
    """profile 里有 personaPrefix 时要能识别出来（好如实提醒用户）。"""
    from src.chat import headless_persona_override

    root = tmp_path / ".dsh"
    patch = root / "profiles" / "headless" / "cordis.patch.yml"
    patch.parent.mkdir(parents=True, exist_ok=True)
    patch.write_text("personaPrefix: |\n  你是 ENI。\n", encoding="utf-8")

    assert headless_persona_override(root) is not None


def test_headless_persona_override_absent(tmp_path):
    from src.chat import headless_persona_override

    root = tmp_path / ".dsh"
    patch = root / "profiles" / "headless" / "cordis.patch.yml"
    patch.parent.mkdir(parents=True, exist_ok=True)
    patch.write_text("plugins: []\n", encoding="utf-8")

    assert headless_persona_override(root) is None


def test_cli_chat_warns_about_persona_override(tmp_path, monkeypatch, capsys):
    """有覆盖时要在 stderr 提醒——不能让用户以为答案可信。"""
    from src import cli
    from src.profile import KnowledgeProfile, write_profile_atomic
    from src.handoff import handoff_dir, task_file_id
    import subprocess

    home = tmp_path / ".dsh"
    patch = home / "profiles" / "headless" / "cordis.patch.yml"
    patch.parent.mkdir(parents=True, exist_ok=True)
    patch.write_text("personaPrefix: |\n  你是 ENI。\n", encoding="utf-8")
    monkeypatch.setenv("DSH_HOME", str(home))

    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    write_profile_atomic(directory / "knowledge.md", KnowledgeProfile())
    target = handoff_dir(directory) / (task_file_id("2026-09-27 10:00") + ".md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(CONTEXT, encoding="utf-8")
    monkeypatch.setattr("src.chat.find_dsh", lambda: "dsh")
    monkeypatch.setattr(
        "src.chat.subprocess.run",
        lambda command, **kw: subprocess.CompletedProcess(command, 0, "答案\n", ""),
    )

    code = cli.main(
        ["chat", "2026-09-27 10:00", "问题"],
        env_path=tmp_path / ".env",
        profile_path=directory / "knowledge.md",
    )
    err = capsys.readouterr().err

    assert code == 0
    assert "人设" in err or "persona" in err.lower()


def test_cli_chat_no_warning_without_override(tmp_path, monkeypatch, capsys):
    from src import cli
    from src.profile import KnowledgeProfile, write_profile_atomic
    from src.handoff import handoff_dir, task_file_id
    import subprocess

    home = tmp_path / ".dsh"
    patch = home / "profiles" / "headless" / "cordis.patch.yml"
    patch.parent.mkdir(parents=True, exist_ok=True)
    patch.write_text("plugins: []\n", encoding="utf-8")
    monkeypatch.setenv("DSH_HOME", str(home))

    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    write_profile_atomic(directory / "knowledge.md", KnowledgeProfile())
    target = handoff_dir(directory) / (task_file_id("2026-09-27 10:00") + ".md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(CONTEXT, encoding="utf-8")
    monkeypatch.setattr("src.chat.find_dsh", lambda: "dsh")
    monkeypatch.setattr(
        "src.chat.subprocess.run",
        lambda command, **kw: subprocess.CompletedProcess(command, 0, "答案\n", ""),
    )

    code = cli.main(
        ["chat", "2026-09-27 10:00", "问题"],
        env_path=tmp_path / ".env",
        profile_path=directory / "knowledge.md",
    )
    err = capsys.readouterr().err

    assert code == 0
    assert "人设" not in err

def test_build_dsh_command_wraps_cmd_on_windows(monkeypatch):
    """Windows 上 .cmd/.bat 必须经命令解释器执行，否则 CreateProcess 找不到文件。

    实测：find_dsh() 返回 dsh.CMD，直接 subprocess 跑会 FileNotFoundError。
    """
    import src.chat as chat

    monkeypatch.setattr(chat.os, "name", "nt")
    monkeypatch.setenv("COMSPEC", r"C:\Windows\system32\cmd.exe")

    command = chat.build_dsh_command(r"C:\npm\dsh.CMD", "问题")

    assert command[0].lower().endswith("cmd.exe")
    assert command[1] == "/c"
    assert command[2] == r"C:\npm\dsh.CMD"
    assert command[-1] == "问题"


def test_build_dsh_command_leaves_exe_alone_on_windows(monkeypatch):
    import src.chat as chat

    monkeypatch.setattr(chat.os, "name", "nt")

    command = chat.build_dsh_command(r"C:\npm\dsh.exe", "问题")

    assert command[0] == r"C:\npm\dsh.exe"
    assert "/c" not in command


# ---------- 8. Windows 传参：换行不许被 cmd.exe 吃掉（2026-09-29 回归） ----------
#
# 现场：`chat` 发出去的 prompt 从**第一个换行处**被切断，五段接力上下文和【我的问题】
# 整段丢失，而 returncode 仍是 0 → 静默答非所问。根因是 cmd.exe 把参数里的 \n
# 当命令分隔符。下面三条测试把这个坑钉住。

SHIM_TEMPLATE = (
    "@ECHO off\r\nGOTO start\r\n:find_dp0\r\nSET dp0=%~dp0\r\nEXIT /b\r\n:start\r\nSETLOCAL\r\n"
    "CALL :find_dp0\r\n\r\n"
    'IF EXIST "%dp0%\\node.exe" (\r\n  SET "_prog=%dp0%\\node.exe"\r\n) ELSE (\r\n'
    '  SET "_prog=node"\r\n)\r\n\r\n'
    'endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & "%_prog%"  '
    '"%dp0%\\node_modules\\@deepseek-ai\\dsh\\lib\\bin.js" %*\r\n'
)

MULTILINE_PROMPT = "第一行\n\n## 一、任务卡\n- **目标**：点名册\n\n【我的问题】我的代码哪里不足？"


def make_npm_shim(tmp_path, *, with_local_node=True, with_entry=True):
    """造一个和 npm 生成的一模一样的 dsh.cmd 骨架，附一个假 node/bin.js。"""
    npm_dir = tmp_path / "npm"
    entry = npm_dir / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
    entry.parent.mkdir(parents=True, exist_ok=True)
    if with_entry:
        entry.write_text("// fake dsh entry\n", encoding="utf-8")
    if with_local_node:
        (npm_dir / "node.exe").write_bytes(b"MZ fake")
    shim = npm_dir / "dsh.cmd"
    shim.write_text(SHIM_TEMPLATE, encoding="utf-8")
    return shim, npm_dir, entry


def test_shim_resolves_to_node_entry_and_keeps_newlines(tmp_path, monkeypatch):
    """能解析 shim 时必须**直接起 node + bin.js**，prompt 里的换行完整保留。"""
    import src.chat as chat

    shim, npm_dir, entry = make_npm_shim(tmp_path)
    monkeypatch.setattr(chat.os, "name", "nt")

    resolved = chat._resolve_npm_shim_entry(str(shim))
    assert resolved == (str(npm_dir / "node.exe"), str(entry))

    command = chat.build_dsh_command(str(shim), MULTILINE_PROMPT)

    assert command[:4] == [str(npm_dir / "node.exe"), str(entry), "--profile", "headless"]
    assert "/c" not in command  # 不经过 cmd.exe
    assert command[-1] == MULTILINE_PROMPT  # 换行原样保留
    assert "\n" in command[-1]


def test_shim_prog_falls_back_to_path_node(tmp_path, monkeypatch):
    """真机走的是 ELSE 分支（%dp0%\\node.exe 不存在）：必须退到 PATH 里的 node。

    实测踩过：只取第一个 SET 候选会误判成「解析失败」，白退回 cmd 那条有截断的路。
    """
    import src.chat as chat

    shim, npm_dir, entry = make_npm_shim(tmp_path, with_local_node=False)
    monkeypatch.setattr(chat.os, "name", "nt")
    monkeypatch.setattr(chat.shutil, "which", lambda name: r"C:\fake\node.exe" if name == "node" else None)

    assert chat._resolve_npm_shim_entry(str(shim)) == (r"C:\fake\node.exe", str(entry))


def test_unresolvable_shim_falls_back_to_cmd_without_newlines(tmp_path, monkeypatch):
    """解析不出（bin.js 不在）→ 退回 cmd，但必须折行并**注明**，不许静默改动材料。"""
    import src.chat as chat

    shim, _npm_dir, _entry = make_npm_shim(tmp_path, with_entry=False)
    monkeypatch.setattr(chat.os, "name", "nt")
    monkeypatch.setenv("COMSPEC", r"C:\Windows\system32\cmd.exe")

    command = chat.build_dsh_command(str(shim), MULTILINE_PROMPT)

    assert command[0].lower().endswith("cmd.exe")
    assert command[1] == "/c"
    assert command[2] == str(shim)
    assert "\n" not in command[-1] and "\r" not in command[-1]
    assert chat.FLATTEN_NOTICE in command[-1]


def test_flatten_leaves_single_line_prompt_untouched():
    import src.chat as chat

    assert chat._flatten_for_cmd("问题") == "问题"
    assert chat._flatten_for_cmd("  我的代码哪里不足？  ") == "我的代码哪里不足？"


@pytest.mark.real
@pytest.mark.skipif(os.name != "nt", reason="cmd.exe 的参数解析规则是 Windows 特有行为")
def test_cmd_truncates_multiline_prompt_but_flatten_survives():
    """这个 bug 的**现场守卫**：cmd.exe 真的会切断多行参数，折行后才全须全尾。

    靶子用 `python -c` 打印收到的参数长度；`node` 之类直接走 PATH 名字，
    避免全路径含空格时撞上 cmd 的引号剥除规则（那是另一个坑，见下条测试）。
    """
    import src.chat as chat

    probe = "import sys;print(len(sys.argv[1]))"

    def delivered_length(argument: str) -> int:
        completed = subprocess.run(
            [os.environ.get("COMSPEC", "cmd.exe"), "/c", "python", "-c", probe, argument],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **silent_kwargs(),
        )
        assert completed.returncode == 0, completed.stderr
        return int(completed.stdout.strip())

    # 1) 多行 prompt 经 cmd.exe → 只剩第一个换行之前的部分（就是现场那个静默截断）
    assert delivered_length(MULTILINE_PROMPT) == len("第一行")
    # 2) 折成单行后 → 一个字符都不少
    flattened = chat._flatten_for_cmd(MULTILINE_PROMPT)
    assert delivered_length(flattened) == len(flattened)


@pytest.mark.real
@pytest.mark.skipif(os.name != "nt", reason="npm shim 只在 Windows 上")
def test_real_npm_shim_on_this_machine_resolves():
    """本机真 shim（若 dsh 是 npm 装的）必须解析得动；解析不动就会退回有截断风险的 cmd。"""
    import src.chat as chat

    shim = find_dsh()
    if not shim or not shim.lower().endswith((".cmd", ".bat")):
        pytest.skip("本机没装 npm 版 dsh（find_dsh 没给出 .cmd）")

    resolved = chat._resolve_npm_shim_entry(shim)

    assert resolved is not None, f"解析不出 {shim} 的真实入口，会退回 cmd 路径"
    node, entry = resolved
    assert Path(node).is_file()
    assert Path(entry).is_file()
    assert entry.lower().endswith(".js")