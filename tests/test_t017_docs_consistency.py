"""T-017 的文档一致性测试（I-5 / I-6）。

用测试锁定"文档与实现对得上"：
- I-5：CLI 命令表必须恰好是六个真实命令；看板动作（含 status）要单独成表，不能混进命令表；
- I-6：模块文档里的【待实现后填写，如 src/xxx.py】占位必须明确标为待实现，不能让人以为已经有这个文件。
"""

from __future__ import annotations

import re
from pathlib import Path

from src import cli

DOCS = Path("项目文档")


def _section(text: str, heading: str) -> str:
    """取某个 ## 小节的内容（到下一个 ## 为止）。"""
    start = text.find(heading)
    assert start >= 0, f"文档里找不到小节：{heading}"
    rest = text[start + len(heading):]
    end = rest.find("\n## ")
    return rest if end < 0 else rest[:end]


def _table_commands(section: str) -> set[str]:
    """命令表第一列里用反引号包起来的命令名。"""
    commands = set()
    for row in re.findall(r"^\| \`([^\`|]+)\`", section, re.M):
        commands.add(row.strip().split()[0])
    return commands


def test_cli_command_table_matches_known_commands():
    text = (DOCS / "模块-命令行入口.md").read_text(encoding="utf-8")
    table = _section(text, "## 7.1 命令表与退出码约定")
    commands = _table_commands(table)

    assert commands == set(cli.KNOWN_COMMANDS)


def test_board_actions_live_in_their_own_table():
    text = (DOCS / "模块-命令行入口.md").read_text(encoding="utf-8")
    cli_table = _section(text, "## 7.1 命令表与退出码约定")
    board_table = _section(text, "## 7.2 看板（serve）的交互动作集")

    assert "status" not in cli_table
    assert "status" in board_table
    assert "固定动作集" in board_table


def test_documented_placeholder_files_are_marked_pending():
    """引用不存在的文件时必须标明是待实现占位。"""
    problems = []
    for docfile in DOCS.glob("模块-*.md"):
        text = docfile.read_text(encoding="utf-8")
        for match in re.finditer(r"src/([a-z_]+\.py)", text):
            name = match.group(1)
            if Path("src", name).exists():
                continue
            window = text[max(0, match.start() - 200): match.start() + 200]
            if "待实现" not in window:
                problems.append(f"{docfile.name}: src/{name} 不存在且未标注待实现")

    assert problems == []


def test_module_docs_only_reference_existing_source_files_or_mark_pending():
    """模块文档里所有 src/*.py 引用：要么文件存在，要么明确标注待实现。"""
    for docfile in DOCS.glob("模块-*.md"):
        text = docfile.read_text(encoding="utf-8")
        for name in sorted(set(re.findall(r"src/([a-z_]+\.py)", text))):
            if Path("src", name).exists():
                continue
            index = text.find(f"src/{name}")
            window = text[max(0, index - 200): index + 200]
            assert "待实现" in window, f"{docfile.name} 里的 src/{name} 既不存在也未标待实现"


def test_book_module_doc_points_to_current_minimal_implementation():
    """T-007 已经把 import 的最小实现落到了 src/syllabus.py，文档应指出来。"""
    text = (DOCS / "模块-书籍蒸馏导入.md").read_text(encoding="utf-8")

    assert "syllabus.py" in text or "cli.py" in text