"""T-028 作业点评：按验收方式给评价 + 建议，并留档到 tasks.md。

设计要点：
- 代码上限 8000 字符，超额**截断并在代码里注明**（不静默丢内容）；
- prompt 里必须带上**验收方式**——点评要对齐"这道题要什么"，不是泛泛而谈；
- 评测结果拆成「评价」与「建议」两段，便于留档与展示；没有分区时整段当评价。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


class ReviewError(Exception):
    """点评失败（LLM 不可用、返回为空等）。"""


# 代码上限：超过就截断，并在代码里留说明
MAX_CODE_CHARS = 8000
TRUNCATED_NOTE = "\n\n/* …代码超出 {limit} 字符，已截断（原文 {total} 字符），点评基于前 {limit} 字符… */"


@dataclass(frozen=True)
class ReviewResult:
    feedback: str
    suggestion: str
    code: str
    truncated: bool = False
    # T-035：这次作业里可复用的「问题点」（最多 3 条），进错题本
    problems: list = field(default_factory=list)

    def render(self) -> str:
        parts = [f"【评价】{self.feedback}"]
        if self.suggestion:
            parts.append(f"【建议】{self.suggestion}")
        if self.truncated:
            parts.append("（代码超过 8000 字符，已截断后点评）")
        return "\n\n".join(parts)


def prepare_code(code: str) -> tuple[str, bool]:
    """把提交的代码裁到上限；超额时在结尾注明，返回 (代码, 是否截断)。"""
    text = str(code or "")
    if len(text) <= MAX_CODE_CHARS:
        return text, False
    head = text[:MAX_CODE_CHARS]
    note = TRUNCATED_NOTE.format(limit=MAX_CODE_CHARS, total=len(text))
    # 注记本身也算进上限，保证返回长度不超
    if len(note) >= MAX_CODE_CHARS:
        return note[:MAX_CODE_CHARS], True
    return head[: MAX_CODE_CHARS - len(note)] + note, True


def build_review_messages(
    goal: str,
    acceptance: str,
    code: str,
    *,
    truncated: bool = False,
    with_problems: bool = False,
) -> list[dict]:
    """构造点评 prompt。**验收方式是点评的标尺**，必须带上。"""
    limit_note = ""
    if truncated:
        limit_note = "\n（注意：代码超过 8000 字符已被截断，只看到前 8000 字符，请在评价里说明这一点。）"
    system = (
        "你是一位严格但友善的编程助教，负责批改学生的动手作业。\n"
        "请**严格对照验收方式**判断是否达标，然后给出：\n"
        "1) 评价：做到了什么、哪里不对、是否通过验收（讲具体，不要客套）；\n"
        "2) 建议：下一步可执行的改进点（1~3 条，越具体越好）。\n"
        "输出格式必须严格为两段：\n【评价】…\n【建议】…"
    )
    if with_problems:
        system += (
            "\n另外用一行给出【问题点】：把这次作业里可复用的**具体毛病**列出来"
            "（短句，像「缩进混乱」「忘记空格」这种，最多 3 条，用、分隔）。"
            "这些会被记进错题本、影响后续出题，所以要具体、不要客套。"
        )
    user = (
        f"【任务目标】{goal or '(未记录)'}\n"
        f"【验收方式】{acceptance or '(未记录，按任务目标判断)'}{limit_note}\n\n"
        f"【学生提交的代码】\n```\n{code}\n```"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


PROBLEM_MARKER = "【问题点】"
MAX_PROBLEMS = 3


def _split_problems(text: str) -> list[str]:
    """把「【问题点】缩进混乱、忘记空格」拆成短句列表（去重、最多 3 条）。"""
    body = text.split(PROBLEM_MARKER, 1)
    if len(body) < 2:
        return []
    chunk = body[1].split("\n", 1)[0]
    items: list[str] = []
    for piece in re.split(r"[、,，;；]+", chunk):
        clean = re.sub(r"\s+", " ", piece).strip(" \t-—.。")
        if clean and clean not in items:
            items.append(clean)
    return items[:MAX_PROBLEMS]


def parse_review(raw: str, *, with_problems: bool = False):
    """把 LLM 回复拆成 (评价, 建议)；with_problems=True 时再多返回问题点列表。

    没有分区时整段当评价；问题点缺失就是空列表（不报错——点评本身还有用）。
    """
    text = str(raw or "").strip()
    if not text:
        raise ReviewError("LLM 返回了空点评，请重试")

    problems: list[str] = []
    if with_problems:
        problems = _split_problems(text)
        text = text.split(PROBLEM_MARKER, 1)[0].rstrip()

    feedback = text
    suggestion = ""
    marker = text.find("【建议】")
    if marker >= 0:
        feedback = text[:marker]
        suggestion = text[marker + len("【建议】"):]
    feedback = feedback.replace("【评价】", "", 1).strip()
    suggestion = suggestion.strip()
    if not feedback:
        raise ReviewError("LLM 没有给出评价")

    if with_problems:
        return feedback, suggestion, problems
    return feedback, suggestion


def review_code(
    *, goal: str, acceptance: str, code: str, completer: Any, with_problems: bool = True
) -> ReviewResult:
    """让 LLM 按验收方式点评代码，并返回结构化结果。

    with_problems（T-035）：顺带让模型给 ≤3 条「问题点」，进错题本影响后续出题。
    """
    prepared, truncated = prepare_code(code)
    messages = build_review_messages(
        goal, acceptance, prepared, truncated=truncated, with_problems=with_problems
    )
    try:
        raw = completer.complete(messages)
    except Exception as exc:
        raise ReviewError(f"点评失败：{exc}") from None
    if with_problems:
        feedback, suggestion, problems = parse_review(raw, with_problems=True)
    else:
        feedback, suggestion = parse_review(raw)
        problems = []
    return ReviewResult(
        feedback=feedback,
        suggestion=suggestion,
        code=prepared,
        truncated=truncated,
        problems=problems,
    )
