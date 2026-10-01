"""T-039 失败测试：学习面板 v1（画像/任务/地图 + 按钮调 Python CLI）。

两半：
- 服务端（plugin/src/server/learning.ts）：读 profile/ 文件、经**白名单**跑 python -m src.cli；
- 客户端（plugin/src/client/index.tsx）：渲染三类数据 + 操作按钮 + 项目路径配置。

安全不变量（这批测试的重点）：
- 命令**只能是** python -m src.cli 加白名单子命令，绝不走 shell；
- 路径参数不许拼接成命令；
- CLI 失败要变成**中文**错误，不能把堆栈或英文原文抛给用户。
"""
from __future__ import annotations
from src.silent import silent_kwargs

import json
import pathlib
import re
import shutil
import subprocess

import pytest

PLUGIN = pathlib.Path("plugin")
NODE = shutil.which("node")
SERVER = PLUGIN / "src" / "server" / "learning.ts"
CLIENT = PLUGIN / "src" / "client" / "index.tsx"


def read(path: pathlib.Path) -> str:
    assert path.is_file(), "缺文件：" + str(path)
    return path.read_text(encoding="utf-8")


requires_node = pytest.mark.skipif(NODE is None, reason="没有 node")


# ---------- 服务端：路由与动作白名单 ----------


def test_server_module_exists():
    assert SERVER.is_file()


@requires_node
def test_server_module_is_valid_js():
    target = SERVER
    done = subprocess.run(
        [NODE, "--check", str(target)],
        capture_output=True, text=True, encoding="utf-8",
        **silent_kwargs(),
    )
    assert done.returncode == 0, done.stderr


def test_registers_authenticated_fetch_route():
    body = read(SERVER)

    assert "connection" in body, "要用 ctx.connection 接缝"
    assert "fetch" in body and "register" in body, "要用精确 Fetch 路由注册"
    assert "path:" in body and "/api/learning" in body
    assert "methods:" in body
    assert "requestBody:" in body


def test_uses_public_inject_not_private_apis():
    body = read(SERVER)

    for forbidden in ("process.binding", "__dsh_internal"):
        assert forbidden not in body, "不该出现 " + forbidden
    # 只禁止 CommonJS 的运行时 require（ESM import 是正常的）
    assert not re.search(r"(?<![.\w])require\s*\(", body), "不该用运行时 require"
    assert "ctx" in body, "要靠 ctx 接缝工作"


def test_declares_action_whitelist():
    """动作必须走白名单——不接任何"命令字符串"。"""
    body = read(SERVER)

    match = re.search(r"ACTIONS\s*(?::[^=]+)?=\s*\{?([^}\n]+)", body)
    assert match, "要有 ACTIONS 白名单"
    for name in ("profile", "tasks", "syllabus", "sync", "next", "done"):
        assert name in body, "白名单缺动作：" + name


def test_cli_commands_are_whitelisted():
    body = read(SERVER)

    assert "spawn" in body, "要用 spawn（而非 exec）以便控制参数数组"
    assert "shell: false" in body or "shell:false" in body, "绝不能走 shell"
    assert "-m" in body and "src.cli" in body


def test_no_string_command_interpolation():
    """不许把用户输入拼进命令字符串。"""
    body = read(SERVER)

    for bad in ("execSync", "child_process.exec"):
        assert bad not in body, "不该出现 " + bad
    assert not re.search(r"(?<![.\w])exec\s*\(", body), "不该用 exec（要 spawn + 参数数组）"


def test_cli_failure_becomes_chinese_error():
    body = read(SERVER)

    assert "失败" in body, "错误信息要用中文"
    assert "stderr" in body, "要读 stderr 拿原因"


def test_project_path_is_configurable():
    body = read(SERVER)

    assert "projectRoot" in body or "project_root" in body
    assert "resolve" in body, "路径要归一化"


# ---------- 客户端：渲染与按钮 ----------


def test_client_panel_renders_three_sections():
    body = read(CLIENT)

    for keyword in ("知识画像", "任务", "知识地图"):
        assert keyword in body, "面板要展示：" + keyword


def test_client_has_action_buttons():
    body = read(CLIENT)

    for label in ("同步并提炼", "出题", "回写"):
        assert label in body, "缺按钮：" + label


def test_client_posts_to_our_route():
    body = read(CLIENT)

    assert "/api/learning" in body
    assert "fetch(" in body


def test_client_shows_errors_inline():
    body = read(CLIENT)

    assert "失败" in body or "错误" in body


def test_client_has_path_setting_input():
    body = read(CLIENT)

    assert "项目路径" in body or "项目根" in body
    assert "input" in body


def test_client_does_not_use_private_host_modules():
    body = read(CLIENT)

    for forbidden in ("__dsh_internal", "process.binding"):
        assert forbidden not in body


@requires_node
def test_client_source_is_valid():
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


# ---------- 契约一致：动作名两端与文档都对齐 ----------


def test_action_names_match_between_halves():
    server = read(SERVER)
    client = read(CLIENT)

    declared = set(re.findall(r"^\s*(profile|tasks|syllabus|sync|next|done)\s*:", server, re.M))
    assert declared, "服务端没解析出动作表"
    for name in declared:
        assert ("'" + name + "'") in client or ('"' + name + '"') in client, \
            "客户端没调用动作：" + name


def test_readme_documents_learning_route():
    body = read(PLUGIN / "README.md")

    assert "/api/learning" in body
    assert "connection.fetch" in body
    assert "0.1.5" in body


def test_readme_documents_new_slots_and_actions():
    body = read(PLUGIN / "README.md")

    for label in ("同步并提炼", "出题", "回写"):
        assert label in body, "README 要写清按钮：" + label


def test_committed_server_bundle_rebuilt():
    """产物要跟着源码更新（宿主只认 lib/）。"""
    bundle = read(PLUGIN / "lib" / "index.js")

    assert "/api/learning" in bundle, "lib/index.js 还是旧的，没重新构建"


def test_committed_client_bundle_has_panel():
    bundle = read(PLUGIN / "lib" / "client.js")

    assert "知识画像" in bundle or "知识画像" in bundle
    assert "/api/learning" in bundle
    assert "__ModuleLoader__.load" in bundle


# ---------- 不许把 Python 仓库搅乱 ----------


def test_plugin_gitignore_covers_build_intermediates():
    ignore = read(PLUGIN / ".gitignore")

    assert "node_modules" in ignore


def test_manifest_still_declares_client_platform():
    data = json.loads(read(PLUGIN / "package.json"))

    assert data["dsh"]["client"]["platform"] == "web"
    assert data["dsh"]["bundle"]["patch"] == "./cordis.patch.yml"