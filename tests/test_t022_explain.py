"""T-022 失败测试：章节讲解 explain（F-10）。

流程（任务卡）：地图定位知识点 → 所属书/章 → 取参考文本（优先 books/ 蒸馏稿对应章节；
books/_src/ 有原书时取原书章节）→ LLM 生成讲解。

硬性约束：

- 单次输入 ≤ 3000 字符，超额截断并注明；
- 知识点不在地图里 → **明确报错，不瞎编**；
- 输出要注明出处（书 + 章）。

素材约定（books/_src/README.md）：前缀 ↔ 书名对照；每书 .txt/.toc.md/.index.md/.code.md；
蒸馏稿里 `L####` 行号即指向 .txt 的行。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.explain import (
    MAX_REFERENCE_CHARS,
    match_source_prefix,
    read_source_prefix,
    TRUNCATED_NOTE,
    ExplainError,
    build_explain_messages,
    explain_point,
    find_explain_source,
    load_source_map,
    read_source_lines,
)
from src.profile import KnowledgeProfile
from src.syllabus import BookMap, Chapter, write_syllabus


SOURCE_README = """# _src 说明

## 一、命名对照

| 文件名前缀 | 书 | 真实格式 | 正文行数 | 字符数 |
|---|---|---|---|---|
| `head-first-html-css` | Head First HTML and CSS, 2nd Edition | EPUB → txt | 29,395 | 977,579 |
| `python-crash-course` | Python Crash Course, 3rd Edition | EPUB → txt | 20,640 | 1,075,698 |
"""


DISTILLATE = """---
book: Head First HTML and CSS（第 2 版）
---

## 5. 分章要点

### 第 1 章 认识 HTML（L100–L200）

**概念**：标签与元素的构成；h1 到 h6 六级标题；文档骨架。

### 第 2 章 深入超文本（L201–L300）

