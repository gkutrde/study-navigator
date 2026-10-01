"""T-041 静默执行：真机子进程一律不弹控制台窗口。

背景：跑 pytest 时，任何真机子进程（dsh、node、python -m src.cli）在 Windows 上
都会弹一个控制台窗口——跑一次全量测试能弹好几次。

做法：统一往 subprocess 调用里加 "creationflags=CREATE_NO_WINDOW"。
非 Windows 上传这个参数会 TypeError，所以用 silent_kwargs() 统一兜住平台差异。
"""
from __future__ import annotations

import os
import subprocess
from typing import Any


# Windows 上 CREATE_NO_WINDOW 的常量值（0x08000000）。
# 不直接用 subprocess.CREATE_NO_WINDOW，是因为它在非 Windows 上不存在——
# 用常量可以让本模块在 Linux/macOS 上也能 import。
CREATE_NO_WINDOW = 0x08000000

# 只在 Windows 上生效；其它平台是 0（等于不传）
SILENT_FLAGS = CREATE_NO_WINDOW if os.name == "nt" else 0


def silent_kwargs() -> dict[str, Any]:
    """返回要合并进 subprocess 调用的静默参数。

    用法：subprocess.run(cmd, **silent_kwargs(), capture_output=True)
    """
    if os.name == "nt":
        return {"creationflags": SILENT_FLAGS}
    return {}


def run_silent(command, **kwargs):
    """静默版 subprocess.run（自动带上平台正确的静默参数）。"""
    merged = silent_kwargs()
    # 调用方显式给的 creationflags 优先（便于测试覆盖）
    merged.update(kwargs)
    return subprocess.run(command, **merged)


def popen_silent(command, **kwargs):
    """静默版 subprocess.Popen。"""
    merged = silent_kwargs()
    merged.update(kwargs)
    return subprocess.Popen(command, **merged)
