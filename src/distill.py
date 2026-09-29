"""T-003：LLM 连通与「笔记 → 知识点」提炼 prompt 雏形。

边界（见 [[模块-知识画像]]）：

- 只产出「名称 + 状态 + 证据」的结构化知识点，不生成任务、不改画像文件。
- 画像文件的合并与落盘属于 T-004；本任务只把结构化结果打出来。
- LLM 的猜测不得当作已掌握事实：拿不准一律「存疑」，prompt 里明确禁止臆断。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable, Sequence

from .llm import LLMError

# 三态与 [[模块-知识画像]] 一致
DISTILL_LEVELS = ("学过", "做过", "存疑")

SAMPLE_NOTE = """# Python 基础笔记

## 列表
列表用方括号定义，可以存放任意类型，支持 append 与切片。

## 字典
字典用花括号定义，是键值对结构，可以用键直接取值。

## 循环
for 循环可以遍历列表和字典，while 循环靠条件控制。
"""

SYSTEM_PROMPT = """你是学习助理，负责从学生的飞书笔记中提炼「编程知识点」，供后续知识画像使用。

要求：
1. 只提炼与编程相关的知识点；数学、英语等非编程内容忽略。
2. 输出一个 JSON 数组，每个元素包含：
   - "name"：知识点名称（简短，如「列表」「字典推导式」）
   - "level"：只能是 "学过"、"做过"、"存疑" 三者之一
   - "evidence"：证据，写清来自笔记的哪一处（可引用笔记中的小节标题或原句）
   - "topic"：可选，归属主题（如「Python 基础」）
3. level 判定标准：
   - 「做过」= 笔记里能看出动手写过代码、有产出；
   - 「学过」= 笔记里有清晰的解释/示例，但看不出动手；
   - 「存疑」= 只提了一句、理解不完整，或你不确定学生是否真的掌握。
