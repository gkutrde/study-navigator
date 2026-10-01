"""T-040 失败测试：任务讨论原生会话（无接缝则降级 headless 自渲染）。

两条路径：
1. **原生**：插件在宿主进程内调公开会话接缝 ctx.sessions（create → open → prompt），
   把 handoff 上下文预填进去，用户在原生会话里继续追问。
2. **降级**：拿不到会话接缝时，调 headless 由面板自渲染——**绝不绕过鉴权**。
"""
from __future__ import annotations
from src.silent import silent_kwargs

import pathlib
import re
import shutil
import subprocess

import pytest

PLUGIN = pathlib.Path("plugin")
NODE = shutil.which("node")
CLIENT = PLUGIN / "src" / "client" / "index.tsx"
SERVER = PLUGIN / "src" / "server" / "learning.ts"


def read(path: pathlib.Path) -> str:
    assert path.is_file(), "缺文件：" + str(path)
    return path.read_text(encoding="utf-8")


requires_node = pytest.mark.skipif(NODE is None, reason="没有 node")


# ---------- 原生路径 ----------


def test_client_injects_sessions_seam():
    """要用 ctx.sessions 就必须先注入它（T-038 的教训：没 inject 会被拒绝访问）。"""
    body = read(CLIENT)

    match = re.search(r"export\s+const\s+inject\s*=\s*\[([^\]]*)\]", body)
    assert match, "客户端要 export const inject"
    names = match.group(1)
    assert "slots" in names, "面板还需要 slots"
    assert "sessions" in names, "讨论要用 sessions 接缝"


def test_client_uses_public_session_seam():
    body = read(CLIENT)

    assert "ctx.sessions" in body, "要用公开的 ctx.sessions"
    assert ".create(" in body, "要创建会话"
    assert ".open(" in body, "要打开会话"
    assert ".prompt(" in body, "要把 handoff 预填进去"


def test_client_does_not_fake_auth():
    """绝不绕过鉴权：不许伪造 cookie/token，不许 hack 桌面令牌。"""
    body = read(CLIENT)

    for bad in ("document.cookie", "localStorage.setItem", "desktop-token", "api/session/create"):
        assert bad not in body, "不该出现 " + bad


def test_client_has_discuss_button():
    body = read(CLIENT)

    assert "讨论" in body, "任务卡片要有「讨论」按钮"


# ---------- 降级路径 ----------


def test_client_has_fallback_path():
    """拿不到会话接缝时要降级，而且要显式告知用户。"""
    body = read(CLIENT)

    assert "降级" in body or "不支持" in body or "不可用" in body
    assert "headless" in body or "讨论" in body


def test_client_fallback_does_not_throw():
    body = read(CLIENT)

    assert "try" in body and "catch" in body, "接缝缺失要用 try/catch 兜住"


# ---------- 服务端：handoff 交付给客户端 ----------


def test_server_exposes_handoff_for_discussion():
    """预填内容来自 handoff 文件；服务端要能把它整段交付。"""
    body = read(SERVER)

    assert "handoff" in body, "服务端要读 handoff"
    assert "discuss" in body, "要有讨论动作"


def test_server_discuss_is_allowlisted():
    body = read(SERVER)

    assert re.search(r"discuss\s*:", body), "discuss 要进动作白名单"


def test_server_reports_session_capability():
    """服务端不创建会话；它只如实报告"这条链路是否可用"，便于面板提示。"""
    body = read(SERVER)

    assert "capabilities" in body or "capability" in body


@requires_node
def test_client_source_still_valid():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        target = pathlib.Path(tmp) / "client.ts"
        target.write_text(read(CLIENT), encoding="utf-8")
        done = subprocess.run(
            [NODE, "--check", str(target)],
            capture_output=True, text=True, encoding="utf-8",
            **silent_kwargs(),
        )
        assert done.returncode == 0, done.stderr


def test_readme_documents_discussion_seams():
    body = read(PLUGIN / "README.md")

    assert "ctx.sessions" in body
    assert "讨论" in body
    assert "降级" in body


def test_committed_bundles_rebuilt_for_discussion():
    client = read(PLUGIN / "lib" / "client.js")

    assert "sessions" in client, "客户端产物没重建"
    assert "讨论" in client


def test_contract_script_covers_discussion():
    script = (PLUGIN / "tests" / "learning.contract.mjs").read_text(encoding="utf-8")

    assert "discuss" in script
