"""T-046 失败测试：任务讨论归入「学习领航员」专用工作区。

客户反馈：讨论会话混在默认工作区里。

宿主接缝（实测 0.1.5-rc.3）：
- 客户端有 "ctx.workspaces" 服务：create({path}) / rename(id, title) / list（快照）；
- "ctx.sessions.create({ workspaceId, cwd })" 可以指定归属工作区；
- **"workspaces.create" 只接受目录路径**，标题由目录派生（rename 可改，但改名是全局的）。

所以"名为「学习领航员」的独立工作区"需要**它自己的目录**；
这条限制必须写进插件 README，并给出最接近的降级（复用项目目录那个工作区）。
"""
from __future__ import annotations

import pathlib
import re

PLUGIN = pathlib.Path("plugin")
CLIENT = PLUGIN / "src" / "client" / "index.tsx"


def read(path: pathlib.Path) -> str:
    assert path.is_file(), "缺文件：" + str(path)
    return path.read_text(encoding="utf-8")


# ---------- 接缝声明 ----------


def test_client_injects_workspaces_seam():
    body = read(CLIENT)

    match = re.search(r"export\s+const\s+inject\s*=\s*\[([^\]]*)\]", body)
    assert match, "要 export const inject"
    names = match.group(1)
    assert "workspaces" in names, "要用 ctx.workspaces 接缝"
    assert "sessions" in names, "讨论还要 sessions"
    assert "slots" in names, "面板还要 slots"


def test_client_creates_workspace_from_project_path():
    body = read(CLIENT)

    assert "ctx.workspaces" in body or "ctx?.workspaces" in body
    assert re.search(r"workspaces\.create\(\s*\{\s*path\s*\}\)", body), \
        "要用 workspaces.create({ path }) —— 它只接受目录路径"


def test_client_passes_workspace_to_session():
    """会话必须建在指定工作区里（这是本卡的核心）。"""
    body = read(CLIENT)

    assert re.search(r"workspaceId", body), "sessions.create 要带 workspaceId"


def test_client_does_not_bypass_auth():
    body = read(CLIENT)

    for bad in ("document.cookie", "localStorage.setItem", "api/session/create"):
        assert bad not in body, "不该出现 " + bad


# ---------- 会话标题 ----------


def test_session_title_uses_timestamp_and_goal():
    """标题 = 任务时间戳 + 任务目标前 20 字。"""
    body = read(CLIENT)

    assert "20" in body, "要截取目标前 20 字"
    assert "rename" in body, "要用 rename 设置标题"


def test_session_title_truncates_long_goal():
    """截断规则要可核对：超过 20 字加省略号。"""
    body = read(CLIENT)

    assert "…" in body or "..." in body, "截断要有省略号"


# ---------- 降级 ----------


def test_client_has_workspace_fallback():
    """拿不到 workspaces 接缝时降级（不能因此让讨论整个失败）。"""
    body = read(CLIENT)

    assert "try" in body and "catch" in body
    assert re.search(r"workspaces[^\n]{0,80}(?:无|没有|不可用|undefined)", body) or \
        "没有工作区" in body or "工作区接缝" in body, "要说明降级原因"


def test_fallback_still_creates_session():
    """降级时仍然要把会话建出来（只是可能落在默认工作区）。"""
    body = read(CLIENT)

    # 拿不到 workspaceId 也要继续调 sessions.create
    assert re.search(r"sessions\.create\(", body), "降级路径也要建会话"


# ---------- README 记录限制 ----------


def test_readme_documents_dedicated_workspace():
    body = read(PLUGIN / "README.md")

    assert "学习领航员" in body
    assert "工作区" in body
    assert "ctx.workspaces" in body


def test_readme_records_windows_path_limitation():
    """如实记录：宿主 create 只吃目录路径，标题由目录派生。"""
    body = read(PLUGIN / "README.md")

    assert "只接受" in body or "只能" in body, "要写清 create 的参数限制"
    assert "rename" in body, "要写清改名是全局的"


def test_readme_gives_closest_fallback():
    body = read(PLUGIN / "README.md")

    assert "降级" in body
    assert "目录" in body, "降级方案要落到目录上"


# ---------- 不许把工作区搞乱 ----------


def test_does_not_rename_existing_workspace_blindly():
    """不许无条件 rename——那会把用户已有的工作区改名（破坏性）。"""
    body = read(CLIENT)

    # rename 必须包在条件里（只有确实需要时才改）
    assert "rename" in body
    assert re.search(r"if\s*\([^)]*\)\s*\{[^}]*rename", body, re.S) or \
        re.search(r"title\s*!==|title\s*===|已有", body), \
        "rename 要有条件（不能无条件改别人已有的工作区名）"


def test_committed_client_bundle_rebuilt():
    bundle = read(PLUGIN / "lib" / "client.js")

    assert "workspaces" in bundle, "客户端产物没重建"
    assert "workspaceId" in bundle

# ---------- T-046 真机踩到的决定性坑：输入面的获取链 ----------


def test_client_uses_resolve_agent_scope_chain():
    """宿主**没有** sessions.get / sessions.session，必须走 sessionOf(resolveAgentScope(id))。

    真机实测（2026-09-29）：
      - ctx.sessions 上真实存在的方法里**没有** get / session / byId / current；
      - 只有 resolveAgentScope / sessionOf 能拿到 Session 输入面；
      - 老的 faceOf() 只试 get/session → 永远 null → 讨论 100% 降级，
        会话虽然进了工作区却永远没有输入面（空壳）。

    契约出处：dsh-api-session-controller/lib/types/client/sessions/service.d.ts
      resolveAgentScope(id: SessionId): AgentContext
      sessionOf(ctx: Context): SessionFace | undefined
    """
    body = read(CLIENT)

    assert "resolveAgentScope" in body, "必须用 resolveAgentScope(id) 拿 AgentContext"
    assert "sessionOf" in body, "必须用 sessionOf(agentCtx) 拿 Session 面"
    # 链要串起来（不是各自出现就行）
    assert re.search(r"resolveAgentScope\(\s*id\s*\)", body), \
        "resolveAgentScope 要吃会话 id"
    assert re.search(r"sessionOf\(\s*agentCtx\s*\)", body), \
        "sessionOf 要吃 resolveAgentScope 的结果"


def code_only(body: str) -> str:
    """剥掉注释，避免"注释里先提到某 API"把顺序判断骗了（本测试第一版就这么假红过）。"""
    without_block = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    return re.sub(r"//[^\n]*", "", without_block)


def test_get_and_session_are_only_fallbacks():
    """get/session 只能当兜底，不能是主路径（按**代码**顺序判断，不看注释）。"""
    body = code_only(read(CLIENT))

    i_chain = body.find("resolveAgentScope")
    i_get = body.find("sessions.get")
    i_session = body.find("sessions.session(")
    assert i_chain > 0, "没有主路径"
    for label, index in (("get", i_get), ("session", i_session)):
        if index > 0:
            assert i_chain < index, "主路径必须在 " + label + " 兜底之前"


def test_face_ready_polling_still_present():
    """scope 是惰性 mint 的，仍要轮询等输入面就绪（T-040 的教训）。"""
    body = read(CLIENT)

    assert re.search(r"for\s*\(\s*let\s+i\s*=\s*0;\s*i\s*<\s*\d+", body), \
        "要有轮询等待"
    assert "setTimeout" in body