4. 不得臆断学生已掌握：信息不足、只是抄录、或你拿不准的，一律用「存疑」。
5. 不要输出 JSON 以外的任何文字；没有可提炼的编程知识点时输出空数组 []。
"""


class DistillError(RuntimeError):
    """提炼失败：LLM 调用失败、输出不可解析或字段不合法。画像不变。"""


@dataclass(frozen=True)
class KnowledgePoint:
    name: str
    level: str
    evidence: str
    topic: str = ""
    # T-035：最近一次"被碰到"的日期（YYYY-MM-DD）。
    # distill 学到它、done 做掉它、review 点评到它，都算碰到；
    # 复习题就是靠这个字段挑"学过但很久没碰"的点。
    last_touched: str = ""

    def as_dict(self) -> dict[str, str]:
        payload = {"name": self.name, "level": self.level, "evidence": self.evidence}
        if self.topic:
            payload["topic"] = self.topic
        return payload


def build_distill_messages(note_text: str, existing_names: Sequence[str] | None = None) -> list[dict[str, str]]:
    """构造提炼用的 messages：system 放规则，user 放笔记正文与已有画像名单。"""
    parts = ["以下是学生的笔记正文（markdown）：", "", note_text.strip() or "（空笔记）"]
    if existing_names:
        parts += [
            "",
            "这些知识点已经在画像里了，如果笔记里再次出现，请沿用完全相同的名称：",
            "、".join(existing_names),
        ]
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(parts)},
    ]


def parse_knowledge_points(raw: str, source: str = "", note_text: str = "") -> list[KnowledgePoint]:
    """把 LLM 回复解析成知识点列表；任何不合约定都抛 DistillError。"""
    payload = _extract_json(raw)
    if isinstance(payload, dict):
        for key in ("points", "knowledge_points", "knowledgePoints", "items"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            raise DistillError("LLM 输出的 JSON 对象里没有知识点数组（期望 points 字段）")
    if not isinstance(payload, list):
        raise DistillError("LLM 输出不是知识点数组")

    points: list[KnowledgePoint] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise DistillError(f"第 {index} 个知识点不是 JSON 对象")
        name = str(item.get("name") or "").strip()
        if not name:
            raise DistillError(f"第 {index} 个知识点缺少必填字段 name")

        level = str(item.get("level") or "").strip()
        if level not in DISTILL_LEVELS:
            raise DistillError(
                f"知识点「{name}」的 level 不合法：{level or '（空）'}；只能是 {'/'.join(DISTILL_LEVELS)}"
            )

        evidence = str(item.get("evidence") or "").strip()
        if not evidence or _is_heading_only(evidence):
            if not source:
                raise DistillError(f"知识点「{name}」缺少必填字段 evidence")
            # 证据不足时回笔记取该小节正文：比标题更有信息量，也不放任空证据入库。
            # 注意 source 是文件路径（用于落档），正文要单独传 note_text。
            evidence = _evidence_from_note(note_text, name) if note_text else ""

        points.append(
            KnowledgePoint(
                name=name,
                level=level,
                evidence=evidence,
                topic=str(item.get("topic") or "").strip(),
            )
        )
    return points


def _extract_json(raw: str):
    text = (raw or "").strip()
    if not text:
        raise DistillError("LLM 返回了空内容，无法解析知识点")

    fenced = re.search("```(?:json)?\\s*(.+?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    if text.startswith("[") or text.startswith("{"):
        candidate = text
    else:
        start = min(
            (index for index in (text.find("["), text.find("{")) if index >= 0),
            default=-1,
        )
        if start < 0:
            raise DistillError("LLM 输出里找不到 JSON（prompt 要求只输出 JSON 数组），请重试")
        candidate = text[start:]
    try:
        return json.loads(candidate)
    except ValueError as exc:
        raise DistillError(f"LLM 输出的 JSON 无法解析：{exc}；请重试") from None


def _is_heading_only(evidence: str) -> bool:
    """证据只是个标题（含 markdown 标记或没有说明性文字）时视为不足。"""
    stripped = evidence.strip()
    if stripped.startswith("#"):
        return True
    return len(stripped.lstrip("#").strip()) <= 6 and stripped.rstrip("：:").strip() in {"标题", "小节", "见笔记"}


def _evidence_from_note(note_text: str, name: str, limit: int = 120) -> str:
    """LLM 没给证据时，回笔记里找同名小节，取该小节正文当证据（找不到则只用知识点名）。"""
    lines = note_text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip().lstrip("#").strip().lstrip("0123456789. ").strip()
        if stripped != name:
            continue
        body: list[str] = []
        for follow in lines[index + 1:]:
            if follow.strip().startswith("#"):
                break
            if follow.strip():
                body.append(follow.strip())
            elif body:
                break
        if body:
            snippet = " ".join(body)
            return snippet if len(snippet) <= limit else snippet[:limit] + "..."
        return name
    return name


def distill_note(
    note_text: str,
    *,
    completer,
    source: str = "",
    existing_names: Sequence[str] | None = None,
) -> list[KnowledgePoint]:
    """调用 LLM 提炼一篇笔记，返回结构化知识点列表。失败抛 DistillError（调用方保持画像不变）。"""
    messages = build_distill_messages(note_text, existing_names=existing_names)
    try:
        raw = completer.complete(messages)
    except DistillError:
        raise  # 已经是可读的提炼失败原因，别再包一层
    except LLMError as exc:
        raise DistillError(f"LLM 调用失败：{exc}") from None
    except Exception as exc:  # 兜底：只报异常类型，避免把请求体/Key 带出来
        raise DistillError(f"LLM 调用失败：{type(exc).__name__}") from None
    return parse_knowledge_points(raw, source=source, note_text=note_text)


def format_points(points: Iterable[KnowledgePoint]) -> str:
    """人读格式：每条一行，含名称、状态与证据。"""
    lines = []
    for point in points:
        topic = f"（{point.topic}）" if point.topic else ""
        lines.append(f"[{point.level}] {point.name}{topic} — 证据：{point.evidence}")
    return "\n".join(lines)


# --- T-016：批量提炼（--all / 看板全量） --------------------------------------


@dataclass
class DistillBatch:
    """一次批量提炼的结果汇总。succeeded 里带该篇产出的知识点，便于调用方合并。"""

    succeeded: list[tuple[Path, list["KnowledgePoint"]]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    note_count: int = 0
    skipped: int = 0

    @property
    def total_points(self) -> int:
        return sum(len(points) for _path, points in self.succeeded)

    @property
    def ok(self) -> bool:
        return not self.failed

    def render(self) -> str:
        """人读汇总：逐篇汇报成败，并说明跳过了多少篇（T-017 I-1/I-2）。"""
        lines = [
            f"批量提炼：共 {self.note_count} 篇，成功 {len(self.succeeded)} 篇，"
            f"跳过 {self.skipped} 篇（内容未变），失败 {len(self.failed)} 篇"
        ]
        for path, points in self.succeeded:
            lines.append(f"  [成功] {path.name}：{len(points)} 个知识点")
        for name, reason in self.failed:
            lines.append(f"  [失败] {name}：{reason}")
        if self.note_count == 0:
            lines.append("  （notes/ 里没有非空笔记）")
        elif self.total_points:
            lines.append(f"合计 {self.total_points} 个知识点")
        return "\n".join(lines)


def file_fingerprint(path: Path | str) -> str:
    """笔记内容指纹（sha256）。用内容而不是 mtime：避免"只 touch 没改内容"也重跑。"""
    target = Path(path)
    try:
        data = target.read_bytes()
    except OSError:
        return ""
    return hashlib.sha256(data).hexdigest()


def load_distill_state(path: Path | str) -> dict:
    """读取提炼状态：{"文件名": {"hash": ..., "size": ...}}；损坏或不存在都返回空表。"""
    target = Path(path)
    if not target.is_file():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(k): v for k, v in payload.items() if isinstance(v, dict)}


def save_distill_state(path: Path | str, state: dict) -> Path:
    """原子写状态文件（临时文件 + 替换），失败不影响主流程。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    try:
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(target)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    return target


