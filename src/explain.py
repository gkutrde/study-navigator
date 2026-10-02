"""T-022：章节讲解 explain（F-10）。

流程：地图定位知识点 → 所属书/章 → 取参考文本 → LLM 生成讲解。

参考文本优先级：

1. **原文**：`books/_src/<前缀>.txt`（按蒸馏稿里的 `L####` 行号区间截取）—— 最准确；
2. **蒸馏稿**：`books/蒸馏-*.md` 里对应章节的内容 —— 兜底。

硬性约束：

- 单次送 LLM 的参考文本 **≤ MAX_REFERENCE_CHARS**，超额截断并在文中注明；
- 知识点**不在地图里就报错**，绝不瞎编；
- 输出必须能注明出处（书 + 章）。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

from .fileio import read_text_or_none, write_text_atomic
from .llm import LLMError
from .syllabus import BookMap

DEFAULT_BOOKS_DIR = Path("books")
DEFAULT_SRC_DIR = Path("books") / "_src"
# 单次送 LLM 的参考文本上限（任务卡硬性要求）
MAX_REFERENCE_CHARS = 3000
TRUNCATED_NOTE = f"\n\n（参考文本过长，已截断到前 {MAX_REFERENCE_CHARS} 字符）"

_PREFIX_ROW_RE = re.compile(r"^\|\s*`(?P<prefix>[a-z0-9-]+)`\s*\|\s*(?P<book>[^|]+?)\s*\|", re.M)
# 真实蒸馏稿里区间有四种写法（实测）：
#   （1266–2881） 纯数字      （L3990–4252） L 前缀
#   （L69–L212）  两侧都带 L  （L2748–L8603）✅  尾随符号
# 行号要求 ≥3 位，避免把「（第 1–11 章）」「（带标签关系句，47 条）」当成行号区间。
# 「第 12 章」→ 12；用于章名中英不一致时的兜底匹配
_CHAPTER_NO_RE = re.compile(r"第\s*(\d{1,3})\s*章")
# 「8.1 结构：…」这类小节名：按章号兜底匹配时要排除它们
_SUBSECTION_RE = re.compile(r"^\d+\.\d+")
_BOOK_FIELD_RE = re.compile(r"^book:\s*(.+)$", re.M)
_SOURCE_FIELD_RE = re.compile(r"^source:\s*([A-Za-z0-9-]+)\s*$", re.M)
# frontmatter 只看文件开头这么多字符
_HEAD_CHARS = 600


def _chapter_number(text: str) -> str | None:
    match = _CHAPTER_NO_RE.search(str(text or ""))
    return match.group(1) if match else None


_CHAPTER_RANGE_RE = re.compile(
    r"^(?P<hashes>#{2,4})\s*(?P<name>.+?)\s*[（(]\s*L?(?P<start>\d{2,})\s*[–\-—~]\s*L?(?P<end>\d{2,})\s*[）)]\s*\S*\s*$",
    re.M,
)


class ExplainError(RuntimeError):
    """讲解失败：知识点不在地图里、参考文本取不到或 LLM 不可用。"""


@dataclass(frozen=True)
class SourceLocator:
    """知识点在地图里的位置。"""

    point: str
    book: str
    chapter: str
    line_start: int | None = None
    line_end: int | None = None


@dataclass(frozen=True)
class ExplainSource:
    """取到的参考文本。"""

    point: str
    book: str
    chapter: str
    text: str
    origin_kind: str          # 「原文」或「蒸馏稿」
    origin_detail: str        # 具体文件与行号，用于注明出处
    locator: SourceLocator


@dataclass(frozen=True)
class ExplainResult:
    text: str
    book: str
    chapter: str
    origin_kind: str
    origin_detail: str
    from_cache: bool = False

    def render(self) -> str:
        suffix = "（来自缓存）" if self.from_cache else ""
        return (
            f"{self.text.strip()}\n\n"
            f"**出处**：{self.book} · {self.chapter}"
            f"（参考 {self.origin_kind}：{self.origin_detail}）{suffix}"
        )


def load_source_map(readme_path: Path | str) -> dict[str, str]:
    """解析 `books/_src/README.md` 的「前缀 ↔ 书名」对照表。"""
    text = read_text_or_none(readme_path) or ""
    mapping: dict[str, str] = {}
    for match in _PREFIX_ROW_RE.finditer(text):
        mapping[match.group("prefix")] = match.group("book").strip()
    return mapping


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _find_point_in_books(point: str, books: list[BookMap] | None) -> SourceLocator | None:
    """在地图里找到包含该知识点的书与章（精确优先，其次归一化包含）。"""
    if not books:
        return None
    wanted = _norm(point)
    contains: SourceLocator | None = None
    for book in books:
        for chapter in book.chapters:
            for raw in chapter.points:
                name = str(raw).strip()
                if not name:
                    continue
                if name == point:
                    return SourceLocator(point=name, book=book.book, chapter=chapter.chapter)
                if contains is None and wanted and (wanted in _norm(name) or _norm(name) in wanted):
                    contains = SourceLocator(point=name, book=book.book, chapter=chapter.chapter)
    return contains


def _chapter_range(distillate: str, chapter: str) -> tuple[int, int] | None:
    """从蒸馏稿里取某章标注的行号区间。

    章名匹配分两层（实测：地图书名是中文「第 1 章 认识 HTML」，蒸馏稿里是英文
    「第 1 章 · getting to know HTML」，直接比名字对不上）：

    1. 章名互相包含；
    2. 章名对不上时按**章号**匹配（取章号相同、且不是「x.y」小节的那一条）。
    """
    wanted = _norm(chapter)
    fallback: tuple[int, int] | None = None
    wanted_no = _chapter_number(chapter)

    for match in _CHAPTER_RANGE_RE.finditer(distillate):
        raw_name = match.group("name").strip()
        name = _norm(raw_name)
        span = (min(int(match.group("start")), int(match.group("end"))),
                max(int(match.group("start")), int(match.group("end"))))
        if wanted and (wanted in name or name in wanted):
            return span
        if fallback is None and wanted_no and _chapter_number(raw_name) == wanted_no:
            # 排除「8.1 结构：…（第 1 章，…）」这类小节：名字以数字点号开头
            if not _SUBSECTION_RE.match(raw_name):
                fallback = span
    return fallback


def _find_distillate(
    books_dir: Path,
    book_title: str,
    source_prefix: str | None = None,
) -> Path | None:
    """按书名（或显式 source 前缀）找到对应的蒸馏稿文件。

    `source_prefix` 优先：蒸馏稿 frontmatter 里写了 `source: <前缀>` 时最可靠。
    """
    if not books_dir.is_dir():
        return None
    files: list[tuple[Path, str, str]] = []
    for path in sorted(books_dir.glob("蒸馏-*.md")):
        text = read_text_or_none(path)
        if text is None:
            continue
        # 每个蒸馏稿只读一次：书名与 source 前缀都从同一段开头里取（以前同一个文件读两遍）
        head = text[:_HEAD_CHARS]
        match = _BOOK_FIELD_RE.search(head)
        files.append((path, match.group(1).strip() if match else path.stem, _source_prefix_in(head) or ""))

    if source_prefix:
        for path, _title, prefix in files:
            if prefix == source_prefix:
                return path

    wanted = _norm(book_title)
    if not wanted:
        return None
    for path, title, _prefix in files:
        if _norm(title) in wanted or wanted in _norm(title):
            return path
    return None


def read_source_lines(path: Path | str, start: int, end: int) -> str:
    """按 **1-based 行号**读原文片段（与 books/_src/README.md 的口径一致）。"""
    target = Path(path)
    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise ExplainError(f"读取原文失败：{target}（{type(exc).__name__}）") from None
    if not lines:
        return ""
    first = max(1, int(start))
    last = min(len(lines), int(end))
    if last < first:
        return ""
    return "\n".join(lines[first - 1:last])


def _truncate(text: str) -> str:
    stripped = (text or "").strip()
    if len(stripped) <= MAX_REFERENCE_CHARS:
        return stripped
    return stripped[:MAX_REFERENCE_CHARS].rstrip() + TRUNCATED_NOTE


DEFAULT_CACHE_DIRNAME = "explanations"


def default_cache_dir(profile_dir: Path | str) -> Path:
    """默认缓存目录：profile/explanations/（T-024 M-03）。"""
    return Path(profile_dir) / DEFAULT_CACHE_DIRNAME


def cache_path_for(cache_dir: Path | str, point: str) -> Path:
    """给一个知识点算缓存文件路径。

    名字里可能有 / : * ? 等字符（用户随手打的），所以只保留安全字符，
    过长或全被过滤掉时用名字的哈希兜底——**绝不能拼出危险路径**。
    """
    safe = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", str(point or "").strip()).strip("._")
    if not safe:
        safe = hashlib.sha1(str(point).encode("utf-8")).hexdigest()[:12]
    if len(safe) > 60:
        safe = safe[:40] + "-" + hashlib.sha1(str(point).encode("utf-8")).hexdigest()[:8]
    return Path(cache_dir) / f"{safe}.md"


def read_cached_explanation(cache_dir: Path | str, point: str) -> str | None:
    """读缓存；没有或读不出返回 None。"""
    raw = read_text_or_none(cache_path_for(cache_dir, point))
    if raw is None:
        return None
    # 缓存文件格式：--- ... --- 的 frontmatter + 正文
    text = raw.lstrip("\ufeff")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            body = text[end + 4:]
            return body.strip() or None
    return text.strip() or None


def save_explanation(cache_dir: Path | str, point: str, result: "ExplainResult") -> Path | None:
    """原子写缓存：frontmatter 记录出处，正文是讲解。失败返回 None。"""
    directory = Path(cache_dir)
    path = cache_path_for(directory, point)
    content = (
        "---\n"
        f"point: {point}\n"
        f"book: {result.book}\n"
        f"chapter: {result.chapter}\n"
        f"origin: {result.origin_kind}｜{result.origin_detail}\n"
        "---\n\n"
        f"{result.text.strip()}\n"
    )
    try:
        return write_text_atomic(path, content)
    except OSError:
        return None  # 缓存写不进去只是下次再调一次 LLM，不该让这次讲解失败


def _map_profile_name(name: str, profile, alignment_path) -> str | None:
    """T-023 L-03：把「画像里的知识点名」映射成「地图里的名字」。

    实况：用户会拿画像里的名字去问 explain，而地图里可能叫别的名字。
    对齐表（T-021）正好记着"地图名 → 画像概念"，这里反查回去。
    """
    if profile is None and not alignment_path:
        return None
    from .alignment import load_alignment

    # 1) 直接用对齐表反查：地图名叫 X、映射到画像概念 Y，问 Y 就答 X
    aligned: dict = {}
    if alignment_path:
        aligned = load_alignment(alignment_path)
    candidates = [
        point_name
        for point_name, entry in aligned.items()
        if entry.profile and entry.profile == name
    ]
    if candidates:
        return candidates[0]

    # 2) 画像里确实有这个知识点时，再从地图里找同名的（大小写/空白差异）
    if profile is not None:
        known = {p.name for p in profile.points}
        if name in known:
            return name
    return None


def find_explain_source(
    point: str,
    books: list[BookMap] | None,
    *,
    books_dir: Path | str = DEFAULT_BOOKS_DIR,
    src_dir: Path | str = DEFAULT_SRC_DIR,
    profile=None,
    alignment_path: Path | str | None = None,
) -> ExplainSource:
    """定位知识点并取参考文本。不在地图里 → ExplainError。

    T-023 L-03：允许用**画像里的知识点名**提问——先查画像名，再经对齐表映射到地图名。
    """
    name = str(point or "").strip()
    if not name:
        raise ExplainError("知识点名称不能为空")

    locator = _find_point_in_books(name, books)
    if locator is None:
        mapped = _map_profile_name(name, profile, alignment_path)
        if mapped:
            locator = _find_point_in_books(mapped, books)
    if locator is None:
        raise ExplainError(
            f"知识点「{name}」不在地图里：先用 import 导入对应书籍、跑 align 对齐，"
            f"再从地图里的知识点名里选一个（不瞎编）"
        )

    books_path = Path(books_dir)
    src_path = Path(src_dir)

    # 1) 优先原文：蒸馏稿里那一章标了 L####–#### 区间，直接截 _src 的 txt。
    #    前缀先按「书名覆盖率」猜；据此找到声明了该前缀的蒸馏稿（或退回按书名找）
    guessed = _match_prefix(locator.book, src_path)
    distillate = _find_distillate(books_path, locator.book, source_prefix=guessed)
    # 蒸馏稿全文只读一次：取行号区间、读 source 前缀、兜底取章节正文都用它
    text = (read_text_or_none(distillate) or "") if distillate is not None else ""
    if text:
        span = _chapter_range(text, locator.chapter)
        if span:
            # 显式声明的 source 前缀优先；没有才用书名猜出来的
            prefix = _source_prefix_in(text[:_HEAD_CHARS]) or guessed
            if prefix:
                txt = src_path / f"{prefix}.txt"
                if txt.is_file():
                    raw = read_source_lines(txt, span[0], span[1])
                    if raw.strip():
                        return ExplainSource(
                            point=locator.point,
                            book=locator.book,
                            chapter=locator.chapter,
                            text=_truncate(raw),
                            origin_kind="原文",
                            origin_detail=f"{txt.name} L{span[0]}–L{span[1]}",
                            locator=locator,
                        )

    # 2) 兜底：蒸馏稿里那一章的内容
    if distillate is not None and text:
        section = _section_of(text, locator.chapter)
        if section.strip():
            return ExplainSource(
                point=locator.point,
                book=locator.book,
                chapter=locator.chapter,
                text=_truncate(section),
                origin_kind="蒸馏稿",
                origin_detail=distillate.name,
                locator=locator,
            )

    raise ExplainError(
        f"找不到「{locator.point}」的参考文本：{locator.book} · {locator.chapter}"
        f"（既没有 _src 原文区间，蒸馏稿里也没这一章）"
    )


def _word_set(text: str) -> set[str]:
    """取可用于比对的词：英文按词、中文按单字+二元组（书名常有译名/版本差异）。"""
    tokens = {token.lower() for token in re.findall(r"[A-Za-z0-9]+", str(text or ""))}
    for chunk in re.findall(r"[\u4e00-\u9fff]+", str(text or "")):
        tokens.update(chunk)
        tokens.update(chunk[i:i + 2] for i in range(len(chunk) - 1))
    return tokens


def read_source_prefix(distillate_path: Path | str) -> str | None:
    """读蒸馏稿 frontmatter 里显式写的 source 前缀（形如 `source: python-crash-course`）。

    显式声明比按书名猜可靠得多——实测译名差异会让覆盖率从 0.11 到 0.78 都有。
    """
    text = read_text_or_none(distillate_path)
    return _source_prefix_in(text[:_HEAD_CHARS]) if text else None


def _source_prefix_in(head: str) -> str | None:
    match = _SOURCE_FIELD_RE.search(head)
    return match.group(1) if match else None


def match_source_prefix(book_title: str, mapping: dict[str, str]) -> str | None:
    """把书名对到 _src 前缀（按「对照表书名被地图书名覆盖的比例」评分）。"""
    wanted = _word_set(book_title)
    if not wanted:
        return None
    best: tuple[float, str] | None = None
    for prefix, title in mapping.items():
        candidate = _word_set(title)
        if not candidate:
            continue
        covered = len(candidate & wanted) / len(candidate)
        if covered < 0.25:          # 完全不相关的书名直接排除
            continue
        if best is None or covered > best[0]:
            best = (covered, prefix)
    return best[1] if best else None


def _match_prefix(book_title: str, src_dir: Path) -> str | None:
    """把地图里的书名对到 _src 前缀。

    实测：地图书名是「Head First HTML and CSS（第 2 版）」，对照表是
    「Head First HTML and CSS, 2nd Edition」——子串匹配不成立。
    改用**词集合包含**（短的一侧完全被长的一侧覆盖即算命中），并取覆盖度最高的。
    """
    mapping = load_source_map(src_dir / "README.md")
    if not mapping:
        return None
    return match_source_prefix(book_title, mapping)


def _distillate_section(distillate_path: Path, chapter: str) -> str:
    """取蒸馏稿里某一章的正文（到下一个同级或更高级标题为止）。

    章名匹配与 _chapter_range 一致：先比名字，对不上再按章号兜底。
    """
    return _section_of(read_text_or_none(distillate_path) or "", chapter)


def _section_of(text: str, chapter: str) -> str:
    """在已读入的蒸馏稿全文里取某一章的正文（_distillate_section 的纯文本版）。"""
    if not text:
        return ""

    wanted = _norm(chapter)
    wanted_no = _chapter_number(chapter)
    lines = text.splitlines()
    marks = [index for index, line in enumerate(lines) if line.startswith("#")]

    chosen: int | None = None
    for index in marks:
        raw_name = lines[index].lstrip("#").strip()
        name = _norm(raw_name)
        if wanted and (wanted in name or name in wanted):
            chosen = index
            break
        if (
            chosen is None
            and wanted_no
            and _chapter_number(raw_name) == wanted_no
            and not _SUBSECTION_RE.match(raw_name)
        ):
            chosen = index
    if chosen is None:
        return ""

    level = len(lines[chosen]) - len(lines[chosen].lstrip("#"))
    end = len(lines)
    for later in marks:
        if later <= chosen:
            continue
        later_level = len(lines[later]) - len(lines[later].lstrip("#"))
        if later_level <= level:
            end = later
            break
    return "\n".join(lines[chosen:end]).strip()


SYSTEM_PROMPT = """你是耐心的高校助教，负责给一名大一计算机方向的学生讲解**一个**知识点。

