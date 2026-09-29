"""T-021：知识点命名对齐（地图点名 ↔ 画像点名）。

问题（T-010 实测）：

- 地图用书里的细粒度名字（「h1 到 h6 六级标题」），画像用提炼出的概括名（「标题与文本格式化标签」）；
- 两者**精确同名交集 0** → A-06 的「与画像最相关的书」全 0 命中 → 退回第一本 → 提议 main 函数；
- 纯文本匹配只覆盖约 2%，且多为误报（「HTML 简史」会匹配到「HTML 标签基础」）。

做法：用 LLM 把每个地图点对齐到画像的**既有概念**；对不上的标成 new（画像里还没有的概念）。
结果落盘到 profile/alignment.json，供 planner 选书/选点使用。

边界：

- LLM 给出的概念名若不在画像里 → **丢弃并标成 new**（不接受编造）；
- 对齐是"看法"不是"事实"：只存映射，不改画像、不改原始 syllabus。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re

from .syllabus import BookMap, Chapter

from .llm import LLMError

DEFAULT_ALIGNMENT_NAME = "alignment.json"
DEFAULT_BATCH_SIZE = 150

_LATIN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#./_-]*")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_PAREN_RE = re.compile(r"（[^（）]*）\s*$")
_JSON_DECODER = json.JSONDecoder()


class AlignmentError(RuntimeError):
    """对齐失败：LLM 不可用或输出无法解析。"""


@dataclass(frozen=True)
class Alignment:
    point: str
    profile: str | None
    confidence: str = "low"

    @property
    def is_new(self) -> bool:
        return not self.profile

    def as_dict(self) -> dict:
        return {"point": self.point, "profile": self.profile, "confidence": self.confidence}


def normalize_text(name: str) -> str:
    """轻量归一化：去首尾空白、去结尾主题括号、转小写。只用于预筛与比较。"""
    text = str(name or "").strip()
    text = _PAREN_RE.sub("", text).strip()
    return text.lower()


def token_set(name: str) -> set[str]:
    """拆出可比较的 token，用于零成本预筛（不做最终判定）。

    - Latin：按词切（img / src / python）；
    - 中文：切**单字与二元组**（「标签与」→ 标签/签与），比整段更有区分度，
      这样「标签基础」与「标签与」能共享「标签」。
    """
    text = str(name or "")
    tokens = {token.lower() for token in _LATIN_RE.findall(text)}
    for chunk in _CJK_RE.findall(text):
        tokens.update(chunk)
        tokens.update(chunk[i:i + 2] for i in range(len(chunk) - 1))
    return tokens


SYSTEM_PROMPT = """你是学习资料整理助手，负责把「书里的细粒度知识点名」对齐到「学生画像里的概念」。

规则：
1. 对每个待对齐的点，从「画像已有概念」里选出**语义最接近**的一个；选不出来就填 null。
2. **不许编造概念名**：只能从给定列表里选，一个字都不能改。
3. 细粒度点比画像概念更细时，选它所属的那个上位概念
   （例：「h1 到 h6 六级标题」→「标题与文本格式化标签」）。
4. 主题词相同但内容不同时不要硬凑（例：「HTML 简史」与「HTML 标签基础」不是一回事，填 null）。
5. 只输出 JSON 数组，不要输出其它文字。每个元素形如：
   {"point": "待对齐的点名", "profile": "选中的概念名或 null", "confidence": "high|medium|low"}
