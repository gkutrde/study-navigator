'''T-033 自动弹终端：点「在 DSH 中继续」时顺手开一个问好的终端窗口。

设计要点：
- 用 cmd /c start + 空标题 + cmd /k，让窗口留着继续追问；
- 列表参数、不走 shell；
- 非 Windows / 没装 cmd / 弹窗失败，一律静默返回 False。
'''

from __future__ import annotations

import os
import subprocess
import sys


class TerminalError(Exception):
    '''保留给需要显式报错的调用方。'''


# 弹窗后自动问的第一条
FIRST_QUESTIONS = (
    "我的代码哪里不足？请对照验收方式逐条指出不达标的地方，并给出最小修改建议。",
    "我该看书的哪部分？请给出书名和章节，并说明重点看什么。",
)


# cmd 下需要加双引号的字符（含空格）
_SPECIAL = " \t&()[]{}^=;!+'`~"


def quote_for_cmd(token: str) -> str:
    '按 cmd 规则给一个参数加引号。'
    text = str(token)
    if not text:
        return '""'
    if text.startswith('"') and text.endswith('"'):
        return text
    # 已经有引号的就不重包；其余只要含特殊字符或引号就包起来
    if '"' not in text and not any(ch in text for ch in _SPECIAL):
        return text
    return '"' + text.replace('"', '""') + '"'

def build_chat_command_line(
    executable: str,
    when: str,
    question: str | None = None,
    *,
    profile_path: str | None = None,
) -> str:
    '''构造要交给 cmd /k 的一条命令。'''
    parts = [
        quote_for_cmd(executable),
        "-m",
        "src.cli",
        "chat",
        quote_for_cmd(str(when)),
        quote_for_cmd(question or FIRST_QUESTIONS[0]),
    ]
    if profile_path:
        parts.extend(["--profile", quote_for_cmd(str(profile_path))])
    return " ".join(parts)


def build_start_argv(
    executable: str,
    when: str,
    question: str | None = None,
    *,
    profile_path: str | None = None,
) -> list[str]:
    '''cmd /c start + 空标题 + cmd /k 的 argv。'''
    comspec = os.environ.get("COMSPEC") or "cmd.exe"
    line = build_chat_command_line(executable, when, question, profile_path=profile_path)
    return [comspec, "/c", "start", "", "cmd", "/k", line]


def launch_chat_terminal(
    executable: str,
    when: str,
    question: str | None = None,
    *,
    profile_path: str | None = None,
) -> bool:
    '''尝试弹一个终端窗口；任何失败都返回 False。'''
    if os.name != "nt":
        return False
    try:
        argv = build_start_argv(executable, when, question, profile_path=profile_path)
        subprocess.Popen(argv, shell=False, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, close_fds=True)
    except Exception:
        return False
    return True


def current_python() -> str:
    '''当前解释器路径。'''
    return sys.executable or "python"