要求：
1. 只讲这一个知识点；可以引用参考文本里的说法，但**不要大段抄原文**。
2. 结构：先用一两句话讲清「它是什么、为什么需要它」，再给一个最小可运行的小例子，
   最后点出初学者最容易踩的 1~2 个坑。
3. 面向刚入门的人：术语出现时要顺手解释。
4. 用中文，Markdown 作答，篇幅控制在 400~700 字。
5. 如果参考文本不足以讲清，就直接说明「材料里没讲到的部分」，**不要编造**。
"""


def build_explain_messages(point: str, source: ExplainSource) -> list[dict[str, str]]:
    header = (
        f"知识点：{point}\n"
        f"出处：{source.book} · {source.chapter}（参考 {source.origin_kind}：{source.origin_detail}）\n"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": header + "\n参考文本：\n\n" + source.text},
    ]


def explain_point(
    point: str,
    books: list[BookMap] | None,
    *,
    completer,
    books_dir: Path | str = DEFAULT_BOOKS_DIR,
    src_dir: Path | str = DEFAULT_SRC_DIR,
    profile=None,
    alignment_path: Path | str | None = None,
    cache_dir: Path | str | None = None,
    refresh: bool = False,
) -> ExplainResult:
    """取参考文本并让 LLM 生成讲解。

    T-024 M-03：`cache_dir` 给了就启用缓存——同名知识点第二次**零 LLM 调用**；
    `refresh=True` 强制重新生成并覆盖缓存。

    缓存按**地图里的点名**（source.point）存取：用户可能用画像名 / 缩略名提问，
    以前读缓存用用户输入、写缓存用地图名，两者不同时缓存永远命中不了。
    """
    source = find_explain_source(
        point,
        books,
        books_dir=books_dir,
        src_dir=src_dir,
        profile=profile,
        alignment_path=alignment_path,
    )
    if cache_dir and not refresh:
        cached = read_cached_explanation(cache_dir, source.point)
        if cached:
            return ExplainResult(
                text=cached,
                book=source.book,
                chapter=source.chapter,
                origin_kind=source.origin_kind,
                origin_detail=source.origin_detail,
                from_cache=True,
            )

    try:
        text = completer.complete(build_explain_messages(source.point, source))
    except LLMError as exc:
        raise ExplainError(f"LLM 调用失败：{exc}") from None
    except Exception as exc:
        raise ExplainError(f"LLM 调用失败：{type(exc).__name__}") from None
    if not str(text or "").strip():
        raise ExplainError("LLM 返回了空讲解，请重试")
    result = ExplainResult(
        text=str(text).strip(),
        book=source.book,
        chapter=source.chapter,
        origin_kind=source.origin_kind,
        origin_detail=source.origin_detail,
    )
    if cache_dir:
        save_explanation(cache_dir, source.point, result)
    return result
