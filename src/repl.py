"""T-034 备选入口：终端 REPL 交互模式。

`chat <时间戳>` 不带问题时进交互循环（提示符「你：」，exit/quit 退出）；
带问题则保持 T-032 的单次模式。

设计成可注入的（ask / read_line / write），所以循环逻辑本身不依赖终端，也便于测试。
"""
from __future__ import annotations

import sys


PROMPT = "你："
EXIT_WORDS = ("exit", "quit", ":q", "q")
BANNER = "进入交互模式：直接输入追问，输入 exit 或 quit 退出。"


def _ask_and_show(ask, writer, text: str) -> None:
    """问一次并把结果写出去；失败只提示，不抛出。"""
    try:
        answer = ask(text)
    except Exception as exc:
        writer("这一轮失败了：" + str(exc) + "（可以继续问，或 exit 退出）")
        return
    writer(str(answer).rstrip())
    writer("")


def run_repl(*, ask, read_line=None, write=None, initial: str | None = None) -> int:
    """跑交互循环。ask(text) -> 回答字符串；ask 抛异常只提示，不退出循环。

    initial（T-036）：启动时先自动问一条（弹窗用首条引导提问），
    这样用户打开窗口就能看到回答、然后停在「你：」等追问。
    首问失败也不能把循环废掉——一次网络抖动不该让窗口没法用。
    """
    reader = read_line or (lambda prompt: input(prompt))
    writer = write or (lambda text: print(text))

    writer(BANNER)
    if initial and str(initial).strip():
        _ask_and_show(ask, writer, str(initial).strip())
    while True:
        # 提示符也写进输出流：这样调用方（以及非交互场景的日志）能看到对话边界，
        # 而不是只有真人对着终端才知道"轮到我说话了"。
        writer(PROMPT)
        try:
            line = reader(PROMPT)
        except (EOFError, KeyboardInterrupt):
            writer("")
            return 0

        if line is None:
            return 0
        text = str(line).strip()
        if not text:
            continue
        if text.lower() in EXIT_WORDS:
            return 0

        _ask_and_show(ask, writer, text)
