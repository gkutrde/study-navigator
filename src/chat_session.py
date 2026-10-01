"""T-034 看板聊天面板的会话层：历史隔离、留档、prompt 组装与裁剪。

每个任务一个会话：历史存 profile/handoff/<id>.chat.md（人可读的留档），
prompt 每轮都重新拼：handoff 全文 + 历史 + 新消息。

历史超长时：**handoff 全文必须保留**，只能从最旧的轮次开始裁，并注明裁了多少轮。
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import time

from .handoff import handoff_dir, task_file_id


class ChatSessionError(Exception):
    """会话层失败（时间戳非法、角色非法、消息为空等）。"""


# 与 T-032 保持同一个上限，避免两处口径漂移
MAX_PROMPT_CHARS = 30000
# 留给历史的下限：再挤也要保证最近几轮进得去
MIN_HISTORY_BUDGET = 2000

ROLES = ("user", "assistant")
USER_LABEL = "你"
ASSISTANT_LABEL = "DSH 助教"


# T-043：历史摘要块的上限（超长时把最旧轮次压成这么长）
SUMMARY_BUDGET = 500
# 留档/缓存里摘要块的标题（解析时要能跳过，不能当成一轮对话）
SUMMARY_LABEL = "较早对话摘要"
_SUMMARY_RE = re.compile(r"^\*\*" + SUMMARY_LABEL + r"\*\*\s*$", re.M)
_SUMMARY_META_RE = re.compile(r"覆盖到第\s*(?P<upto>\d+)\s*轮")
# 进程内缓存：同一批旧轮次不重复压（落盘缓存之外的加速层）
_SUMMARY_MEMO: dict = {}


@dataclass(frozen=True)
class HistorySummary:
    """一段被压缩过的早期对话。"""

    text: str
    # 覆盖到第几轮（含），便于判断缓存是否还有效
    upto: int = 0


# T-037：留档里"思考过程"小节的标题
THINKING_LABEL = "思考过程"
_THINKING_RE = re.compile(r"^\*\*" + THINKING_LABEL + r"\*\*\s*$", re.M)


@dataclass(frozen=True)
class ChatTurn:
    role: str
    text: str
    at: str = ""
    # T-037：stderr 推理流（可空）。留档里存成独立的「思考过程」小节。
    thinking: str = ""


def archive_path(profile_dir: Path | str, when: str) -> Path:
    """某个任务的对话留档路径：profile/handoff/<id>.chat.md。"""
    stamp = str(when or "").strip()
    if not stamp:
        raise ChatSessionError("聊天需要任务时间戳")
    return handoff_dir(profile_dir) / (task_file_id(stamp) + ".chat.md")


def _normalize(role: str) -> str:
    text = str(role or "").strip().lower()
    if text not in ROLES:
        raise ChatSessionError("角色只能是 user 或 assistant，收到：" + repr(role))
    return text


# 留档里用作分隔的二级标题（正文里出现同形态的标题必须被改写，否则读回来会多切出轮次）
_HEADING_TEXT_RE = re.compile(r"^(#{1,6})(\s*)", re.M)


def render_archive(when: str, turns) -> str:
    """把整段对话渲染成 markdown 留档。

    **正文里的 markdown 标题要降级**：实测 dsh 的回答里就有 "## xxx" 这类小标题，
    如果不改写，读回时会被当成新一轮的分隔符——真机上表现为「3 轮对话读回来 9 轮」。
    这里把正文里的行首 # 前面加一个零宽空格，人看着一样，但不会再被解析成分隔符。
    """
    lines = ["# 对话留档 · " + str(when), ""]
    for turn in turns:
        who = USER_LABEL if turn.role == "user" else ASSISTANT_LABEL
        stamp = ("（" + turn.at + "）") if getattr(turn, "at", "") else ""
        body = _HEADING_TEXT_RE.sub(lambda m: "\u200b" + m.group(1) + m.group(2), str(turn.text).strip())
        lines.append("## " + who + stamp)
        lines.append("")
        lines.append(body)
        lines.append("")
        # T-037：思考过程放进独立小节（同样做标题降级，防止切轮次）
        thought = str(getattr(turn, "thinking", "") or "").strip()
        if thought:
            guarded = _HEADING_TEXT_RE.sub(
                lambda m: "\u200b" + m.group(1) + m.group(2), thought
            )
            lines.append("**" + THINKING_LABEL + "**")
            lines.append("")
            lines.append(guarded)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def save_archive(profile_dir: Path | str, when: str, turns) -> Path:
    """原子写留档（tmp + replace），失败抛 ChatSessionError。"""
    target = archive_path(profile_dir, when)
    tmp = target.with_name(target.name + ".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # T-043：追加轮次时要把**已有摘要块**带上，否则摘要会被这次重写冲掉
        existing = None
        if target.is_file():
            try:
                existing = load_summary(profile_dir, when)
            except Exception:
                existing = None
        body = render_archive(when, turns)
        if existing is not None:
            block = "**" + SUMMARY_LABEL + "**" + chr(10) + chr(10) + existing.text
            if existing.upto:
                block += chr(10) + chr(10) + "（覆盖到第 " + str(existing.upto) + " 轮）"
            first = body.find("## ")
            body = (body[:first] + block + chr(10) + chr(10) + body[first:]) if first > 0 else (body + chr(10) + block)
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, target)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise ChatSessionError("写对话留档失败：" + type(exc).__name__) from None
    return target


_HEADING_RE = re.compile(r"^##\s+(?P<who>.+?)(?:（(?P<at>[^）]*)）)?\s*$", re.M)


def _strip_guard(text: str) -> str:
    """把渲染时加的零宽前缀去掉。

    T-035 为了防止回答里的标题冒充分隔符，给正文行首的 # 前面加了 U+200B。
    那个字符**只**是留档层面的防护，读回来必须剥掉——否则 T-037 的 markdown
    渲染会把 "\u200b## 标题" 当成普通段落（实测踩过）。
    """
    return text.replace("\u200b", "")


def _decode_archive(text: str) -> list:
    """把留档读回成 turns。容忍手工编辑：认不出的小节按 assistant 处理。"""
    # T-043：摘要块不是一轮对话，先摘掉（否则会多切出一轮）
    marker = _SUMMARY_RE.search(text)
    if marker:
        head = text[: marker.start()]
        rest = text[marker.end():]
        # 摘要块一直延伸到下一个轮次标题（## ...）之前
        nxt = re.search(r"^## ", rest, re.M)
        tail = rest[nxt.start():] if nxt else ""
        text = head + tail

    turns: list = []
    marks = list(_HEADING_RE.finditer(text))
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        body = text[mark.end():end].strip()
        if not body:
            continue
        who = mark.group("who").strip()
        role = "user" if who == USER_LABEL else "assistant"
        thinking = ""
        marker = _THINKING_RE.search(body)
        if marker:
            thinking = _strip_guard(body[marker.end():].strip())
            body = body[: marker.start()].strip()
        turns.append(
            ChatTurn(
                role=role,
                text=_strip_guard(body),
                at=(mark.group("at") or ""),
                thinking=thinking,
            )
        )
    return turns


def load_turns(profile_dir: Path | str, when: str) -> list:
    """读某个任务的历史；没有留档就返回空列表。"""
    target = archive_path(profile_dir, when)
    if not target.is_file():
        return []
    try:
        return _decode_archive(target.read_text(encoding="utf-8", errors="replace"))
    except OSError as exc:
        raise ChatSessionError("读对话留档失败：" + type(exc).__name__) from None


def append_turn(
    profile_dir: Path | str,
    when: str,
    *,
    role: str,
    text: str,
    thinking: str = "",
    at: str | None = None,
) -> list:
    """追加一轮并落盘，返回追加后的完整历史。"""
    kind = _normalize(role)
    body = str(text or "").strip()
    if not body:
        raise ChatSessionError("消息不能为空")
    moment = at or time.strftime("%Y-%m-%d %H:%M")
    turns = load_turns(profile_dir, when)
    turns.append(
        ChatTurn(role=kind, text=body, at=moment, thinking=str(thinking or "").strip())
    )
    save_archive(profile_dir, when, turns)
    return turns


def save_summary(profile_dir: Path | str, when: str, text: str, upto: int) -> HistorySummary:
    """把摘要写进留档（独立块，人可读）。"""
    summary = HistorySummary(text=str(text or "").strip()[: SUMMARY_BUDGET * 4], upto=int(upto or 0))
    turns = load_turns(profile_dir, when)
    _write_archive_with_summary(profile_dir, when, turns, summary)
    _SUMMARY_MEMO[(str(profile_dir), str(when))] = summary
    return summary


def load_summary(profile_dir: Path | str, when: str) -> HistorySummary | None:
    """从留档里读摘要块；没有就 None。"""
    target = archive_path(profile_dir, when)
    if not target.is_file():
        return None
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    marker = _SUMMARY_RE.search(text)
    if not marker:
        return None
    tail = text[marker.end():]
    block = tail.split("## ", 1)[0].strip()
    if not block:
        return None
    upto_match = _SUMMARY_META_RE.search(block)
    body = _SUMMARY_META_RE.sub("", block).strip()
    return HistorySummary(text=_strip_guard(body), upto=int(upto_match.group("upto")) if upto_match else 0)


def _write_archive_with_summary(profile_dir: Path | str, when: str, turns, summary) -> None:
    """写留档：摘要块放在最前面（在轮次之前），轮次照旧。"""
    target = archive_path(profile_dir, when)
    tmp = target.with_name(target.name + ".tmp")
    body = render_archive(when, turns)
    block = "**" + SUMMARY_LABEL + "**" + chr(10) + chr(10) + summary.text
    if summary.upto:
        block += chr(10) + chr(10) + "（覆盖到第 " + str(summary.upto) + " 轮）"
    # 插在第一个轮次标题之前
    first = body.find("## ")
    merged = (body[:first] + block + chr(10) + chr(10) + body[first:]) if first > 0 else (body + chr(10) + block)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(merged, encoding="utf-8")
        os.replace(tmp, target)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise ChatSessionError("写对话留档失败：" + type(exc).__name__) from None


def _render_history(turns) -> str:
    blocks = []
    for turn in turns:
        who = USER_LABEL if turn.role == "user" else ASSISTANT_LABEL
        blocks.append(who + "：" + str(turn.text).strip())
    return "\n\n".join(blocks)


def _split_for_summary(turns, room: int):
    """把历史切成「要压的旧轮次」与「原文保留的新轮次」。"""
    kept: list = []
    used = 0
    for turn in reversed(turns):
        piece = len(_render_history([turn])) + 2
        if kept and used + piece > room:
            break
        kept.append(turn)
        used += piece
    kept.reverse()
    old_count = len(turns) - len(kept)
    return turns[:old_count], kept


def build_prompt(
    context: str,
    turns,
    message: str,
    summarizer=None,
    profile_dir: Path | str | None = None,
    when: str = '',
) -> str:
    """拼本轮 prompt：handoff 全文 + 历史（+ 早期摘要）+ 新消息。

    历史放不下时（T-043）：
    - 有 summarizer → 把最旧的轮次**压成摘要块**（≤ SUMMARY_BUDGET 字），
      摘要可以落盘缓存（传 profile_dir/when）避免每轮重压；
    - 没有 summarizer → 退回老的**硬裁**行为（老调用方不受影响）。

    handoff 全文**永不裁**。
    """
    ask = str(message or '').strip()
    if not ask:
        raise ChatSessionError("消息不能为空")

    head = "下面是这道练习的接力上下文，请据此回答我的问题：" + chr(10) + chr(10)
    body = str(context or '').strip()
    tail = chr(10) + chr(10) + "【我的问题】" + ask + chr(10)

    if not turns:
        return head + body + tail

    plain = chr(10) + chr(10) + "【之前的对话】" + chr(10) + _render_history(turns) + chr(10)
    if len(head) + len(body) + len(tail) + len(plain) <= MAX_PROMPT_CHARS:
        return head + body + plain + tail

    room = MAX_PROMPT_CHARS - len(head) - len(body) - len(tail)
    if room < MIN_HISTORY_BUDGET:
        room = MIN_HISTORY_BUDGET

    old_turns, kept = _split_for_summary(turns, room)

    if summarizer is None or not old_turns:
        note = chr(10) + "（历史过长，已裁剪 " + str(len(old_turns)) + " 轮最旧的对话；接力上下文未裁剪）"
        history = chr(10) + chr(10) + "【之前的对话】" + note + chr(10) + _render_history(kept) + chr(10)
        return head + body + history + tail

    summary = _get_or_make_summary(summarizer, old_turns, profile_dir, when)
    note = chr(10) + "（更早的 " + str(len(old_turns)) + " 轮已压缩成摘要；接力上下文未裁剪）"
    history = (
        chr(10) + chr(10) + "【之前的对话】"
        + chr(10) + chr(10) + "【较早对话摘要】" + chr(10)
        + str(summary.text).strip()[:SUMMARY_BUDGET]
        + chr(10)
        + note
        + chr(10)
        + _render_history(kept)
        + chr(10)
    )
    return head + body + history + tail


def _get_or_make_summary(summarizer, old_turns, profile_dir, when) -> HistorySummary:
    """取缓存或压一次；结果落进程内缓存（传了 profile_dir 时也落盘）。"""
    key = (str(profile_dir or ''), str(when or ''), len(old_turns))
    if profile_dir and when:
        stored = load_summary(profile_dir, when)
        if stored is not None and stored.upto >= len(old_turns):
            _SUMMARY_MEMO[key] = stored
            return stored
    if key in _SUMMARY_MEMO:
        return _SUMMARY_MEMO[key]

    produced = summarizer(old_turns)
    text, upto = (produced if isinstance(produced, tuple) else (produced, len(old_turns)))
    summary = HistorySummary(
        text=str(text or '').strip()[: SUMMARY_BUDGET * 4], upto=int(upto or len(old_turns))
    )
    _SUMMARY_MEMO[key] = summary
    if profile_dir and when:
        try:
            save_summary(profile_dir, when, summary.text, summary.upto)
        except ChatSessionError:
            pass
    return summary


SUMMARY_SYSTEM_PROMPT = (
    "你在帮一段长对话做压缩。把下面这段较早的对话压成"
    + chr(10)
    + "不超过 " + str(SUMMARY_BUDGET) + " 字的摘要，要求："
    + chr(10)
    + "1. 保留所有**结论、决定、约定、具体数值/命名**（后面还要引用）；"
    + chr(10)
    + "2. 丢掉寒暄、重复、已经推翻的中间过程；"
    + chr(10)
    + "3. 直接输出摘要正文，不要写「总结如下」之类的前言。"
)


def build_summarizer(completer):
    """把 LLM completer 包成一个摘要器（给 build_prompt 用）。

    返回 `summarizer(old_turns) -> (摘要文本, 覆盖轮数)`。
    LLM 失败时**不抛**：退回一个保底摘要（否则一轮问答会因为压缩失败而整个答不出来）。
    """

    def summarizer(old_turns):
        history = _render_history(old_turns)
        messages = [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": history[: MAX_PROMPT_CHARS]},
        ]
        try:
            raw = completer.complete(messages)
        except Exception:
            return _fallback_summary(old_turns), len(old_turns)
        text = str(raw or "").strip()
        if not text:
            return _fallback_summary(old_turns), len(old_turns)
        return text[:SUMMARY_BUDGET], len(old_turns)

    return summarizer


def _fallback_summary(old_turns) -> str:
    """压不动时的保底：保留最早的结论句 + 说明压缩失败。"""
    pieces = [str(t.text).strip() for t in old_turns if str(t.text).strip()]
    joined = " ".join(pieces)
    return ("（自动摘要失败，以下是早期内容开头）" + joined)[:SUMMARY_BUDGET]
