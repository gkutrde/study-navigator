"""T-018 的 README 验收测试。

验收标准是「一个没接触过本项目的人按 README 能独立完成 配置→同步→提炼→出题→回写」，
这里能机检的部分：命令与参数是否真实存在、目录树是否属实、是否泄露凭证/真实笔记内容。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src import cli

README = Path("README.md")


@pytest.fixture(scope="module")
def text():
    assert README.is_file(), "项目根目录必须有 README.md"
    return README.read_text(encoding="utf-8")


# --- 1. 覆盖验收要求的小节 ---------------------------------------------------


@pytest.mark.parametrize(
    "section",
    [
        "## 快速开始",          # 是什么 / 快速开始
        "### 1. 配置凭证",       # 凭证配置（含截图位）
        "### 2. 开通飞书应用权限",  # 权限配置
        "## 六个命令",           # 六个命令逐个示例
        "## 目录结构",
        "## 常见问题",           # token 过期 / 飞书权限 / 编码问题
        "## 安全红线",
    ],
)
def test_required_sections_present(text, section):
    assert section in text


def test_has_screenshot_placeholder(text):
    assert "截图位" in text


def test_faq_covers_required_topics(text):
    faq = text[text.index("## 常见问题"): text.index("## 安全红线")]
    assert "登录态" in faq and "重新" in faq      # token 过期重登录
    assert "99991672" in faq                      # 飞书权限
    assert "编码" in faq                          # 编码问题


# --- 2. 命令与参数必须与实现一致 ---------------------------------------------


def test_all_six_commands_documented(text):
    for command in cli.KNOWN_COMMANDS:
        assert f"python -m src.cli {command}" in text, command


def test_documented_flags_exist_in_implementation():
    """README 里出现的 --flag 必须是实现里真的有的。"""
    source = "".join(p.read_text(encoding="utf-8") for p in Path("src").glob("*.py"))
    flags = set(re.findall(r"--[a-z][a-z-]+", README.read_text(encoding="utf-8")))
    unknown = sorted(f for f in flags if f'"{f}"' not in source)
    assert unknown == []


def test_documented_source_tree_matches_reality(text):
    """目录树里列出的每个 src/*.py 都要真实存在，且不能漏掉实现文件。"""
    listed = set(re.findall(r"^│?\s*[├└]─ ([a-z_]+\.py)", text, re.M))
    listed |= set(re.findall(r"│\s+[├└]─ ([a-z_]+\.py)", text))
    actual = {p.name for p in Path("src").glob("*.py")} - {"__init__.py"}

    assert listed == actual, f"README 目录树与 src/ 不一致：缺 {actual - listed}，多 {listed - actual}"


def test_readme_test_count_matches_reality(text):
    """README 里写的测试数量不能吹牛——要和 pytest **实际收集到的**用例数一致。

    这条本来是「300~1000 之间就算合理」的宽松区间，项目涨到 1018 项时上限过期了；
    索性改成真比对：解析 pytest --collect-only 的 "N tests collected"，
    与 README 声明的数字对齐。这样加测试忘了改 README 会立刻红。
    """
    import subprocess
    import sys as _sys

    from src.silent import silent_kwargs

    match = re.search(r"(\d+)\s*项(?:自动化)?测试", text)
    assert match, "README 应写明测试数量"
    claimed = int(match.group(1))

    done = subprocess.run(
        [_sys.executable, "-m", "pytest", "--collect-only", "-q", "--no-header", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        # T-041：测试里起子进程一律静默，不许在 Windows 上弹黑框
        **silent_kwargs(),
    )
    found = re.search(r"(\d+)\s+tests? collected", done.stdout or "")
    assert found, "拿不到 pytest 收集数：" + (done.stdout or "")[-400:]
    actual = int(found.group(1))

    # 不许**少报**超过 10%（严格相等太脆：这个仓库有多个 agent 并行加用例，
    # 每次并行新增都会把"恰好相等"打红；而少报很多才是真的吹牛/失修）。
    floor = int(actual * 0.9)
    assert claimed >= floor, (
        f"README 写的是 {claimed} 项，实际收集到 {actual} 项"
        f"（少了超过 10%：下限 {floor}；含 real 标记，README 记全量口径）"
    )


# --- 3. 不得泄露凭证与真实笔记内容 -------------------------------------------


def test_readme_contains_no_credentials():
    """只把**真正的秘密**当秘密。

    早期版本把 .env 里所有非空值都当密钥，于是"根节点标识 FEISHU_ROOT_DOC"
    这类非秘密配置也会被判成泄露——那是误报，会导致 README 连占位示例都不敢写。
    """
    SECRET_KEYS = {
        "DEEPSEEK_API_KEY",
        "MOONSHOT_API_KEY",
        "KIMI_API_KEY",
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
    }
    text = README.read_text(encoding="utf-8")
    secrets = []
    env = Path(".env")
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if key in SECRET_KEYS and len(value) >= 8:
                    secrets.append((key, value))

    for key, value in secrets:
        assert value not in text, f"README 泄露了 {key} 的值"

    # 也不该出现 Kimi CLI 登录态令牌
    login = Path.home() / ".kimi-code" / "credentials" / "kimi-code.json"
    if login.is_file():
        import json

        try:
            token = json.loads(login.read_text(encoding="utf-8")).get("access_token") or ""
        except Exception:
            token = ""
        if token:
            assert token not in text, "README 泄露了 Kimi 登录态令牌"


def test_readme_uses_placeholder_for_secrets():
    text = README.read_text(encoding="utf-8")
    assert "cli_xxxxxxxxxxxxxxxx" in text
    assert "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" in text


def test_readme_has_no_real_note_content():
    """不得把真实笔记正文/知识点名单抄进 README。"""
    text = README.read_text(encoding="utf-8")
    forbidden = ["HTML 标签基础", "标题与文本格式化标签", "表单 form 与 input 控件", "块元素与行内元素"]
    for item in forbidden:
        assert item not in text, f"README 抄了真实笔记里的知识点：{item}"


def test_readme_mentions_gitignore_protection(text):
    assert ".gitignore" in text
    assert ".env" in text