**概念**：a 标签创建超链接；href 属性指定目的地。
"""


def make_sources(tmp_path) -> tuple[Path, Path]:
    src = tmp_path / "_src"
    src.mkdir()
    (src / "README.md").write_text(SOURCE_README, encoding="utf-8")
    body = ["第 %d 行内容" % i for i in range(1, 401)]
    body[99] = "h1 到 h6 六级标题：用 h1 表示主标题，h2 表示次级标题"
    body[101] = "标签与元素的构成：标签由尖括号包围"
    (src / "head-first-html-css.txt").write_text("\n".join(body), encoding="utf-8")

    books = tmp_path / "books"
    books.mkdir()
    (books / "蒸馏-HeadFirst-HTML-CSS-2e.md").write_text(DISTILLATE, encoding="utf-8")
    return src, books


def profile_with(*names, level="存疑"):
    from src.distill import KnowledgePoint

    return KnowledgeProfile(points=[KnowledgePoint(n, level, "e") for n in names])


def syllabus_map():
    return [BookMap(book="Head First HTML and CSS（第 2 版）", chapters=[
        Chapter("第 1 章 认识 HTML", ["h1 到 h6 六级标题", "标签与元素的构成"]),
        Chapter("第 2 章 深入超文本", ["a 标签创建超链接"]),
    ])]


# --- 1. 命名对照表 ------------------------------------------------------------


def test_load_source_map_parses_prefix_table(tmp_path):
    src, _books = make_sources(tmp_path)

    mapping = load_source_map(src / "README.md")

    assert mapping["head-first-html-css"] == "Head First HTML and CSS, 2nd Edition"
    assert "python-crash-course" in mapping


def test_load_source_map_missing_file_returns_empty(tmp_path):
    assert load_source_map(tmp_path / "nope.md") == {}


# --- 2. 定位参考文本 ----------------------------------------------------------


def test_find_source_locates_point_in_syllabus(tmp_path):
    src, books = make_sources(tmp_path)

    found = find_explain_source(
        "h1 到 h6 六级标题",
        syllabus_map(),
        books_dir=books,
        src_dir=src,
    )

    assert found.book.startswith("Head First")
    assert "第 1 章" in found.chapter


def test_find_source_rejects_point_not_in_map(tmp_path):
    src, books = make_sources(tmp_path)

    with pytest.raises(ExplainError) as exc:
        find_explain_source("完全不在地图里的知识点", syllabus_map(), books_dir=books, src_dir=src)

    assert "地图" in str(exc.value)


def test_find_source_reads_original_lines_when_available(tmp_path):
    src, books = make_sources(tmp_path)

    reference = find_explain_source("h1 到 h6 六级标题", syllabus_map(), books_dir=books, src_dir=src)

    assert "h1 到 h6 六级标题" in reference.text
    assert "第 100 行" in reference.text or "第 101 行" in reference.text
    assert reference.origin_kind == "原文"


def test_find_source_falls_back_to_distillate(tmp_path):
    """没有 _src 原书时，用蒸馏稿里那一章的内容。"""
    _src, books = make_sources(tmp_path)

    reference = find_explain_source(
        "a 标签创建超链接", syllabus_map(), books_dir=books, src_dir=tmp_path / "nope"
    )

    assert "a 标签创建超链接" in reference.text
    assert reference.origin_kind == "蒸馏稿"


def test_reference_is_truncated_to_limit(tmp_path):
    src, books = make_sources(tmp_path)
    # 造一个超长章节（蒸馏稿兜底路径也要能触发截断）
    long_section = "".join("很长的一行 " + "填充" * 200 + "\n" for _ in range(40))
    (books / "蒸馏-HeadFirst-HTML-CSS-2e.md").write_text(
        "---\nbook: Head First HTML and CSS（第 2 版）\n---\n\n"
        "## 5. 分章要点\n\n### 第 1 章 认识 HTML（L100–L200）\n\n" + long_section,
        encoding="utf-8",
    )
    # 同时让 _src 不可用，确保走蒸馏稿路径
    reference = find_explain_source(
        "h1 到 h6 六级标题", syllabus_map(), books_dir=books, src_dir=tmp_path / "nope"
    )

    assert len(reference.text) <= MAX_REFERENCE_CHARS + len(TRUNCATED_NOTE) + 50
    assert TRUNCATED_NOTE.strip() in reference.text


def test_read_source_lines_is_one_based(tmp_path):
    src, _books = make_sources(tmp_path)

    text = read_source_lines(src / "head-first-html-css.txt", 1, 3)

    assert text.splitlines()[0] == "第 1 行内容"
    assert len(text.splitlines()) == 3


def test_read_source_lines_clamps_out_of_range(tmp_path):
    src, _books = make_sources(tmp_path)

    text = read_source_lines(src / "head-first-html-css.txt", 400, 99999)

    assert "第 400 行内容" in text


# --- 3. LLM 讲解 --------------------------------------------------------------


class Stub:
    def __init__(self):
        self.prompts: list[str] = []

    def complete(self, messages):
        self.prompts.append(messages[-1]["content"])
        return "这是讲解正文。\n\n- 要点一\n- 要点二"


def test_build_explain_messages_includes_reference_and_source(tmp_path):
    src, books = make_sources(tmp_path)
    reference = find_explain_source("h1 到 h6 六级标题", syllabus_map(), books_dir=books, src_dir=src)

    messages = build_explain_messages("h1 到 h6 六级标题", reference)

    prompt = messages[-1]["content"]
    assert "h1 到 h6 六级标题" in prompt
    assert reference.text[:200] in prompt
    assert "第 1 章" in prompt


def test_explain_point_returns_text_with_source(tmp_path):
    src, books = make_sources(tmp_path)
    stub = Stub()

    result = explain_point("h1 到 h6 六级标题", syllabus_map(), completer=stub,
                           books_dir=books, src_dir=src)

    assert "这是讲解正文" in result.text
    assert result.book.startswith("Head First")
    assert "第 1 章" in result.chapter
    assert stub.prompts and "第 1 章" in stub.prompts[0]


def test_explain_point_truncates_reference_before_llm(tmp_path):
    src, books = make_sources(tmp_path)
    long_lines = ["很长的一行 " + "填充" * 300 for _ in range(30)]
    (src / "head-first-html-css.txt").write_text("\n".join(long_lines), encoding="utf-8")
    stub = Stub()

    explain_point("h1 到 h6 六级标题", syllabus_map(), completer=stub, books_dir=books, src_dir=src)

    prompt = stub.prompts[0]
    assert len(prompt) <= MAX_REFERENCE_CHARS + 2000


def test_explain_point_rejects_unknown_point(tmp_path):
    src, books = make_sources(tmp_path)

    with pytest.raises(ExplainError):
        explain_point("不存在的东西", syllabus_map(), completer=Stub(), books_dir=books, src_dir=src)


def test_explain_point_reports_llm_failure(tmp_path):
    src, books = make_sources(tmp_path)

    class Boom:
        def complete(self, messages):
            raise RuntimeError("网络断了")

    with pytest.raises(ExplainError) as exc:
        explain_point("h1 到 h6 六级标题", syllabus_map(), completer=Boom(), books_dir=books, src_dir=src)

    assert "LLM" in str(exc.value) or "调用" in str(exc.value)

# --- 4. 显式前缀优先（实测：按书名猜前缀不可靠） ------------------------------


def test_find_source_prefers_explicit_prefix_in_frontmatter(tmp_path):
    """实测：按书名猜 _src 前缀不可靠（译名差异大，覆盖率 0.11~0.78 都有）。

    所以蒸馏稿 frontmatter 里显式写 source 前缀时应直接采信。
    """
    src, books = make_sources(tmp_path)
    (books / "蒸馏-HeadFirst-HTML-CSS-2e.md").write_text(
        "---\nbook: 随便一个对不上的书名\nsource: head-first-html-css\n---\n\n"
        "## 5. 分章要点\n\n### 第 1 章 认识 HTML（L100–L200）\n\n**概念**：x\n",
        encoding="utf-8",
    )

    reference = find_explain_source(
        "h1 到 h6 六级标题", syllabus_map(), books_dir=books, src_dir=src
    )

    assert reference.origin_kind == "原文"
    assert "第 100 行" in reference.text or "第 101 行" in reference.text


def test_read_frontmatter_source_prefix(tmp_path):
    from src.explain import read_source_prefix

    path = tmp_path / "d.md"
    path.write_text("---\nbook: X\nsource: python-crash-course\n---\n\n正文\n", encoding="utf-8")

    assert read_source_prefix(path) == "python-crash-course"


def test_read_source_prefix_returns_none_when_absent(tmp_path):
    from src.explain import read_source_prefix

    path = tmp_path / "d.md"
    path.write_text("---\nbook: X\n---\n\n正文\n", encoding="utf-8")

    assert read_source_prefix(path) is None


def test_prefix_matching_tolerates_translated_titles(tmp_path):
    """对照表书名与地图书名是译名差异时，也要能对上（用覆盖率评分）。"""
    from src.explain import match_source_prefix

    mapping = {"head-first-html-css": "Head First HTML and CSS, 2nd Edition"}

    assert match_source_prefix("Head First HTML 与 CSS（第 2 版）", mapping) == "head-first-html-css"


def test_prefix_matching_rejects_unrelated(tmp_path):
    from src.explain import match_source_prefix

    mapping = {"head-first-html-css": "Head First HTML and CSS, 2nd Edition"}

    assert match_source_prefix("鸟哥的 Linux 私房菜", mapping) is None

# --- 5. 仓库里的真实素材：7 份蒸馏稿都要显式声明 source 前缀 --------------------


def test_shipped_distillates_declare_source_prefix():
    """7 份真实蒸馏稿都应在 frontmatter 里写明 _src 前缀（否则只能按书名猜，不可靠）。"""
    from src.explain import load_source_map, read_source_prefix

    mapping = load_source_map(Path("books/_src/README.md"))
    problems = []
    for path in sorted(Path("books").glob("蒸馏-*.md")):
        prefix = read_source_prefix(path)
        if not prefix:
            problems.append(f"{path.name}: 没写 source 前缀")
        elif prefix not in mapping:
            problems.append(f"{path.name}: source={prefix} 不在 _src 对照表里")

    assert problems == []


def test_shipped_source_files_exist_for_every_prefix():
    from src.explain import load_source_map

    missing = []
    for prefix in load_source_map(Path("books/_src/README.md")):
        for suffix in (".txt", ".toc.md", ".index.md", ".code.md"):
            if not Path("books/_src", prefix + suffix).is_file():
                missing.append(prefix + suffix)

    assert missing == []

# --- 6. 真实蒸馏稿的标题区间格式（实测发现纯数字、L 前缀、尾随符号三种） --------


@pytest.mark.parametrize(
    "heading,expected",
    [
        ("### 第 1 章 · getting to know HTML（1266–2881）", (1266, 2881)),   # 纯数字
        ("### 第 1 章 Getting Started（L3990–4252）", (3990, 4252)),          # L 前缀
        ("### 第 1 章 A Brief History of JavaScript（L69–L212）", (69, 212)),  # 两侧都带 L
        ("### 第 1 章 Getting Started（L2748–L8603）✅", (2748, 8603)),        # 尾随符号
        ("#### 第 1 章 认识 HTML（L100-L200）", (100, 200)),                   # 半角连字符
    ],
)
def test_chapter_range_accepts_real_heading_formats(tmp_path, heading, expected):
    from src.explain import _chapter_range

    text = "## 5. 分章要点\n\n" + heading + "\n\n正文\n"

    assert _chapter_range(text, "第 1 章") == expected


def test_chapter_range_ignores_non_line_ranges():
    """像「Part I：Basics（第 1–11 章）」「（带标签关系句，47 条）」不是行号区间。"""
    from src.explain import _chapter_range

    text = "### Part I：Basics（第 1–11 章）\n\n### 4.1 小节（带标签关系句，47 条）\n"

    assert _chapter_range(text, "Part I") is None
