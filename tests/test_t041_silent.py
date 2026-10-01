"""T-041 失败测试：测试静默化（零弹窗）+ 真机用例打标。

客户痛点：跑 pytest 时真机子进程会弹控制台窗口。

两件事：
1. 真机子进程统一 **CREATE_NO_WINDOW**（Windows），或干脆直解析 npm shim 起 node.exe；
2. 真机用例打 **real** 标记，**默认跳过**；需要时 `pytest -m real` 才跑。

验收：pytest 全量零弹窗；`-m real` 时真机用例仍全过。
"""
from __future__ import annotations

import configparser
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
TESTS = ROOT / "tests"


def read(path: pathlib.Path) -> str:
    assert path.is_file(), "缺文件：" + str(path)
    return path.read_text(encoding="utf-8")


# ---------- 1. 静默执行工具 ----------


def test_silent_run_helper_exists():
    """要有统一的静默执行入口，不能各处自己拼 subprocess。"""
    module = SRC / "silent.py"
    assert module.is_file(), "缺 src/silent.py（静默执行工具）"


def test_silent_helper_defines_create_no_window():
    body = read(SRC / "silent.py")

    assert "CREATE_NO_WINDOW" in body
    assert "creationflags" in body


def test_silent_helper_is_noop_on_non_windows():
    """非 Windows 平台不该传 creationflags（会 TypeError）。"""
    from src.silent import SILENT_FLAGS, silent_kwargs

    import os

    kwargs = silent_kwargs()
    if os.name == "nt":
        assert kwargs.get("creationflags") == SILENT_FLAGS
    else:
        assert "creationflags" not in kwargs


def test_silent_flags_are_zero_off_windows():
    from src import silent

    import os

    if os.name != "nt":
        assert silent.SILENT_FLAGS == 0


def test_chat_uses_silent_kwargs():
    """chat_once 调 dsh 必须静默（这是最常被试跑的真机子进程）。"""
    body = read(SRC / "chat.py")

    assert "silent" in body, "chat.py 要走静默执行"
    assert "creationflags" in body or "silent_kwargs" in body


def test_no_bare_subprocess_run_left_in_chat():
    """chat.py 里不该再有裸 subprocess.run（除了经过静默包装的那一处）。"""
    body = read(SRC / "chat.py")

    calls = re.findall(r"subprocess\.run\(", body)
    assert len(calls) <= 1, "chat.py 里还有 " + str(len(calls)) + " 处裸 subprocess.run"


# ---------- 2. real 标记 ----------


def test_pytest_ini_registers_real_marker():
    body = read(ROOT / "pytest.ini")

    assert "real" in body, "pytest.ini 要注册 real 标记"
    assert "markers" in body


def test_real_tests_skipped_by_default():
    body = read(ROOT / "pytest.ini")

    assert "addopts" in body
    assert "real" in body.split("addopts")[1][:200], "addopts 里要默认排除 real"


def test_real_tests_are_marked():
    """打标的真机用例要真的存在，否则这条规则是空的。"""
    marked = []
    for path in TESTS.glob("test_*.py"):
        if "pytest.mark.real" in path.read_text(encoding="utf-8"):
            marked.append(path.name)

    assert marked, "没有任何用例打 real 标记"
    assert "test_t032_chat.py" in marked, "T-032 那条真机解析 shim 的用例应该打标"


def test_real_marker_available_at_runtime():
    """标记必须已注册，否则 pytest 会告警（--strict-markers 下直接失败）。"""
    config = configparser.ConfigParser()
    config.read(ROOT / "pytest.ini", encoding="utf-8")

    markers = config["pytest"].get("markers", "")
    assert "real" in markers


# ---------- 3. 测试自己也不许弹窗 ----------


def test_tests_do_not_spawn_windows_without_flags():
    """测试里的真机 subprocess 也要静默，否则 pytest 一跑就弹窗。"""
    # 用括号配平找出每个 subprocess.run(...) 的完整参数段，
    # 再看这段里有没有静默参数（简单窗口会被多行参数骗过去——我第一版就这么错的）。
    offenders = []
    for path in TESTS.glob("test_*.py"):
        # 跳过本文件：它自己就含 "subprocess.run(" 这个模式串，会误报
        if path.name == pathlib.Path(__file__).name:
            continue
        body = path.read_text(encoding="utf-8")
        for match in re.finditer(r"subprocess\.run\(", body):
            start = body.index("(", match.start())
            depth = 0
            end = start
            for index in range(start, len(body)):
                if body[index] == "(":
                    depth += 1
                elif body[index] == ")":
                    depth -= 1
                    if depth == 0:
                        end = index
                        break
            chunk = body[start:end]
            if "creationflags" in chunk or "silent_kwargs" in chunk:
                continue
            offenders.append(path.name + ":" + str(body[: match.start()].count(chr(10)) + 1))

    assert not offenders, "这些测试的 subprocess 没静默：" + str(offenders)


def test_plugin_contract_script_is_silent_safe():
    """插件契约脚本由 pytest 拉起，它自己也要能静默。"""
    body = read(ROOT / "tests" / "test_t039_contract.py")

    assert "silent" in body or "creationflags" in body


# ---------- 4. 真机用例清单可核对 ----------


def test_real_tests_are_documented():
    """README 或任务卡要写清哪些用例属于 real，便于交付说明。"""
    body = read(ROOT / "README.md")

    assert "-m real" in body, "README 要写怎么跑真机用例"
    assert "弹窗" in body or "静默" in body


def test_run_command_documented_with_marker():
    body = read(ROOT / "README.md")

    assert "pytest" in body
    assert re.search(r"pytest[^\n]*-m real", body), "要给出 -m real 的命令示例"

# ---------- 5. 真机证明：静默参数真的消掉控制台窗口（real 标记） ----------


@pytest.mark.real
@pytest.mark.skipif(sys.platform != "win32", reason="CREATE_NO_WINDOW 是 Windows 概念")
def test_create_no_window_really_suppresses_console():
    """真机对照：同一个子进程，加不加静默参数，控制台窗口的存在与否不同。

    子进程自己报 GetConsoleWindow()——这是**决定性**证据，
    比在外部数窗口可靠（外部枚举会被环境里已有的控制台淹掉）。
    """
    import subprocess as sp
    import sys as _sys

    from src.silent import silent_kwargs

    child = (
        "import ctypes;"
        "k=ctypes.windll.kernel32;"
        "print(1 if k.GetConsoleWindow() else 0)"
    )

    def has_console(**extra_kwargs) -> bool:
        done = sp.run(
            [_sys.executable, "-c", child],
            capture_output=True,
            text=True,
            encoding="utf-8",
            **extra_kwargs,
        )
        return done.stdout.strip() == "1"

    assert has_console() is True, "基线：不带静默参数时子进程应当有控制台窗口"
    assert has_console(**silent_kwargs()) is False, "带静默参数后不该再有控制台窗口"


@pytest.mark.real
@pytest.mark.skipif(sys.platform != "win32", reason="CREATE_NO_WINDOW 是 Windows 概念")
def test_real_spawn_site_passes_the_flag(monkeypatch):
    """真机 spawn 点（chat_once）确实把静默参数传下去了。"""
    import subprocess as sp

    import src.chat as chat
    from src.silent import silent_kwargs

    captured = {}

    def fake_run(command, **kwargs):
        captured.update(kwargs)
        return sp.CompletedProcess(command, 0, "答案", "")

    monkeypatch.setattr(chat.subprocess, "run", fake_run)
    chat.chat_once("dsh", "问题")

    assert captured.get("creationflags") == silent_kwargs().get("creationflags")