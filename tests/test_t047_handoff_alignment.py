"""T-047 失败测试：接力上下文第 4 段（书籍出处）必须用对齐后的地图查。

现象（2026-09-29 实测，nav.html 那道题）：
`profile/syllabus.md` 里明明有《Head First HTML 与 CSS（第 2 版）》的第 2/3/4 章，
`profile/alignment.json` 里也早就有映射，可生成出来的
`profile/handoff/2026-09-29-1341.md` 第 4 段四个知识点**全部**是
「（知识地图里找不到这个知识点…）」—— 出题（next）和接力（handoff）两条路
对同一份数据给出了两套结论。

根因：`op_handoff` 拿 `load_syllabus` 的**原始**地图去查。地图点存的是书上的
原话（「id 做页面内锚点」「a 标签创建超链接」），任务卡记的是**画像概念名**
（「超链接 a 标签（href/target）」），两边精确同名交集是 0。
`next` 早在 T-021 就做了 `apply_alignment`，handoff 这条路径漏了这一步。

要求：
1. 有 alignment.json 时，第 4 段按对齐后的名字给出「书 · 章」；
2. 没有 alignment.json 时退回原始地图，不报错、不崩；
3. 任务卡里直接写的**地图原名**仍要能精确命中（别把原来的能力改坏）。
"""

from __future__ import annotations

import json

from src.distill import KnowledgePoint
from src.profile import KnowledgeProfile, write_profile_atomic
from src.syllabus import BookMap, Chapter, render_syllabus

TASKS_MD = """# 任务记录

## 2026-09-29 13:41

**目标**：做一个 nav.html：顶部一条导航，点链接跳到页内小节

**用到的知识点**：超链接 a 标签（href/target）、列表（ul/ol/li）

**验收方式**：点导航每一项，页面都滚到对应小节
"""

TASKS_MD_RAW_NAMES = """# 任务记录

## 2026-09-29 13:41

**目标**：做一个 nav.html

**用到的知识点**：id 做页面内锚点

**验收方式**：点导航能跳到对应小节
"""

BOOKS = [
    BookMap(
        "Head First HTML 与 CSS（第 2 版）",
        [
            Chapter("第 2 章 深入超文本", ["a 标签创建超链接", "href 属性指定目的地"]),
            Chapter("第 3 章 网页构造", ["ul 与 ol 列表"]),
            Chapter("第 4 章 连接上网", ["id 做页面内锚点", "target 开新窗口"]),
        ],
    )
]

ALIGNMENT = {
    "version": 1,
    "mapped": 4,
    "total": 4,
    "alignments": [
        {"point": "a 标签创建超链接", "profile": "超链接 a 标签（href/target）", "confidence": "high"},
        {"point": "href 属性指定目的地", "profile": "超链接 a 标签（href/target）", "confidence": "high"},
        {"point": "ul 与 ol 列表", "profile": "列表（ul/ol/li）", "confidence": "high"},
        {"point": "id 做页面内锚点", "profile": "超链接 a 标签（href/target）", "confidence": "high"},
        {"point": "target 开新窗口", "profile": "超链接 a 标签（href/target）", "confidence": "high"},
    ],
}


def make_directory(tmp_path, tasks_md=TASKS_MD, with_alignment=True):
    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    write_profile_atomic(
        directory / "knowledge.md",
        KnowledgeProfile(
            points=[
                KnowledgePoint("超链接 a 标签（href/target）", "学过", "e"),
                KnowledgePoint("列表（ul/ol/li）", "学过", "e"),
            ]
        ),
    )
    (directory / "tasks.md").write_text(tasks_md, encoding="utf-8")
    (directory / "syllabus.md").write_text(render_syllabus(BOOKS), encoding="utf-8")
    if with_alignment:
        (directory / "alignment.json").write_text(
            json.dumps(ALIGNMENT, ensure_ascii=False), encoding="utf-8"
        )
    return directory


def make_board(tmp_path, directory):
    from src import cli

    return cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )


def book_section(directory) -> str:
    """取生成出来的接力上下文第 4 段。"""
    files = list((directory / "handoff").glob("*.md"))
    assert files, "没有生成接力上下文文件"
    text = files[0].read_text(encoding="utf-8")
    assert "## 四、书籍出处与章节" in text
    return text.split("## 四、书籍出处与章节")[1].split("## 五、")[0]


# ---------- 1. 对齐后的名字要能查到出处 ----------


def test_book_section_uses_aligned_names(tmp_path):
    directory = make_directory(tmp_path)
    board = make_board(tmp_path, directory)
    board.run_action("handoff", {"task": "2026-09-29 13:41"})

    section = book_section(directory)
    assert "《Head First HTML 与 CSS（第 2 版）》" in section
    assert "第 2 章 深入超文本" in section
    assert "第 3 章 网页构造" in section
    assert "知识地图里找不到这个知识点" not in section


# ---------- 2. 没有 alignment.json 时退回原始地图，不报错 ----------


def test_book_section_falls_back_without_alignment(tmp_path):
    directory = make_directory(tmp_path, with_alignment=False)
    board = make_board(tmp_path, directory)
    board.run_action("handoff", {"task": "2026-09-29 13:41"})

    section = book_section(directory)
    assert "知识地图里找不到这个知识点" in section  # 画像名查不到原始地图，如实写明


# ---------- 3. 地图原名仍然精确命中（原有能力不许改坏）----------


def test_book_section_still_matches_raw_map_names(tmp_path):
    directory = make_directory(tmp_path, tasks_md=TASKS_MD_RAW_NAMES, with_alignment=True)
    board = make_board(tmp_path, directory)
    board.run_action("handoff", {"task": "2026-09-29 13:41"})

    section = book_section(directory)
    assert "第 4 章 连接上网" in section
    assert "知识地图里找不到这个知识点" not in section
