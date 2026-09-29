"""T-010：import 命令（蒸馏稿 → 知识地图）+ 分块提炼策略。

设计要点：

- 蒸馏稿单文件 67K~129K 字符，**不能整本塞进一次 LLM 调用**：按章节标题切块、逐块提炼再合并；
- 格式不符要**指出缺什么**（缺 frontmatter / 缺书名 / 正文为空），且不破坏既有地图；
- 地图只存「章节名 + 知识点名称」，不抄原文段落（A-05）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import re

from .llm import LLMError

__all__ = [
    "BookMap",
    "Chapter",
    "DistillateInfo",
    "Section",
    "SyllabusError",
    "build_import_messages",
    "chunk_book",
    "import_book",
    "load_syllabus",
    "merge_chapters",
    "parse_chapters",
    "parse_syllabus",
    "read_book_title",
    "render_syllabus",
    "split_sections",
    "validate_distillate",
    "write_syllabus",
]

DEFAULT_SYLLABUS_PATH = Path("profile") / "syllabus.md"
FRONTMATTER_PATTERN = "---*"
# 块上限（T-010 实测选定）：实测蒸馏稿的二级节最大 16.7K 字符，
# 取 30000 可让绝大多数章节**不被硬切**（保住章节语义），同时把 7 本书的调用数从 60 降到 25。
DEFAULT_CHUNK_CHARS = 30000
DEFAULT_SECTION_LEVEL = 2
_TITLE_KEYS = ("title", "书名", "book")

_FENCE_RE = re.compile(r"^```(?:json)?\s*\n(?P<body>.*?)\n```\s*$", re.M | re.S)
_FRONTMATTER_RE = re.compile(r"^---\s*\n(?P<body>.*?)\n---\s*\n?", re.S)
_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<name>.+?)\s*$")
_CHAPTER_RE = re.compile(r"^##\s+(?P<name>.+?)\s*$")
_POINT_RE = re.compile(r"^\s*[-*]\s+(?P<name>.+?)\s*$")
_FENCE_CHAR = chr(96) * 3
_JSON_FENCE_RE = re.compile("^" + _FENCE_CHAR + "(?:json)?\\s*\\n(?P<body>.*?)\\n" + _FENCE_CHAR + "\\s*$", re.M | re.S)


class SyllabusError(RuntimeError):
    """蒸馏稿不合约定或 LLM 输出不可用。"""


@dataclass
class Chapter:
    chapter: str
    points: list[str] = field(default_factory=list)


@dataclass
class BookMap:
    book: str
    chapters: list[Chapter] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "book": self.book,
            "chapters": [{"chapter": c.chapter, "points": list(c.points)} for c in self.chapters],
        }


@dataclass(frozen=True)
class DistillateInfo:
    """校验通过后的蒸馏稿信息。"""

    book: str
    body: str
    characters: int
    sections: int


@dataclass(frozen=True)
class Section:
    heading: str
    body: str


SYSTEM_PROMPT = """你是学习资料整理助手，负责把一份书籍蒸馏稿的**某个片段**整理成章节与知识点。