"""


def _build_messages(profile_names: list[str], batch: list[str]) -> list[dict[str, str]]:
    concepts = "\n".join(f"- {name}" for name in profile_names)
    items = "\n".join(f"- {name}" for name in batch)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"待对齐的点（共 {len(batch)} 个）：\n{items}\n\n画像已有概念（只能从这里选）：\n{concepts}",
        },
    ]


def _extract_json(raw: str):
    text = (raw or "").strip()
    if not text:
        raise AlignmentError("对齐失败：LLM 返回了空内容")
    starts = [index for index in (text.find("["), text.find("{")) if index >= 0]
    if not starts:
        raise AlignmentError("对齐失败：LLM 输出里找不到 JSON")
    last_error: Exception | None = None
    for start in sorted(starts):
        try:
            value, _ = _JSON_DECODER.raw_decode(text[start:])
            return value
        except ValueError as exc:
            last_error = exc
    raise AlignmentError(f"对齐失败：LLM 输出的 JSON 无法解析（{last_error}）")


def align_points(
    points: list[str],
    profile: KnowledgeProfile,
    *,
    completer,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, Alignment]:
    """把细粒度点批量对齐到画像概念。返回 {点名: Alignment}。

    LLM 给出的概念名必须**精确存在于画像**，否则丢弃并标成 new。
    """
    from .profile import KnowledgeProfile as _Profile  # 仅用于类型提示，运行时无副作用

    names = [str(p) for p in points if str(p).strip()]
    if not names:
        return {}

    profile_names = [point.name for point in profile.points]
    allowed = set(profile_names)
    size = max(1, int(batch_size))
    result: dict[str, Alignment] = {}

    for start in range(0, len(names), size):
        batch = names[start:start + size]
        try:
            raw = completer.complete(_build_messages(profile_names, batch))
        except LLMError as exc:
            raise AlignmentError(f"对齐失败：LLM 调用失败（{exc}）") from None
        except Exception as exc:
            raise AlignmentError(f"对齐失败：LLM 调用失败（{type(exc).__name__}）") from None

        payload = _extract_json(raw)
        if isinstance(payload, dict):
            payload = payload.get("alignments") or payload.get("items") or []
        if not isinstance(payload, list):
            raise AlignmentError("对齐失败：LLM 输出的不是数组")

        seen: set[str] = set()
        for item in payload:
            if not isinstance(item, dict):
                continue
            point = str(item.get("point") or item.get("name") or "").strip()
            if not point:
                continue
            target = item.get("profile") or item.get("concept") or item.get("profile_name")
            target = str(target).strip() if target else ""
            if target and target not in allowed:
                # 编造的概念名：丢弃，标成 new
                target = ""
            confidence = str(item.get("confidence") or "").strip().lower() or ("high" if target else "low")
            result[point] = Alignment(point=point, profile=target or None, confidence=confidence)
            seen.add(point)

        # LLM 漏报的点按 new 处理（宁可保守，也不猜）
        for point in batch:
            if point not in seen:
                result[point] = Alignment(point=point, profile=None, confidence="low")

    return result


def map_point_names(aligned: dict[str, Alignment]) -> dict[str, str | None]:
    """把 {点名: Alignment} 压成 {点名: 画像概念或 None}。"""
    return {name: entry.profile for name, entry in aligned.items()}


def save_alignment(path: Path | str, aligned: dict[str, Alignment]) -> Path:
    """原子落盘（临时文件 + 替换）。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "mapped": sum(1 for entry in aligned.values() if not entry.is_new),
        "total": len(aligned),
        "alignments": [entry.as_dict() for entry in aligned.values()],
    }
    tmp = target.with_name(target.name + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise AlignmentError(f"写入对齐结果失败：{target}（{type(exc).__name__}）") from None
    return target


def load_alignment(path: Path | str) -> dict[str, Alignment]:
    """读取对齐结果；文件不存在或损坏都返回空表（不拖垮出题）。"""
    target = Path(path)
    if not target.is_file():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    items = payload.get("alignments") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return {}
    result: dict[str, Alignment] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        point = str(item.get("point") or "").strip()
        if not point:
            continue
        target_name = item.get("profile")
        result[point] = Alignment(
            point=point,
            profile=str(target_name).strip() if target_name else None,
            confidence=str(item.get("confidence") or "low").strip().lower() or "low",
        )
    return result


# 只有这个置信度的对齐才当作"命中"。T-021 实测：high 350 条全部正确；
# medium/low 共 2818 条里大量是硬凑（「浏览器与服务器的工作原理」→「计算机网络」、
# 「API 概念」「速率限制」→「计算机网络」）。宁可少映射，也不要把错的说成对的。
TRUSTED_CONFIDENCE = ("high",)


def apply_alignment(
    books: list[BookMap],
    aligned: dict[str, Alignment],
    *,
    trusted_only: bool = True,
) -> list[BookMap]:
    """把地图点换成画像概念（新的点原样保留）；章内去重保序。

    默认只采用**高置信度**对齐（见 TRUSTED_CONFIDENCE），其余按新概念处理。
    原始 syllabus.md 不动 —— 地图仍然是你翻书的目录，对齐只是给 planner 看的"看法"。
    """
    mapped_books: list[BookMap] = []
    for book_map in books:
        chapters: list[Chapter] = []
        for chapter in book_map.chapters:
            points: list[str] = []
            for raw in chapter.points:
                name = str(raw).strip()
                if not name:
                    continue
                entry = aligned.get(name)
                usable = bool(entry and entry.profile)
                if usable and trusted_only and entry.confidence not in TRUSTED_CONFIDENCE:
                    usable = False
                final = entry.profile if usable else name
                if final not in points:
                    points.append(final)
            chapters.append(Chapter(chapter=chapter.chapter, points=points))
        mapped_books.append(BookMap(book=book_map.book, chapters=chapters))
    return mapped_books


def summary(aligned: dict[str, Alignment]) -> dict:
    """给报告用的统计：总点数、已对齐数、新增概念数、每本书的高置信度占比。"""
    total = len(aligned)
    mapped = sum(1 for entry in aligned.values() if not entry.is_new)
    trusted = sum(
        1 for entry in aligned.values()
        if entry.profile and entry.confidence in TRUSTED_CONFIDENCE
    )
    return {
        "total": total,
        "mapped": mapped,
        "trusted": trusted,
        "new": total - mapped,
        "ratio": round(mapped / total, 3) if total else 0.0,
    }
