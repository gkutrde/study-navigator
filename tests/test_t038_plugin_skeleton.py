"""T-038 失败测试：DSH 插件骨架（plugin/ 子目录）。

这份测试**不依赖网络与 pnpm 安装**：校验的是插件包的"形状"——
清单、宿主接线、客户端产物是否符合宿主公开接缝，以及 README 那份兼容矩阵。
形状错了，dsh plugin add 装上去也不会出现面板。
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
PKG = "dsh-learning-navigator"


def read(rel: str) -> str:
    target = PLUGIN / rel
    assert target.is_file(), "缺文件：" + str(target)
    return target.read_text(encoding="utf-8")


def manifest() -> dict:
    return json.loads(read("package.json"))


def node_check(path: pathlib.Path) -> subprocess.CompletedProcess:
    target = path
    # node --check 按扩展名判定语法模式：.tsx 会当成 JS 而误报。
    # 复制一份 .ts 再检查，拿到的是同一份源码的真实语法结论。
    if target.suffix == ".tsx":
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / (target.stem + ".ts")
            target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            return subprocess.run(
                [NODE, "--check", str(target)],
                capture_output=True, text=True, encoding="utf-8",
                **silent_kwargs(),
            )
    return subprocess.run(
        [NODE, "--check", str(target)],
        capture_output=True, text=True, encoding="utf-8",
        **silent_kwargs(),
    )


requires_node = pytest.mark.skipif(NODE is None, reason="没有 node")


def test_plugin_dir_exists():
    assert PLUGIN.is_dir(), "插件必须放在本仓库 plugin/ 子目录"


def test_manifest_name_and_type():
    data = manifest()
    assert data["name"] == PKG
    assert data["type"] == "module"
    assert str(data["engines"]["node"]).startswith(">=")


def test_manifest_declares_bundle_patch():
    assert manifest()["dsh"]["bundle"]["patch"] == "./cordis.patch.yml"


def test_manifest_declares_client_half():
    client = manifest()["dsh"]["client"]
    assert client["platform"] == "web"
    assert isinstance(client.get("inject", []), list)


def test_manifest_exports_client_entry():
    data = manifest()
    assert data["exports"]["./client"] == "./lib/client.js"


def test_manifest_exports_package_json():
    assert "./package.json" in manifest()["exports"]


def test_files_whitelist_includes_build_output():
    files = manifest()["files"]
    assert any(item.startswith("lib") for item in files), files
    assert "cordis.patch.yml" in files


def test_no_runtime_deps_beyond_schemastery():
    deps = manifest().get("dependencies", {})
    assert set(deps) <= {"@deepseek-ai/schemastery"}, deps


def test_cordis_patch_mounts_plugin():
    patch = read("cordis.patch.yml")
    assert "insert:" in patch
    assert PKG in patch
    assert not patch.strip().startswith("[]"), "空 patch 等于没挂载"


def test_patch_is_valid_yaml():
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load(read("cordis.patch.yml"))
    assert isinstance(data, list) and data
    entries = data[0]["insert"]
    assert any(row.get("name") == PKG for row in entries)


@requires_node
def test_server_entry_is_valid_js():
    entry = PLUGIN / "src" / "index.ts"
    assert entry.is_file()
    assert node_check(entry).returncode == 0


def test_server_entry_exports_name_and_apply():
    body = read("src/index.ts")
    assert re.search(r"export\s+const\s+name\s*=", body)
    assert re.search(r"export\s+function\s+apply\s*\(", body)
    assert PKG in body


def test_server_entry_does_not_use_private_apis():
    body = read("src/index.ts")
    for forbidden in ("process.binding", "__dsh_internal"):
        assert forbidden not in body, "不该出现 " + forbidden


@requires_node
def test_client_source_is_valid():
    entry = PLUGIN / "src" / "client" / "index.tsx"
    assert entry.is_file(), "客户端入口应为 src/client/index.tsx"
    assert node_check(entry).returncode == 0


def test_client_registers_into_a_documented_slot():
    body = read("src/client/index.tsx")
    assert "ctx.slots.inject" in body
    assert "ctx.slots.register" in body
    slot = re.search(r"SLOT\s*=\s*[\'\"]([\w.]+)[\'\"]", body)
    if not slot:
        slot = re.search(r"slots\.inject\(\s*[\'\"]([\w.]+)[\'\"]", body)
    assert slot, "要明确注入的 slot 名"
    assert slot.group(1) in read("README.md"), "用的 slot 必须写进 README 的接缝清单"


def test_client_renders_learning_panel():
    assert "学习" in read("src/client/index.tsx"), "面板要显示「学习」"


def test_client_uses_platform_react():
    body = read("src/client/index.tsx")
    assert "react" in body
    assert "@deepseek-ai/dsh-web" not in body


def test_committed_client_bundle_exists():
    assert (PLUGIN / "lib" / "client.js").is_file()


@requires_node
def test_committed_client_bundle_is_valid_js():
    assert node_check(PLUGIN / "lib" / "client.js").returncode == 0


def test_committed_bundle_is_moduleloader_wrapped():
    body = read("lib/client.js")
    assert "__ModuleLoader__.load" in body
    assert "factory" in body
    assert PKG in body, "模块 id 要是包名"
    assert "return module.exports" in body


def test_bundle_does_not_inline_react():
    body = read("lib/client.js")
    assert ("require(\"react\")" in body) or ("require(\'react\')" in body)


def test_tsdown_config_declares_loader_banner():
    config = read("tsdown.config.ts")
    assert "__ModuleLoader__.load" in config
    assert "neverBundle" in config
    assert "react" in config


def test_readme_has_seam_inventory():
    body = read("README.md")
    assert "接缝" in body
    assert "ctx.slots" in body
    assert "inject" in body


def test_readme_has_version_compat_matrix():
    body = read("README.md")
    assert "兼容矩阵" in body
    assert "0.1.5" in body, "要写明实测的宿主版本"


def test_readme_lists_every_slot_we_use():
    body = read("README.md")
    source = read("src/client/index.tsx")
    used = set(re.findall(r"SLOT\s*=\s*[\'\"]([\w.]+)[\'\"]", source))
    used |= set(re.findall(r"slots\.inject\(\s*[\'\"]([\w.]+)[\'\"]", source))
    missing = [name for name in used if name not in body]
    assert not missing, "这些 slot 没写进 README：" + str(missing)


def test_readme_has_smoke_checklist():
    body = read("README.md")
    assert "冒烟" in body
    assert "出题" in body
    assert "讨论" in body


def test_readme_states_no_private_apis_rule():
    body = read("README.md")
    assert "公开" in body
    assert ("鉴权" in body) or ("不绕过" in body)


def test_readme_notes_python_core_stays_backend():
    body = read("README.md")
    assert "Python" in body
    assert ("后端" in body) or ("逻辑" in body)


def test_plugin_has_gitignore_for_node_modules():
    assert (PLUGIN / ".gitignore").is_file(), "要忽略 node_modules 与构建中间物"
    ignore = read(".gitignore")
    assert "node_modules" in ignore

def test_committed_server_bundle_exists():
    """真机教训：宿主按 main 字段加载 lib/index.js。

    只构建客户端半边时，profile 直接起不来：
    Cannot find module .../dsh-learning-navigator/lib/index.js
    """
    assert (PLUGIN / "lib" / "index.js").is_file(), "服务端入口也要有构建产物"


@requires_node
def test_committed_server_bundle_is_valid_js():
    assert node_check(PLUGIN / "lib" / "index.js").returncode == 0


def test_manifest_main_points_at_built_output():
    data = manifest()
    assert data["main"] == "./lib/index.js"
    assert data["exports"]["."] == "./lib/index.js"


def test_server_bundle_exports_name_and_apply():
    body = read("lib/index.js")
    assert "dsh-learning-navigator" in body
    assert "apply" in body

def test_client_declares_slots_inject():
    """真机教训：客户端 inject 少了 slots，宿主会拒绝访问 ctx.slots。

    报错原文：cannot get property "slots" without inject
    → 界面直接显示 Failed to load plugins，面板当然不出现。
    """
    body = read("src/client/index.tsx")

    assert re.search(r"export\s+const\s+inject\s*=\s*\[\s*[\'\"]slots[\'\"]", body), \
        "客户端入口必须 export const inject = [slots]"


def test_server_inject_declares_connection():
    """T-038 时服务端 inject 是空数组（骨架）；**T-039 起要 ['connection']**。

    只声明确定存在的接缝（web profile 一定有 connection——/api 就是它挂的）。
    """
    body = read("src/index.ts")

    assert re.search(r"export\s+const\s+inject[^=]*=\s*\[\s*['\"]connection['\"]", body), \
        "T-039 起服务端要注入 connection"