"""T-045 失败测试：残渣防复发。

两件事故背景：
- 模板里的临时目录（profile/_xxx/）忘了删，留在真实仓库里；
- 测试忘传路径参数，写到真实的 profile/syllabus.md（test_t010 里那句注释就是现场）。

守护方式：
1. **profile/ 不许有 _ 开头的文件/目录**（临时残渣的指纹）；
2. 测试里不许出现"往真实 profile/ 写"的调用；
3. 写路径必须来自 tmp_path。
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
PROFILE = ROOT / "profile"


# ---------- 1. profile/ 无临时残渣 ----------


def test_profile_has_no_underscore_leftovers():
    """守护：profile/ 下不许有 _ 开头的文件或目录。

    这是"临时目录忘了删"最直接的指纹（实测出现过 profile/_t031_probe.md、profile/_t037_pw/）。
    """
    leftovers = sorted(
        item.name for item in PROFILE.iterdir() if item.name.startswith("_")
    )

    assert not leftovers, "profile/ 里有临时残渣：" + ", ".join(leftovers)


def test_profile_exists():
    assert PROFILE.is_dir(), "找不到 profile/ 目录"


def test_no_nested_scratch_dirs_in_profile():
    """profile/ 下面只允许已知的那几个条目——多出来的就是残渣。"""
    allowed = {
        "knowledge.md",
        "tasks.md",
        "syllabus.md",
        "assignments.md",
        "alignment.json",
        ".distill-state.json",
        "explanations",
        "handoff",
        "weaknesses.md",
    }
    unexpected = sorted(
        item.name for item in PROFILE.iterdir() if item.name not in allowed
    )

    assert not unexpected, "profile/ 里有预期外的条目：" + ", ".join(unexpected)


def test_profile_has_no_tmp_files():
    """原子写的中间产物也不许留下。"""
    tmps = sorted(str(p.relative_to(ROOT)) for p in PROFILE.rglob("*.tmp"))

    assert not tmps, "profile/ 里有 .tmp 残留：" + ", ".join(tmps)


# ---------- 2. 测试不许写真实 profile/ ----------


def _write_calls(body: str):
    """找出写文件/写文件夹相关的调用（用于判断是不是往真实 profile 写）。"""
    tree = ast.parse(body)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            name = node.func.attr
            if name in (
                "write_text",
                "write_bytes",
                "append_task_record",
                "write_profile_atomic",
                "write_syllabus",
                "merge_weaknesses",
                "save_explanation",
                "write_handoff",
                "save_archive",
                "append_turn",
            ):
                yield node


def test_tests_do_not_write_to_real_profile():
    """测试里的写调用不许直接指向真实 profile/ 路径字面量。"""
    offenders = []
    for path in TESTS.glob("test_*.py"):
        if path.name == pathlib.Path(__file__).name:
            continue
        body = path.read_text(encoding="utf-8")
        for node in _write_calls(body):
            chunk = ast.unparse(node)
            if re.search(r"['\"]profile/", chunk) and "tmp_path" not in chunk:
                offenders.append(
                    path.name + ":" + str(node.lineno) + "  " + chunk[:90]
                )

    assert not offenders, "这些测试在往真实 profile/ 写：" + chr(10).join(offenders)


def test_cli_tests_pass_profile_path(tmp_path):
    """调 cli.main 的测试必须显式传 profile_path（否则会落到真实画像）。"""
    offenders = []
    for path in TESTS.glob("test_*.py"):
        if path.name == pathlib.Path(__file__).name:
            continue
        body = path.read_text(encoding="utf-8")
        if "cli.main(" not in body:
            continue
        for match in re.finditer(r"cli\.\.main\(([^)]{0,300})", body, re.S):
            chunk = match.group(1)
            line = body[: match.start()].count(chr(10)) + 1
            # 只查"会写"的子命令
            if not re.search(r"['\"](sync|import|distill|align|next|done|report)['\"]", chunk):
                continue
            if "profile_path" in chunk or "tmp_path" in chunk:
                continue
            offenders.append(path.name + ":" + str(line))

    assert not offenders, "这些调用没传 profile_path：" + ", ".join(offenders)


def test_no_hardcoded_repo_profile_writes():
    """不许出现 Path("profile/...") 后直接写。"""
    offenders = []
    for path in TESTS.glob("test_*.py"):
        if path.name == pathlib.Path(__file__).name:
            continue
        body = path.read_text(encoding="utf-8")
        for match in re.finditer(
            r"Path\(\s*[\'\"]profile/[^\'\"]*[\'\"]\s*\)\s*\.\s*(write_text|write_bytes|unlink|mkdir)",
            body,
        ):
            line = body[: match.start()].count(chr(10)) + 1
            offenders.append(path.name + ":" + str(line))

    assert not offenders, "这些地方在写真实 profile/：" + ", ".join(offenders)


# ---------- 3. 跑完一轮测试后仍然干净 ----------


def test_profile_snapshot_is_stable():
    """记录当前 profile/ 条目；本条与上一条一起构成"跑测试不落残渣"的守护。

    如果哪天有测试往真实 profile 写了东西，上面的条目白名单会红。
    """
    names = sorted(item.name for item in PROFILE.iterdir())

    assert "knowledge.md" in names
    assert not [n for n in names if n.startswith("_")]


# ---------- 4. 测试自己的 tmp_path 用法 ----------


def test_most_tests_use_tmp_path():
    """样板：相当比例（≥40%）的用例用 tmp_path 隔离。

    实测基线是 454/981 ≈ 46%——多数用例是纯函数/prompt 组装，本来不需要临时目录。
    这个断言只防**退化**（有人把已有隔离改成写真实路径），不是要求 100%。
    """
    total = 0
    using = 0
    for path in TESTS.glob("test_*.py"):
        body = path.read_text(encoding="utf-8")
        for match in re.finditer(r"^def (test_\w+)", body, re.M):
            total += 1
            signature_start = match.start()
            signature = body[signature_start: body.find(chr(10), signature_start)]
            if "tmp_path" in signature:
                using += 1

    assert total > 0
    assert using / total >= 0.40, "用 tmp_path 的用例比例退化了：" + str(using) + "/" + str(total)
