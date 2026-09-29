"""T-020 经典课程实验题库（F-09）。"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import re
from .planner import GeneratedTask, MASTERED_LEVELS
from .profile import KnowledgeProfile
_META_RE = re.compile("^```yaml\\s*\\n(?P<body>.*?)\\n```\\s*$", re.M | re.S)
_ENTRY_RE = re.compile("^##\\s+(?P<ident>[A-Za-z]+-\\d+)\\s+(?P<title>.+?)\\s*$", re.M)
_GOAL_RE = re.compile("^\\*\\*目标\\*\\*[：:]\\s*(?P<goal>.+?)\\s*$", re.M)
_ACCEPT_RE = re.compile("^\\*\\*验收方式\\*\\*[：:]\\s*(?P<accept>.+?)\\s*$", re.M)
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
    match = re.search("^\\*\\*实现要点\\*\\*[：:]\\s*$", block, re.M)
    if not match:
        return []
    tail = block[match.end():]
    stop = re.search("^\\*\\*|^---", tail, re.M)
    if stop:
        tail = tail[: stop.start()]
    steps = []
    for line in tail.splitlines():
        step = re.match("^\\s*\\d+[.、]\\s*(?P<text>.+?)\\s*$", line)
        if step:
            steps.append(step.group("text"))
    return steps
def load_assignments(path) -> list[Assignment]:
    target = Path(path)
    if not target.is_file():
        return []
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
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
        items.append(Assignment(
            ident=mark.group("ident"),
            title=mark.group("title").strip(),
            course=course,
            tags=tags,
            goal=goal_match.group("goal").strip(),
            steps=_parse_steps(block),
            acceptance=accept_match.group("accept").strip(),
            level=str(meta.get("level") or "入门").strip() or "入门",
            new_skill=new_skill or None,
        ))
    return items
def _mastered_names(profile: KnowledgeProfile) -> set:
    return {point.name for point in profile.points if point.level in MASTERED_LEVELS}
def match_score(assignment: Assignment, profile: KnowledgeProfile):
    mastered = _mastered_names(profile)
    known = {point.name for point in profile.points}
    hit = [tag for tag in assignment.tags if tag in mastered]
    if not hit:
        return None
    if [tag for tag in assignment.tags if tag not in known]:
        return None
    new_skill = assignment.new_skill or None
    if new_skill and new_skill in mastered:
        new_skill = None
    level_rank = -_LEVEL_ORDER.get(assignment.level, 99)
    if new_skill:
        origin = 0 if new_skill in (known - mastered) else 1
        return (origin, -len(hit), 1, level_rank, assignment.ident)
    return (0, -len(hit), 0, level_rank, assignment.ident)
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
    viable = [
        (match_score(item, profile), item)
        for item in assignments
        if item.ident not in excluded
    ]
    viable = [(score, item) for score, item in viable if score is not None]
    if not viable:
        return None
    viable.sort(key=lambda pair: pair[0])
    return viable[0][1]
def assignment_to_task(assignment: Assignment, profile: KnowledgeProfile) -> GeneratedTask:
    mastered = _mastered_names(profile)
    skills = [tag for tag in assignment.tags if tag in mastered]
    new_skill = assignment.new_skill or None
    if new_skill and new_skill in mastered:
        new_skill = None
    return GeneratedTask(
        goal=assignment.goal,
        skills=skills,
        acceptance=assignment.acceptance,
        steps=list(assignment.steps),
        new_skill=new_skill,
        source=assignment.course,
        source_label=assignment.label,
    )