def discover_notes(notes_dir: Path | str) -> list[Path]:
    """列出可提炼的笔记：notes/ 下的 .md，跳过空文件，按文件名排序（结果稳定可复现）。"""
    directory = Path(notes_dir)
    if not directory.is_dir():
        return []
    found: list[Path] = []
    for path in sorted(directory.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if text.strip():
            found.append(path)
    return found


def distill_notes(
    notes_dir: Path | str,
    *,
    completer,
    state: dict | None = None,
    force: bool = False,
    on_progress=None,
) -> DistillBatch:
    """逐篇提炼 notes/ 下的全部非空笔记。

    - 单篇失败（LLM 报错或输出不可解析）只记进 failed，不阻塞其余篇目；
    - state 传入时启用增量：内容指纹与上次相同则跳过（force=True 可强制重跑）；
    - on_progress(index, total, 文件名, 状态) 用于逐篇进度提示（T-017 I-1）。

    只有**成功**的篇目才写入 state，失败篇目下次会自动重试。
    """
    notes = discover_notes(notes_dir)
    batch = DistillBatch(note_count=len(notes))
    total = len(notes)
    known = state if state is not None else {}

    for position, path in enumerate(notes, start=1):
        fingerprint = file_fingerprint(path)
        previous = known.get(path.name)
        unchanged = (
            not force
            and isinstance(previous, dict)
            and previous.get("hash") == fingerprint
            and fingerprint != ""
        )
        if unchanged:
            batch.skipped += 1
            if on_progress:
                on_progress(position, total, path.name, "跳过（内容未变）")
            continue

        if on_progress:
            on_progress(position, total, path.name, "提炼中")

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            batch.failed.append((path.name, f"读取失败（{type(exc).__name__}）"))
            if on_progress:
                on_progress(position, total, path.name, "读取失败")
            continue
        try:
            points = distill_note(text, completer=completer, source=str(path))
        except DistillError as exc:
            batch.failed.append((path.name, str(exc)))
            if on_progress:
                on_progress(position, total, path.name, "失败")
            continue
        except Exception as exc:  # 兜底：任何单篇异常都不该中断整批
            batch.failed.append((path.name, f"未预期错误：{type(exc).__name__}"))
            if on_progress:
                on_progress(position, total, path.name, "失败")
            continue

        batch.succeeded.append((path, points))
        known[path.name] = {"hash": fingerprint, "size": path.stat().st_size if path.exists() else 0}
        if on_progress:
            on_progress(position, total, path.name, f"成功（{len(points)} 个知识点）")

    return batch
