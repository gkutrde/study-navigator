"""T-039 契约测试驱动：跑 plugin/tests/learning.contract.mjs。

那条 Node 脚本用类型剥离**直接加载 plugin/src/server/learning.ts 源码**，
在真实仓库上校验：读画像/任务/地图 + 动作白名单 + 命令参数不被拼接。

放在 pytest 里跑，是为了让它进"全量测试"这道门——不然插件那半边会悄悄腐化。
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

from src.silent import silent_kwargs

SCRIPT = pathlib.Path("plugin") / "tests" / "learning.contract.mjs"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="没有 node")
def test_learning_contract_passes():
    assert SCRIPT.is_file(), "缺契约脚本：" + str(SCRIPT)

    # 用绝对路径：脚本内部会按自身位置推算仓库根，cwd 设成 plugin 更贴近真实运行
    done = subprocess.run(
        [NODE, str(SCRIPT.resolve())],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(SCRIPT.resolve().parent.parent),
        timeout=120,
        # T-041：静默执行，跑测试时不弹控制台窗口
        **silent_kwargs(),
    )

    assert done.returncode == 0, done.stdout + done.stderr
    assert "ALL CHECKS PASSED" in done.stdout, done.stdout
    # 契约脚本必须真的跑了检查，不能是空跑
    assert done.stdout.count("PASS ") >= 15, done.stdout
    assert "FAIL " not in done.stdout, done.stdout


@pytest.mark.skipif(NODE is None, reason="没有 node")
def test_contract_is_wired_into_suite():
    """这条测试存在的意义：插件那半边的安全不变量也进全量测试。"""
    script = SCRIPT.read_text(encoding="utf-8")

    assert "rc -rf" not in script
    assert "unknown_action_rejected" in script
    assert "user_input_stays_whole_arg" in script
