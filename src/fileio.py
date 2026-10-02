"""本地文件读写的两个公共动作：原子写、容错读。

项目约定（[[02-系统架构]]「接口与数据所有权」）：写入**先落临时文件再替换**，
任何一步失败都不留下半成品、不动旧文件。这条约定以前在 11 个模块里各写了一遍
（tmp = ...；write_text；replace；失败 unlink），这里收敛成一处。

各模块仍然用自己的异常类型报错（ProfileError / PlannerError / …）：
本模块只抛 OSError，由调用方包成带中文上下文的领域异常。
"""

from __future__ import annotations

import contextlib
from pathlib import Path

TMP_SUFFIX = ".tmp"


def tmp_path_for(path: Path | str) -> Path:
    """原子写用的临时文件：与目标同目录（同盘才能原子替换），名字加 .tmp 后缀。"""
    target = Path(path)
    return target.with_name(target.name + TMP_SUFFIX)


def write_text_atomic(path: Path | str, content: str) -> Path:
    """先写 <name>.tmp，成功后再替换目标；失败时删掉临时文件并原样抛出 OSError。

    父目录不存在会自动创建（建目录失败同样以 OSError 抛出）。
    """
    target = Path(path)
    tmp = tmp_path_for(target)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(target)
    except OSError:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        raise
    return target


def read_text_or_none(path: Path | str) -> str | None:
    """读 UTF-8 文本；文件不存在或读不了都返回 None（坏字节按 replace 处理）。

    用于「读不到就当没有」的场景（任务记录、错题本、对齐表……），
    调用方不必每处都写一遍 is_file + try/except OSError。
    """
    target = Path(path)
    if not target.is_file():
        return None
    try:
        return target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
