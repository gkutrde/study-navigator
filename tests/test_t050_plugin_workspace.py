"""T-050 插件：只在「学习领航员」工作区启用（客户端注入 + 服务端路由都按工作区过滤）。

两条 Node 契约脚本进全量测试这道门：
- plugin/tests/learning.contract.mjs：服务端（源码，类型剥离加载）——工作区核验、默认项目根、白名单；
- plugin/tests/client.contract.mjs：客户端（**构建产物** lib/client.js）——工作区过滤、讨论会话建法、slot 注册。

另外核对两半与 Python 核心之间的一处"同一规则两份实现"：handoff 文件名
（TS 的 taskFileId 必须与 Python 的 handoff.task_file_id 逐字一致，否则「讨论」读不到接力文件）。
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess

import pytest

from src.silent import silent_kwargs

PLUGIN = pathlib.Path("plugin")
NODE = shutil.which("node")
requires_node = pytest.mark.skipif(NODE is None, reason="没有 node")


def read(rel: str) -> str:
    return (PLUGIN / rel).read_text(encoding="utf-8")


def run_node(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [NODE, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(PLUGIN.resolve()),
        timeout=120,
        **silent_kwargs(),
    )


@requires_node
def test_client_contract_passes():
    done = run_node(str((PLUGIN / "tests" / "client.contract.mjs").resolve()))

    assert done.returncode == 0, done.stdout + done.stderr
    assert "ALL CHECKS PASSED" in done.stdout
    assert done.stdout.count("PASS ") >= 25, done.stdout
    assert "FAIL " not in done.stdout


@requires_node
def test_server_contract_covers_workspace_gate():
    script = read("tests/learning.contract.mjs")
    for name in ("gate_rejects_other_workspace", "gate_fails_closed_without_registry", "serve_ignores_forged_title"):
        assert name in script


@requires_node
def test_handoff_file_id_matches_python():
    from src.handoff import task_file_id

    stamps = ["2026-09-27 10:30", "2026-09-27 10:30:15", "2026-9-7 9:05", "复习：列表 10:00", "../../etc/passwd 10:30"]
    probe = (
        "const m = await import(new URL('./src/server/learning.ts', 'file:///' + process.cwd().replace(/\\\\/g, '/') + '/'));"
        "console.log(JSON.stringify(" + json.dumps(stamps) + ".map((s) => m.taskFileId(s))))"
    )
    done = run_node("--input-type=module", "-e", probe)

    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == [task_file_id(stamp) for stamp in stamps]


def test_server_injects_workspace_registry():
    body = read("src/index.ts")
    match = re.search(r"export\s+const\s+inject\s*=\s*\[([^\]]*)\]", body)
    assert match and "workspaceRegistry" in match.group(1), "服务端要注入 workspaceRegistry 才能按工作区过滤"


def test_client_only_mounts_input_dock():
    """0.2.0 起 conversation.session.header.actions 会真的渲染：整块面板不能再挂过去。"""
    body = read("src/client/index.tsx")
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", body, flags=re.S)

    assert "'conversation.session.header.actions'" not in code
    assert "SLOTS = [SLOT]" in code


def test_client_sends_workspace_with_every_request():
    body = read("src/client/index.tsx")

    assert "workspaceId" in body
    assert "learningWorkspaceOf" in body


def test_shared_module_is_the_single_source_of_workspace_title():
    shared = read("src/shared.ts")
    assert "export const WORKSPACE_TITLE = '学习领航员'" in shared
    for rel in ("src/client/index.tsx", "src/server/learning.ts"):
        assert "WORKSPACE_TITLE = " not in read(rel), rel + " 不该再自己定义工作区名"


def test_create_never_gets_both_workspace_and_cwd():
    """宿主 session.create 收到 workspaceId + cwd 会直接 bad-request（源码 commands.ts 核对过）。"""
    body = read("src/client/index.tsx")

    assert "payload.cwd = cwd" not in body
    assert "{ workspaceId: options.workspaceId }" in body


def test_no_undefined_debug_tracer_left_in_bundle():
    """以前 openNativeDiscussion 里调了 5 次未定义的 step()，讨论按钮必然抛 ReferenceError。"""
    for rel in ("src/client/index.tsx", "lib/client.js"):
        assert not re.search(r"(?<![\w.])step\(", read(rel)), rel


def test_package_has_test_script():
    scripts = json.loads(read("package.json"))["scripts"]
    assert "learning.contract.mjs" in scripts["test"]
    assert "client.contract.mjs" in scripts["test"]


def test_readme_documents_workspace_filtering():
    body = read("README.md")

    assert "只在「学习领航员」工作区启用" in body
    assert "workspaceRegistry" in body
    assert "0.2.0-rc.1" in body
