"""T-020 经典课程实验题库（F-09）。

题库是 profile/assignments.md：每条「## <编号> <标题>」+ 一段 yaml 元数据（course / tags /
level / new_skill）+ 目标 / 实现要点 / 验收方式。出题时先按画像匹配这里的条目，
命中就以该经典实验为骨架出题（不调 LLM），匹配不上才回退 LLM 现编。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

from .fileio import read_text_or_none
from .planner import MASTERED_LEVELS, GeneratedTask
from .profile import KnowledgeProfile

_META_RE = re.compile(r"^```yaml\s*\n(?P<body>.*?)\n```\s*$", re.M | re.S)
_ENTRY_RE = re.compile(r"^##\s+(?P<ident>[A-Za-z]+-\d+)\s+(?P<title>.+?)\s*$", re.M)
_GOAL_RE = re.compile(r"^\*\*目标\*\*[：:]\s*(?P<goal>.+?)\s*$", re.M)
_ACCEPT_RE = re.compile(r"^\*\*验收方式\*\*[：:]\s*(?P<accept>.+?)\s*$", re.M)
_STEPS_HEAD_RE = re.compile(r"^\*\*实现要点\*\*[：:]\s*$", re.M)
_STEPS_STOP_RE = re.compile(r"^\*\*|^---", re.M)
_STEP_RE = re.compile(r"^\s*\d+[.、]\s*(?P<text>.+?)\s*$")
_LEVEL_ORDER = {level: index for index, level in enumerate(("入门", "进阶", "挑战"))}


@dataclass(frozen=True)
class Assignment:
    ident: str
    title: str
    course: str
    tags: list[str] = field(default_factory=list)
    goal: str = ""
    steps: list[str] = field(default_factory=list)
    acceptance: str = ""
    level: str = "入门"
    new_skill: str | None = None

    @property
    def label(self) -> str:
        return self.ident + " " + self.title


def _unquote(raw: str) -> str:
    return raw.strip().strip("'").strip('"')


def _parse_meta(block: str) -> dict:
    """解析条目里的 ```yaml 元数据（只认 key: value 与 key: [a, b] 两种写法）。"""
    meta: dict = {}
    match = _META_RE.search(block)
    if not match:
        return meta
    for line in match.group("body").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, raw = line.partition(":")
        key = key.strip()
        raw = raw.strip()
        if raw.startswith("[") and raw.endswith("]"):
            meta[key] = [item.strip() for item in raw[1:-1].split(",") if item.strip()]
        else:
            meta[key] = _unquote(raw)
    return meta


def _parse_steps(block: str) -> list[str]:
    match = _STEPS_HEAD_RE.search(block)
    if not match:
        return []
    tail = block[match.end():]
    stop = _STEPS_STOP_RE.search(tail)
    if stop:
        tail = tail[: stop.start()]
    steps = []
    for line in tail.splitlines():
        step = _STEP_RE.match(line)
        if step:
            steps.append(step.group("text"))
    return steps


def load_assignments(path) -> list[Assignment]:
    """读题库；文件不存在或读不了返回空列表。缺 course / tags / 目标 / 验收方式的条目跳过。"""
    text = read_text_or_none(path)
    if text is None:
        return []
    marks = list(_ENTRY_RE.finditer(text))
    items: list[Assignment] = []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        block = text[mark.end():end]
        meta = _parse_meta(block)
        goal_match = _GOAL_RE.search(block)
        accept_match = _ACCEPT_RE.search(block)
        course = str(meta.get("course") or "").strip()
        tags = meta.get("tags") or []
        if not isinstance(tags, list):
            tags = [str(tags)]
        if not (course and tags and goal_match and accept_match):
            continue
        new_skill = str(meta.get("new_skill") or "").strip()
        items.append(
            Assignment(
                ident=mark.group("ident"),
                title=mark.group("title").strip(),
                course=course,
                tags=tags,
                goal=goal_match.group("goal").strip(),
                steps=_parse_steps(block),
                acceptance=accept_match.group("accept").strip(),
                level=str(meta.get("level") or "入门").strip() or "入门",
                new_skill=new_skill or None,
            )
        )
    return items


def _mastered_names(profile: KnowledgeProfile) -> set:
    return {point.name for point in profile.points if point.level in MASTERED_LEVELS}


def _effective_new_skill(assignment: Assignment, mastered: set) -> str | None:
    """条目声明的新点；已经掌握了就不算新点。"""
    new_skill = assignment.new_skill or None
    return None if new_skill in mastered else new_skill


def _score(assignment: Assignment, mastered: set, known: set):
    """排序键（越小越好）；不适合当前画像返回 None。

    规则：至少命中一个已掌握标签；标签里不许有画像完全没见过的点；
    新点优先选「画像里有但还没掌握」的，其次命中标签多、难度低、编号小。
    """
    hit = [tag for tag in assignment.tags if tag in mastered]
    if not hit:
        return None
    if any(tag not in known for tag in assignment.tags):
        return None
    level_rank = -_LEVEL_ORDER.get(assignment.level, 99)
    new_skill = _effective_new_skill(assignment, mastered)
    if new_skill:
        origin = 0 if new_skill in (known - mastered) else 1
        return (origin, -len(hit), 1, level_rank, assignment.ident)
    return (0, -len(hit), 0, level_rank, assignment.ident)


def match_score(assignment: Assignment, profile: KnowledgeProfile):
    """单条条目与画像的匹配分（排序键，越小越好；不匹配返回 None）。"""
    return _score(assignment, _mastered_names(profile), {point.name for point in profile.points})


def pick_assignment(
    assignments,
    profile: KnowledgeProfile,
    skip: set | None = None,
    already_given: set | None = None,
):
    """挑一条最适合当前画像的条目。

    - `skip`：被 A-06 拒绝过的条目（本次挑选内排除）；
    - `already_given`（T-023 L-02）：**已经出过**的条目编号。
      题库是确定性的：画像没变时永远命中同一条，于是 next 会一直出同一题。
      把出过的排除掉，才能连着出不同的题。
    """
    if not assignments:
        return None
    excluded = (skip or set()) | (already_given or set())
    # 画像集合只算一次（以前每条条目都重算一遍）
    mastered = _mastered_names(profile)
    known = {point.name for point in profile.points}
    viable = []
    for item in assignments:
        if item.ident in excluded:
            continue
        score = _score(item, mastered, known)
        if score is not None:
            viable.append((score, item))
    if not viable:
        return None
    return min(viable, key=lambda pair: pair[0])[1]


def assignment_to_task(assignment: Assignment, profile: KnowledgeProfile) -> GeneratedTask:
    mastered = _mastered_names(profile)
    return GeneratedTask(
        goal=assignment.goal,
        skills=[tag for tag in assignment.tags if tag in mastered],
        acceptance=assignment.acceptance,
        steps=list(assignment.steps),
        new_skill=_effective_new_skill(assignment, mastered),
        source=assignment.course,
        source_label=assignment.label,
    )