要求：
1. 只输出章节名与该章涉及的知识点名称，**不要抄录原文段落**。
2. 输出一个 JSON 数组，每个元素形如 {"chapter": "第 4 章 函数", "points": ["函数定义", "参数", "返回值"]}。
3. 知识点名称要短、可用于后续出题（如「列表推导式」），不要写整句解释。
4. 按片段里的原有顺序输出；只覆盖本片段出现的章节，不要臆造。
5. 只输出 JSON，不要输出其它文字。
"""


def validate_distillate(markdown: str, fallback: str = "") -> DistillateInfo:
    """校验蒸馏稿格式；不合约定就指出**缺什么**。

    规则（T-010）：
    - 必须有 frontmatter（--- 开头的那一段）；
    - frontmatter 里必须有书名（title / 书名 / book 任一）；
    - 去掉 frontmatter 后正文不能为空。
    """
    text = markdown or ""
    if not text.strip():
        raise SyllabusError("蒸馏稿是空文件：缺书名 frontmatter，也缺正文")

    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise SyllabusError(
            "蒸馏稿缺 frontmatter：文件必须以 --- 开头，并在里面写书名，例如"
            "\n---\ntitle: 书名\n---"
        )

    title = ""
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        if key.strip().lower() in _TITLE_KEYS:
            title = value.strip().strip('"').strip("'")
            break
    if not title:
        raise SyllabusError(
            "蒸馏稿的 frontmatter 里缺书名：请加一行 title: 书名（也接受 book: 或 书名:）"
        )

    body = text[match.end():]
    if not body.strip():
        raise SyllabusError(f"蒸馏稿《{title}》的正文是空的：frontmatter 之后没有任何内容")

    return DistillateInfo(
        book=title,
        body=body.strip(),
        characters=len(body.strip()),
        sections=len(split_sections(body)),
    )


def split_sections(text: str, level: int = DEFAULT_SECTION_LEVEL) -> list[Section]:
    """按指定级别的标题切分；该级别不存在时退而切所有级别标题。"""
    lines = (text or "").splitlines()
    headings: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match:
            headings.append((index, match.group("hashes")))

    chosen = level
    if headings and not any(len(hashes) == level for _index, hashes in headings):
        chosen = min(len(hashes) for _index, hashes in headings)

    marks = [line_index for line_index, hashes in headings if len(hashes) == chosen]
    if not marks:
        stripped = (text or "").strip()
        return [Section(heading="", body=stripped)] if stripped else []

    sections: list[Section] = []
    for position, line_index in enumerate(marks):
        end = marks[position + 1] if position + 1 < len(marks) else len(lines)
        heading = _HEADING_RE.match(lines[line_index]).group("name").strip()
        sections.append(Section(heading=heading, body="\n".join(lines[line_index:end]).strip()))
    return sections


def chunk_book(text: str, max_chars: int = DEFAULT_CHUNK_CHARS) -> list[str]:
    """把蒸馏稿按章节边界切块，避免整本塞进一次 LLM 调用。

    - 在章节边界处断开（不切碎章节内容）；
    - 单节超过上限时硬切（保底，避免一块过大）；
    - 不丢内容：所有块拼起来等于原文（只差块间空白）。
    """
    if max_chars <= 0:
        raise SyllabusError("分块大小必须是正数")
    stripped = (text or "").strip()
    if not stripped:
        return []
    if len(stripped) <= max_chars:
        return [stripped]

    sections = split_sections(stripped)
    pieces: list[Section] = []
    for section in sections:
        if section.body and len(section.body) > max_chars:
            for start in range(0, len(section.body), max_chars):
                pieces.append(Section(heading=section.heading, body=section.body[start:start + max_chars]))
        else:
            pieces.append(section)

    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for piece in pieces:
        body = piece.body.strip()
        if not body:
            continue
        if current and size + len(body) > max_chars:
            chunks.append("\n\n".join(current))
            current, size = [], 0
        current.append(body)
        size += len(body)
    if current:
        chunks.append("\n\n".join(current))
    return chunks or [stripped]


def read_book_title(markdown: str, fallback: str = "") -> str:
    """兼容入口：从蒸馏稿取书名，取不到就用 fallback。

    T-010 起「必须写书名」由 validate_distillate 强制；本函数保留给「只想读一眼书名」的调用方。
    """
    try:
        return validate_distillate(markdown, fallback).book
    except SyllabusError:
        return fallback


def build_import_messages(title: str, body: str, *, index: int = 0, total: int = 1) -> list[dict[str, str]]:
    """构造一次调用的消息。**不再截断正文**：分块由 chunk_book 负责。"""
    header = f"书名：{title}\n"
    if total > 1:
        header += f"（这是第 {index + 1}/{total} 个片段，只需覆盖本片段出现的章节）\n"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": header + "\n蒸馏稿片段：\n\n" + body.strip()},
    ]


def merge_chapters(groups: list[list[Chapter]]) -> list[Chapter]:
    """合并多块提炼结果：章节按首次出现顺序，知识点去重保序。"""
    order: list[str] = []
    point_map: dict[str, list[str]] = {}
    for chapters in groups:
        for chapter in chapters:
            name = (chapter.chapter or "").strip()
            if not name:
                continue
            if name not in point_map:
                order.append(name)
                point_map[name] = []
            for point in chapter.points:
                text = str(point).strip()
                if text and text not in point_map[name]:
                    point_map[name].append(text)
    return [Chapter(chapter=name, points=point_map[name]) for name in order]


def parse_chapters(raw: str) -> list[Chapter]:
    """解析 LLM 返回的章节 JSON。容忍 ```json 围栏与前后多余文字。"""
    text = (raw or "").strip()
    fenced = _JSON_FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1).strip()

    starts = [index for index in (text.find("["), text.find("{")) if index >= 0]
    if not starts:
        raise SyllabusError("LLM 输出里找不到 JSON")
    decoder = json.JSONDecoder()
    payload = None
    last_error: Exception | None = None
    for start in sorted(starts):
        try:
            payload, _ = decoder.raw_decode(text[start:])
            break
        except ValueError as exc:
            last_error = exc
    if payload is None:
        raise SyllabusError(f"LLM 输出的 JSON 无法解析：{last_error}")

    if isinstance(payload, dict):
        payload = payload.get("chapters") or payload.get("chapter") or []
    if not isinstance(payload, list):
        raise SyllabusError("LLM 输出的章节不是数组")

    chapters: list[Chapter] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("chapter") or item.get("name") or "").strip()
        raw_points = item.get("points") or item.get("knowledge_points") or []
        if isinstance(raw_points, str):
            raw_points = [raw_points]
        points = [str(p).strip() for p in raw_points if str(p).strip()]
        if name or points:
            chapters.append(Chapter(chapter=name or "未命名章节", points=points))
    if not chapters:
        raise SyllabusError("LLM 没有给出任何章节")
    return chapters



def render_syllabus(books: list[BookMap]) -> str:
    lines = ["# 知识地图", ""]
    # 不排序：书序就是调用方给的顺序（导入顺序），A-06 的「按书序」依赖它
    for book in books:
        lines += [f"## {book.book}", ""]
        for chapter in book.chapters:
            lines.append(f"### {chapter.chapter}")
            lines.append("")
            for point in chapter.points:
                lines.append(f"- {point}")
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def parse_syllabus(markdown: str) -> list[BookMap]:
    books: list[BookMap] = []
    current_book: BookMap | None = None
    current_chapter: Chapter | None = None

    for raw in (markdown or "").splitlines():
        line = raw.rstrip()
        book_match = re.match(r"^##\s+(?!#)(?P<name>.+?)\s*$", line)
        if book_match:
            current_book = BookMap(book=book_match.group("name"))
            books.append(current_book)
            current_chapter = None
            continue
        chapter_match = re.match(r"^###\s+(?P<name>.+?)\s*$", line)
        if chapter_match and current_book is not None:
            current_chapter = Chapter(chapter=chapter_match.group("name"))
            current_book.chapters.append(current_chapter)
            continue
        point_match = _POINT_RE.match(line)
        if point_match and current_chapter is not None:
            current_chapter.points.append(point_match.group("name"))
    return books


def load_syllabus(path: Path | str) -> list[BookMap]:
    target = Path(path)
    if not target.is_file():
        return []
    return parse_syllabus(target.read_text(encoding="utf-8", errors="replace"))


def write_syllabus(path: Path | str, books: list[BookMap]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    try:
        tmp.write_text(render_syllabus(books), encoding="utf-8")
        tmp.replace(target)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise SyllabusError(f"写入知识地图失败：{target}（{type(exc).__name__}）") from None
    return target


def import_book(
    book_path: Path | str,
    *,
    completer,
    syllabus_path: Path | str = DEFAULT_SYLLABUS_PATH,
    max_chars: int = DEFAULT_CHUNK_CHARS,
    on_progress=None,
) -> tuple[BookMap, Path]:
    """把一本书的蒸馏稿导入知识地图，返回 (该书地图, 落盘路径)。

    T-010：长稿**分块提炼**再合并，不把整本塞进一次调用；格式不符直接报错且不动地图。
    """
    source = Path(book_path)
    if not source.is_file():
        raise SyllabusError(f"找不到蒸馏稿：{source}")
    try:
        markdown = source.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SyllabusError(f"读取蒸馏稿失败：{source}（{type(exc).__name__}）") from None

    info = validate_distillate(markdown, source.stem)
    chunks = chunk_book(info.body, max_chars=max_chars)
    if not chunks:
        raise SyllabusError(f"蒸馏稿《{info.book}》没有可提炼的正文")

    groups: list[list[Chapter]] = []
    total = len(chunks)
    for index, chunk in enumerate(chunks):
        if on_progress:
            on_progress(index + 1, total)
        try:
            raw = completer.complete(build_import_messages(info.book, chunk, index=index, total=total))
        except LLMError as exc:
            raise SyllabusError(f"LLM 调用失败（第 {index + 1}/{total} 块）：{exc}") from None
        except Exception as exc:
            raise SyllabusError(f"LLM 调用失败（第 {index + 1}/{total} 块）：{type(exc).__name__}") from None
        try:
            groups.append(parse_chapters(raw))
        except SyllabusError as exc:
            # 指明是第几块失败：长稿续跑时能判断"从哪继续"
            raise SyllabusError(f"第 {index + 1}/{total} 块提炼失败：{exc}") from None

    book = BookMap(book=info.book, chapters=merge_chapters(groups))

    target = Path(syllabus_path)
    existing = [b for b in load_syllabus(target) if b.book != book.book]  # 同名书覆盖，其余保留
    existing.append(book)
    write_syllabus(target, existing)
    return book, target
