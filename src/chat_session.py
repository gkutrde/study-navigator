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


@dataclass(frozen=True)
class ChatTurn:
    role: str
    text: str
    at: str = ""


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
    return "\n".join(lines).rstrip() + "\n"


def save_archive(profile_dir: Path | str, when: str, turns) -> Path:
    """原子写留档（tmp + replace），失败抛 ChatSessionError。"""
    target = archive_path(profile_dir, when)
    tmp = target.with_name(target.name + ".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(render_archive(when, turns), encoding="utf-8")
        os.replace(tmp, target)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise ChatSessionError("写对话留档失败：" + type(exc).__name__) from None
    return target


_HEADING_RE = re.compile(r"^##\s+(?P<who>.+?)(?:（(?P<at>[^）]*)）)?\s*$", re.M)


def _decode_archive(text: str) -> list:
    """把留档读回成 turns。容忍手工编辑：认不出的小节按 assistant 处理。"""
    turns: list = []
    marks = list(_HEADING_RE.finditer(text))
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        body = text[mark.end():end].strip()
        if not body:
            continue
        who = mark.group("who").strip()
        role = "user" if who == USER_LABEL else "assistant"
        turns.append(ChatTurn(role=role, text=body, at=(mark.group("at") or "")))
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
    at: str | None = None,
) -> list:
    """追加一轮并落盘，返回追加后的完整历史。"""
    kind = _normalize(role)
    body = str(text or "").strip()
    if not body:
        raise ChatSessionError("消息不能为空")
    moment = at or time.strftime("%Y-%m-%d %H:%M")
    turns = load_turns(profile_dir, when)
    turns.append(ChatTurn(role=kind, text=body, at=moment))
    save_archive(profile_dir, when, turns)
    return turns


def _render_history(turns) -> str:
    blocks = []
    for turn in turns:
        who = USER_LABEL if turn.role == "user" else ASSISTANT_LABEL
        blocks.append(who + "：" + str(turn.text).strip())
    return "\n\n".join(blocks)


def build_prompt(context: str, turns, message: str) -> str:
    """拼本轮 prompt：handoff 全文 + 历史 + 新消息。

    历史放不下时**从最旧开始裁**并注明裁了几轮——handoff 全文永不裁。
    """
    ask = str(message or "").strip()
    if not ask:
        raise ChatSessionError("消息不能为空")

    head = "下面是这道练习的接力上下文，请据此回答我的问题：\n\n"
    body = str(context or "").strip()
    tail = "\n\n【我的问题】" + ask + "\n"

    if not turns:
        return head + body + tail

    plain = "\n\n【之前的对话】\n" + _render_history(turns) + "\n"
    if len(head) + len(body) + len(tail) + len(plain) <= MAX_PROMPT_CHARS:
        return head + body + plain + tail

    room = MAX_PROMPT_CHARS - len(head) - len(body) - len(tail)
    if room < MIN_HISTORY_BUDGET:
        room = MIN_HISTORY_BUDGET

    kept: list = []
    used = 0
    for turn in reversed(turns):
        piece = len(_render_history([turn])) + 2
        if kept and used + piece > room:
            break
        kept.append(turn)
        used += piece
    kept.reverse()
    trimmed = len(turns) - len(kept)
    if trimmed < 0:
        trimmed = 0

    note = "\n（历史过长，已裁剪 " + str(trimmed) + " 轮最旧的对话；接力上下文未裁剪）"
    history = "\n\n【之前的对话】" + note + "\n" + _render_history(kept) + "\n"
    return head + body + history + tail
