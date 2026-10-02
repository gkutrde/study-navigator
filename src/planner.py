"""T-005：出题（next）——读画像 [+ 地图]，生成一个可验收的动手任务。

约束（[[模块-任务生成]]）：

- 只用画像里已有的知识点，**至多 1 个新知识点**；
- 有地图时，新点优先取地图中按书序的下一个未掌握点；无地图则降级为「仅画像版」；
- 输出含目标、用到的知识点、验收方式；默认 Python；
- 不替客户写代码 —— 任务里的代码由客户自己写。

越界（声明了画像里没有的知识点）会带着提示重试一次，仍不符则报错不出题。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
from typing import Sequence

from .distill import KnowledgePoint
from .fileio import read_text_or_none, write_text_atomic
from .llm import JSONExtractionError, LLMError, extract_json
from .profile import DEFAULT_TOPIC, MASTERED_LEVELS, KnowledgeProfile

MIN_POINTS = 3
MAX_NEW_SKILLS = 1
MAX_RECENT_GOALS = 5
MAX_PROFILE_IN_PROMPT = 40
MAX_UNCERTAIN_IN_PROMPT = 10
DEFAULT_LANGUAGE = "Python"

# 「未分类」主题：与画像同一个常量（以前两边各写一份字面量）
UNCLASSIFIED_TOPIC = DEFAULT_TOPIC


def _topic_of(point) -> str:
    """知识点所属主题；空主题归「未分类」（主题过滤、看板多选、选点都按这个口径）。"""
    return (point.topic or UNCLASSIFIED_TOPIC).strip() or UNCLASSIFIED_TOPIC


def _book_points(book) -> set[str]:
    """一本书里出现过的全部点名（去首尾空白）。"""
    return {
        str(point).strip()
        for chapter in getattr(book, "chapters", []) or []
        for point in getattr(chapter, "points", []) or []
    }


class PlannerError(RuntimeError):
    """出题失败：画像不足、LLM 失败或输出越界/不可解析。"""


@dataclass(frozen=True)
class GeneratedTask:
    goal: str
    skills: list[str]
    acceptance: str
    steps: list[str] = field(default_factory=list)
    new_skill: str | None = None
    # T-020：命中题库时记录出处课程与条目编号；LLM 现编的任务留空
    source: str | None = None
    source_label: str | None = None
    # T-035：复习题标记（看板画「复习」角标；计数时也不算新题）
    is_review: bool = False

    def as_dict(self) -> dict:
        payload = {
            "goal": self.goal,
            "skills": list(self.skills),
            "acceptance": self.acceptance,
            "steps": list(self.steps),
        }
        if self.new_skill:
            payload["new_skill"] = self.new_skill
        if self.source:
            payload["source"] = self.source
        if self.source_label:
            payload["source_label"] = self.source_label
        return payload


SYSTEM_PROMPT = """你是学习教练，为一名大一计算机方向的学生安排「现在就动手做」的编程任务。

学生背景：Python 是主力语言（正学 C++，前端只会 HTML/CSS 基础）。默认出 Python 任务。

硬性约束：
1. 任务主体只能使用「已掌握知识点」清单里的知识点。
2. 最多只能引入 `1 个`新知识点。若给了知识地图，新点必须是地图中按书序的「下一个未掌握点」；没有地图时你可以自行提出一个新点。
3. 任务要能在 1~3 小时内完成，产出可运行的代码。
4. 验收方式必须具体到「运行后能观察到什么」。
5. **不要替学生写代码**：只给目标、要点和步骤提示，代码由学生自己写。
6. 只输出一个 JSON 对象，不要输出 JSON 以外的文字。

JSON 字段：
- "goal"：要做出的东西（一句话）
- "skills"：用到的知识点名称数组（必须来自已掌握清单；§NOCODE§只写知识点名称，不要带主题§NOCODE§，
  例如写 "列表" 而不是 "列表（Python 基础）"）
- "new_skill"：新知识点名称（没有就填 null）
- "steps"：3~5 条实现要点提示
- "acceptance"：验收方式（运行后能观察到什么）
"""


def describe_profile(profile: KnowledgeProfile, limit: int | None = None) -> str:
    points = profile.points if limit is None else profile.points[:limit]
    if not points:
        return "（画像为空）"
    return "\n".join(f"- {point.name}（{point.topic or UNCLASSIFIED_TOPIC}）：{point.level}" for point in points)


def describe_syllabus(syllabus: dict | None) -> str:
    if not syllabus:
        return "（没有知识地图：请按「仅画像版」出题，新点自行提出）"
    book = syllabus.get("book") or "未命名"
    lines = [f"《{book}》"]
    for chapter in syllabus.get("chapters") or []:
        name = chapter.get("chapter") or ""
        points = "、".join(chapter.get("points") or [])
        lines.append(f"- {name}：{points}")
    return "\n".join(lines)


# T-042：地图摘录的字符预算（实测 C++ Primer 全章节 5901 字符把 prompt 撑爆）
SYLLABUS_EXCERPT_BUDGET = 2000
# 选中点所在章的前后各取几章
SYLLABUS_NEIGHBOUR_CHAPTERS = 1


def describe_syllabus_excerpt(book, focus_point: str | None, budget: int = SYLLABUS_EXCERPT_BUDGET) -> str:
    """只描述**这一本**书里跟 focus_point 相关的一段（T-042）。

    实测的错位：选点用「与画像最相关的书」（HTML），prompt 却塞 books_map[0]
    的**全章节**（C++ Primer，5901 字符）——LLM 看到的地图与选点依据对不上。

    这里：
    - 只放选中这本书；
    - 只放 focus_point 所在章 ± 前后各一章；
    - 附一行全图摘要（总章数/总点数），让模型知道还有别的；
    - 超预算时继续砍邻章（保留选中章）。
    """
    chapters = list(getattr(book, "chapters", []) or [])
    if not chapters:
        return "（这本书没有章节信息）"

    title = str(getattr(book, "book", "") or "未命名")
    total_points = sum(len(getattr(ch, "points", []) or []) for ch in chapters)
    summary = f"《{title}》共 {len(chapters)} 章 / {total_points} 个点（全图摘要）"

    target = str(focus_point or "").strip()
    center = 0
    if target:
        for index, chapter in enumerate(chapters):
            if target in (getattr(chapter, "points", []) or []):
                center = index
                break

    def render(index: int) -> str:
        chapter = chapters[index]
        name = getattr(chapter, "chapter", "") or ""
        points = "、".join(getattr(chapter, "points", []) or [])
        return f"- {name}：{points}"

    # 邻章从近到远依次加入，超预算就停
    order = [center]
    for delta in range(1, SYLLABUS_NEIGHBOUR_CHAPTERS + 1):
        for index in (center - delta, center + delta):
            if 0 <= index < len(chapters):
                order.append(index)

    kept: list[int] = []
    for index in order:
        candidate = kept + [index]
        body = chr(10).join(render(i) for i in sorted(candidate))
        if len(body) > budget and kept:
            break
        kept = candidate

    lines = [summary]
    lines.extend(render(i) for i in sorted(kept))
    return chr(10).join(lines)


def build_next_messages(
    profile: KnowledgeProfile,
    syllabus: dict | None = None,
    violations: Sequence[str] | None = None,
    recent_goals: Sequence[str] | None = None,
    topics=None,
    weaknesses: Sequence[str] | None = None,
    book=None,
    focus_point: str | None = None,
) -> list[dict[str, str]]:
    """构造出题 messages。

    `violations` 用于重试时说明上一次越界在哪；
    `recent_goals`（T-023 L-02）：最近出过的任务目标——不带上它，模型很容易又出同一题。
    `topics`（T-029）：只看这些主题的知识点。
    `weaknesses`（T-035）：错题本里累积的问题点——出题要优先让学员练到这些毛病。
    """
    profile = filter_profile_by_topics(profile, topics)
    mastered = [p for p in profile.points if p.level in MASTERED_LEVELS]
    uncertain = [p for p in profile.points if p.level not in MASTERED_LEVELS]

    # 控制 prompt 长度，避免知识点一多就把上下文塞满
    parts = [
        "已掌握知识点（只能用这些）：",
        describe_profile(KnowledgeProfile(points=mastered), limit=MAX_PROFILE_IN_PROMPT)
        if mastered
        else "（暂无）",
        "",
        "仍存疑的知识点（不要当作已掌握来出题）：",
        describe_profile(KnowledgeProfile(points=uncertain), limit=MAX_UNCERTAIN_IN_PROMPT)
        if uncertain
        else "（无）",
        "",
        "知识地图（新点优先取其中按书序的下一个未掌握点）：",
        # T-042：传了 book 就只展示这本书的相关章——地图必须和选点依据是同一本书
        describe_syllabus_excerpt(book, focus_point) if book is not None else describe_syllabus(syllabus),
        "",
        "请给出下一个动手任务。",
    ]

    # T-035：错题本注入——让出题优先练到反复犯的毛病
    complaints = [str(item).strip() for item in (weaknesses or []) if str(item).strip()]
    if complaints:
        parts.append("")
        parts.append("这位学员反复出现这些问题点（错题本），**设计任务时要让他练到、并要求他别再犯**：")
        parts.extend(f"- {item}" for item in complaints)

    goals = [str(goal).strip() for goal in (recent_goals or []) if str(goal).strip()]
    if goals:
        parts.append("")
        parts.append("已经出过这些任务，**不要重复**（换个不同的目标或不同的场景）：")
        parts.extend(f"- {goal}" for goal in goals[-MAX_RECENT_GOALS:])

    next_point = next_unmet_point(syllabus, profile)
    if next_point:
        parts.append(f"提示：地图中按书序的下一个未掌握点是「{next_point}」，优先把它作为新知识点。")
    elif syllabus:
        parts.append("提示：地图中的知识点学生都已掌握，本次可以不出新点。")

    if violations:
        parts += [
            "",
            "上一次的输出越界了：下列知识点既不在画像里，也没有被标成新知识点："
            + "、".join(violations),
            "请重新出题，skills 里只能出现画像中的知识点。",
        ]

    return [
        {"role": "system", "content": SYSTEM_PROMPT.replace("`", "").replace("**", "")},
        {"role": "user", "content": "\n".join(parts)},
    ]


def _point_in_topics(point_name: str, allowed: set[str], profile: KnowledgeProfile) -> bool:
    """地图上的点名是否落在选中主题里（靠画像里的同名点反查主题）。

    地图本身没有主题字段，主题只存在于画像，所以这里"按名字反查"。
    画像里查不到的点（真正的全新点）没有主题信息，**不算落入任何主题**——
    否则"选样式"时会把一堆未知的 HTML 点也带出来。
    """
    name = str(point_name or "").strip()
    if not name:
        return False
    for point in profile.points:
        if point.name == name:
            return _topic_of(point) in allowed
    return False


def _keep_points_in_topics(book, allowed: set[str], profile: KnowledgeProfile):
    """复制一本书，只保留落在 allowed 主题里的点；没有点就返回 None（整本丢弃）。"""
    from .syllabus import BookMap, Chapter

    kept_chapters = []
    for chapter in getattr(book, "chapters", []) or []:
        kept = [
            str(point)
            for point in (getattr(chapter, "points", []) or [])
            if _point_in_topics(point, allowed, profile)
        ]
        if kept:
            kept_chapters.append(Chapter(getattr(chapter, "title", "") or "", kept))
    if not kept_chapters:
        return None
    return BookMap(book=getattr(book, "book", "") or "", chapters=kept_chapters)


# ---------- T-035 复习题与错题本 ----------

# 每出满这么多**新题**，下一道就出复习题
REVIEW_EVERY_NEW_TASKS = 3
# 默认「多久没碰算超期」（天）；可配
DEFAULT_STALE_DAYS = 14
# 任务块里标记复习题的行
REVIEW_FLAG = "**复习**：是"


def count_new_tasks(path) -> int:
    """数「上一道复习题之后」出了几道新题。

    复习题本身不计数——它就是用来打断新题连发的，出完重新开始数。
    """
    records = read_task_records(path)
    count = 0
    for record in reversed(records):
        if is_review_record(record):
            break
        count += 1
    return count


def is_review_record(record) -> bool:
    """这条任务记录是不是复习题（新写入的看 **复习** 标记，老的看目标前缀）。"""
    raw = getattr(record, "raw", "") or ""
    if "**复习**" in raw:
        return True
    return str(getattr(record, "goal", "") or "").strip().startswith("复习")


def review_due(path, *, every: int = REVIEW_EVERY_NEW_TASKS, profile=None, stale_days: int = DEFAULT_STALE_DAYS) -> bool:
    """是不是该出复习题了。

    两个条件都要满足：**到节奏了**（出满 N 道新题）**并且有超期没碰的点**。
    只看到节奏就出，会在"刚出完题、所有点都刷新成今天"时给出空复习——
    实测踩过：连出 4 题，第 4 题因为挑不出超期点而又变成新题。
    """
    if count_new_tasks(path) < max(1, every):
        return False
    if profile is None:
        return True
    return pick_review_point(profile, stale_days=stale_days) is not None


def _days_since(stamp: str, today) -> int | None:
    text = str(stamp or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (today - parsed).days


def pick_review_point(profile, *, stale_days: int = DEFAULT_STALE_DAYS, today=None):
    """从「学过但超期没碰」的点里挑一个（挑不出来返回 None）。

    只有「学过」参与：存疑的还没学会、做过/输出的刚练过，都不是复习目标。
    **没有 last_touched 的老画像按超期算**——否则这个功能对老数据永远不生效。
    """
    moment = today or datetime.now().date()
    threshold = max(0, int(stale_days))
    candidates: list[tuple[int, str]] = []
    for point in profile.points:
        if point.level != "学过":
            continue
        gap = _days_since(getattr(point, "last_touched", ""), moment)
        if gap is None or gap >= threshold:
            # 没有时间戳的老画像按「很久没碰」排：越久没碰越优先
            candidates.append((gap if gap is not None else 10 ** 6, point.name))
    if not candidates:
        return None
    # max 取第一个最大值：并列时保持画像里的顺序（稳定）
    return max(candidates, key=lambda item: item[0])[1]


def mark_review(task: "GeneratedTask", point: str) -> "GeneratedTask":
    """把任务标成复习题（目标加前缀，看板靠 is_review 画角标）。"""
    goal = str(task.goal or "").strip()
    if not goal.startswith("复习"):
        goal = f"复习：{point}｜{goal}" if goal else f"复习：{point}"
    skills = list(task.skills or [])
    if point and point not in skills:
        skills = [point] + skills
    return GeneratedTask(
        goal=goal,
        skills=skills,
        acceptance=task.acceptance,
        steps=list(task.steps or []),
        new_skill="",
        source=task.source,
        source_label=task.source_label,
        is_review=True,
    )


def render_review_task(point: str) -> "GeneratedTask":
    """不调 LLM 的保底复习题（LLM 路径失败也要能出）。"""
    return GeneratedTask(
        goal=f"复习：{point}",
        skills=[point],
        acceptance=f"不看笔记，用「{point}」重做一个小例子并能讲清它解决什么问题",
        steps=["凭记忆写一个最小例子", "对照笔记找差距", "用一句话说清它解决什么问题"],
        new_skill="",
        is_review=True,
    )


def selectable_topics(profile: KnowledgeProfile) -> list[str]:
    """画像里出现过的主题（用于看板多选）。「未分类」永远排最后。"""
    seen: list[str] = []
    for point in profile.points:
        topic = _topic_of(point)
        if topic not in seen:
            seen.append(topic)
    # 保序（画像里的出现顺序）——看板的复选框顺序要稳定、可预期；
    # 只把「未分类」压到最后。
    classified = [topic for topic in seen if topic != UNCLASSIFIED_TOPIC]
    unclassified = [topic for topic in seen if topic == UNCLASSIFIED_TOPIC]
    return classified + unclassified


def normalize_topics(topics) -> list[str]:
    """去重、去空白、保序。None/空 → []（表示"没指定"）。"""
    if not topics:
        return []
    if isinstance(topics, str):
        topics = [topics]
    result: list[str] = []
    for item in topics:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def resolve_topics(available: Sequence[str], exclude=None) -> list[str]:
    """从"全部可选主题"里去掉被排除的，得到**实际参与出题**的主题。

    T-029：全不选是明确的用户错误（没有知识池就没法出题），必须报错而不是硬出。
    """
    everything = normalize_topics(available)
    removed = set(normalize_topics(exclude))
    kept = [topic for topic in everything if topic not in removed]
    if not kept:
        raise PlannerError(
            "主题过滤后没有可用的知识点：至少要留一个主题（当前把 "
            + "、".join(everything)
            + " 全排除了）"
        )
    return kept


def filter_profile_by_topics(profile: KnowledgeProfile, topics=None) -> KnowledgeProfile:
    """按主题裁剪画像知识池。topics 为空表示不过滤（原样返回）。"""
    wanted = normalize_topics(topics)
    if not wanted:
        return profile
    allowed = set(wanted)
    return KnowledgeProfile(points=[point for point in profile.points if _topic_of(point) in allowed])


def next_unmet_point(syllabus: dict | None, profile: KnowledgeProfile) -> str | None:
    """按书序找地图中第一个「画像里还没有（或仅存疑）」的知识点。"""
    if not syllabus:
        return None
    mastered = {p.name for p in profile.points if p.level in MASTERED_LEVELS}
    for chapter in syllabus.get("chapters") or []:
        for point in chapter.get("points") or []:
            name = str(point).strip()
            if name and name not in mastered:
                return name
    return None


def pick_book_and_point(
    books: list | None,
    profile: KnowledgeProfile,
    raw_books: list | None = None,
    topics=None,
) -> tuple[object, str] | None:
    """选书 + 选点，**一次做完并一起返回**（T-042）。

    为什么必须一起返回：prompt 里的地图要塞"选中的那本书"，
    而"选中哪本书"是这里的选书逻辑决定的。分成两个函数各自算一遍，
    就会出现实测那个错位——选点用了 HTML 书、prompt 却塞了 books_map[0]（C++ Primer）。

    返回 (书对象, 点)。书对象取自 raw_books（真名更有信息量），保持与 books 同序。
    """
    if not books:
        return None

    # T-029：过滤在**点**这一级做——只把"落在选中主题里"的点放进书。
    #
    # 曾经写成"按书过滤"（整本书只要有一个点匹配就留下），结果是：
    # 「网页书」里有一个画像还未知的点（弹性盒），整本书就被留下，
    # 于是只选「样式与布局」时仍然会挑出「网页书」的「网格布局」。
    # 正确语义是"在选中主题里找下一个该学的点"，所以必须逐点筛。
    wanted = normalize_topics(topics)
    if wanted:
        allowed = set(wanted)
        books = [_keep_points_in_topics(book, allowed, profile) for book in books]
        books = [book for book in books if book is not None]
        if raw_books:
            raw_books = [_keep_points_in_topics(book, allowed, profile) for book in raw_books]
            raw_books = [book for book in raw_books if book is not None]
        if not books:
            return None

    source = raw_books or books
    mastered = {p.name for p in profile.points if p.level in MASTERED_LEVELS}
    profile_names = {p.name for p in profile.points}

    if not mastered:
        chosen = source[0]
        found = _first_unmet_in_book(chosen, mastered)
        return (chosen, found) if found else None

    # 每本书与画像的交集大小只算一次（选书与按相关度排序都用它）
    hits = [len(_book_points(book) & mastered) for book in books]
    if not any(hits):
        # 没有任何书与画像有交集 → 退回第一本
        chosen = source[0]
        found = _first_unmet_in_book(chosen, mastered)
        return (chosen, found) if found else None
    best_index = hits.index(max(hits))  # 平手取地图里靠前的那本

    # 选中的书若已没有"该学的新东西"，就按相关度依次看下一本（T-021 实测：
    # HTML 书的高置信度点全已掌握时，硬塞一个未映射的零碎条目没有意义）。
    ranked = sorted(range(len(books)), key=lambda i: -hits[i])
    for candidate_index in ranked:
        found = _mapped_unmastered_in_book(
            books[candidate_index],
            source[candidate_index],
            mastered,
            profile_names,
        )
        if found:
            # 书与点来自**同一个** candidate_index —— 这就是修掉错位的关键
            return source[candidate_index], found

    chosen = source[best_index]
    found = _first_unmet_in_book(chosen, mastered)
    return (chosen, found) if found else None


def next_unmet_point_for_books(
    books: list | None,
    profile: KnowledgeProfile,
    raw_books: list | None = None,
    topics=None,
) -> str | None:
    """多本书时：先挑「与画像最相关」的书，再取它按书序的第一个未掌握点。

    实测问题（T-010）：地图里一次导入 5~7 本书时，旧实现只把所有章节拉平后取第一个，
    等于按**字典序第一本**（C++ Primer）决定"下一个学什么"，会给 HTML 学到一半的学生
    安排「main 函数」。

    选书规则：
    1. 优先选「书里的知识点已被画像掌握最多」的那本（说明正在学它）；
    2. 平手时按地图里的原始顺序（文件顺序，不是字典序）；
    3. 一本书都没匹配上（画像与任何书都无交集）→ 退回第一本书。

    `raw_books`（T-021）：传**已按画像概念重写过的** books 时，选书用对齐后的名字，
    但返回给调用方的点应当取自**原始**地图（真名更有信息量）。两者顺序必须一致。

    注意：A-06 约束的是"点"而不是"书"——本函数只负责把"书序"落到一本合理的书上。

    T-042：实现已收敛到 pick_book_and_point（选书+选点一次完成），
    本函数只是取它的点——保证 prompt 与选点用的是**同一本书**。
    """
    picked = pick_book_and_point(books, profile, raw_books=raw_books, topics=topics)
    return picked[1] if picked else None


def _mapped_unmastered_in_book(book, raw, mastered: set[str], profile_names: set[str]) -> str | None:
    """在一本书里找「已映射到画像概念、但还没掌握」的点（跳过导读章与序言条目）。"""
    for chapter_index, chapter in enumerate(getattr(raw, "chapters", []) or []):
        if is_intro_chapter(getattr(chapter, "chapter", "")):
            continue
        aligned_chapter = (
            book.chapters[chapter_index] if chapter_index < len(getattr(book, "chapters", [])) else None
        )
        for position, point in enumerate(getattr(chapter, "points", []) or []):
            name = str(point).strip()
            if not name or is_front_matter(name) or name in mastered:
                continue
            mapped = (
                aligned_chapter.points[position]
                if aligned_chapter and position < len(aligned_chapter.points)
                else name
            )
            if mapped in mastered:
                continue
            if mapped in profile_names:
                return mapped
    return None


# 序言/导读类条目：书的开头常被蒸馏出这些，它们不是可出题的知识点（T-021 实测）
FRONT_MATTER_PATTERNS = (
    "适用读者",
    "学习原理",
    "元认知",
    "给读者的",
    "给读者的作业",
    "版权",
    "致谢",
    "前言",
    "序言",
    "导读",
    "本书怎么用",
    "阅读建议",
    "关于本书",
    "作者简介",
    "目录",
)


def is_front_matter(name: str) -> bool:
    """判断一个地图点是不是书的序言/导读（不该拿来出题）。"""
    text = str(name or "").strip()
    if not text:
        return True
    return any(pattern in text for pattern in FRONT_MATTER_PATTERNS)


# 导读章：书的第 1 章常是「Intro 导读」，里面的条目是讲怎么读书的，不是知识点
INTRO_CHAPTER_PATTERNS = ("导读", "前言", "序言", "introduction", "intro", "preface")


def is_intro_chapter(name: str) -> bool:
    """判断一章是不是书的导读/前言（不该从这里取知识点）。"""
    text = str(name or "").strip().lower()
    if not text:
        return False
    return any(pattern in text for pattern in INTRO_CHAPTER_PATTERNS)


def _first_unmet_in_book(book, mastered: set[str]) -> str | None:
    for chapter in getattr(book, "chapters", []) or []:
        if is_intro_chapter(getattr(chapter, "chapter", "")):
            continue
        for point in getattr(chapter, "points", []) or []:
            name = str(point).strip()
            if not name or name in mastered:
                continue
            if is_front_matter(name):
                continue
            return name
    return None


def _extract_json(raw: str):
    # 实测：真实模型常在 JSON 后继续写说明文字（"希望这个任务对你有帮助"）。
    # extract_json 用 raw_decode 只取第一个完整 JSON 值，围栏、寒暄、尾巴都能容忍。
    try:
        return extract_json(raw)
    except JSONExtractionError as exc:
        if exc.reason == "empty":
            raise PlannerError("LLM 返回了空内容") from None
        if exc.reason == "missing":
            raise PlannerError("LLM 输出里找不到 JSON，请重试") from None
        raise PlannerError(f"LLM 输出的 JSON 无法解析：{exc.detail}；请重试") from None


def parse_task(raw: str) -> GeneratedTask:
    payload = _extract_json(raw)
    if isinstance(payload, list):
        if not payload:
            raise PlannerError("LLM 没有给出任务")
        payload = payload[0]
    if isinstance(payload, dict) and "task" in payload and isinstance(payload["task"], dict):
        payload = payload["task"]
    if not isinstance(payload, dict):
        raise PlannerError("LLM 输出的任务不是 JSON 对象")

    goal = str(payload.get("goal") or "").strip()
    if not goal:
        raise PlannerError("任务缺少必填字段 goal")

    raw_skills = payload.get("skills")
    if raw_skills is None:
        raise PlannerError("任务缺少必填字段 skills")
    if isinstance(raw_skills, str):
        raw_skills = [raw_skills]
    skills = [str(item).strip() for item in raw_skills if str(item).strip()]

    acceptance = str(payload.get("acceptance") or "").strip()
    if not acceptance:
        raise PlannerError("任务缺少必填字段 acceptance（验收方式）")

    new_skill = payload.get("new_skill") or payload.get("newSkill")
    new_skill = str(new_skill).strip() if new_skill else None

    raw_steps = payload.get("steps") or []
    if isinstance(raw_steps, str):
        raw_steps = [raw_steps]
    steps = [str(item).strip() for item in raw_steps if str(item).strip()]

    return GeneratedTask(goal=goal, skills=skills, acceptance=acceptance, steps=steps, new_skill=new_skill)


_TOPIC_SUFFIX_RE = re.compile(r"（[^（）]*）\s*$")


def normalize_skill_name(name: str) -> str:
    """去掉「（主题）」后缀：模型常照抄 prompt 里带主题的写法，那不是越界。"""
    return _TOPIC_SUFFIX_RE.sub("", str(name or "")).strip()


def _align_skills(task: GeneratedTask, profile: KnowledgeProfile) -> GeneratedTask:
    """把能归一化匹配到画像的名字换回画像里的原名，保持输出整洁一致。"""
    by_normalized = {normalize_skill_name(p.name): p.name for p in profile.points}
    aligned = []
    for skill in task.skills:
        aligned.append(by_normalized.get(normalize_skill_name(skill), skill))
    new_skill = task.new_skill
    if new_skill:
        new_skill = by_normalized.get(normalize_skill_name(new_skill), new_skill)
    return GeneratedTask(
        goal=task.goal,
        skills=aligned,
        acceptance=task.acceptance,
        steps=list(task.steps),
        new_skill=new_skill,
    )


def out_of_scope_skills(task: GeneratedTask, profile: KnowledgeProfile) -> list[str]:
    """返回 skill 里既不在画像、又没被标成新点的知识点（名称做归一化后比较）。"""
    known = {p.name for p in profile.points}
    known_normalized = {normalize_skill_name(name) for name in known}
    new_normalized = normalize_skill_name(task.new_skill) if task.new_skill else None
    violations: list[str] = []
    for skill in task.skills:
        normalized = normalize_skill_name(skill)
        if normalized in known_normalized or normalized == new_normalized:
            continue
        violations.append(skill)
    return violations


def generate_task(
    profile: KnowledgeProfile,
    *,
    completer,
    syllabus: dict | None = None,
    attempts: int = 2,
    assignments: list | None = None,
    books: list | None = None,
    raw_books: list | None = None,
    recent_goals: Sequence[str] | None = None,
    given_idents: set | None = None,
    topics=None,
    weaknesses: Sequence[str] | None = None,
    tasks_path=None,
    stale_days: int = DEFAULT_STALE_DAYS,
) -> GeneratedTask:
    """生成一个任务；越界会带提示重试一次，仍不符则抛 PlannerError。

    T-020：先按画像匹配题库（`assignments`），命中就直接以该经典实验为骨架出题，
    **不调用 LLM**；没有合适条目才回退到 LLM 现编。

    `books`（BookMap 列表，T-010）：给 A-06 用。多本书时先挑「与画像最相关的书」，
    再取那本书按书序的下一个未掌握点；`syllabus`（单本 dict）仍保留兼容。

    `topics`（T-029）：只在这些主题里出题。传入后**知识池与越界校验都用裁剪后的画像**——
    这样 LLM 硬塞被排除主题的点会被现有越界机制拦下，不用另写一套校验。
    """
    # T-035：出满 N 道新题后，这一道强制出复习题（走保底模板，不调 LLM——
    # 复习题本来就该是"重做一遍旧东西"，不需要模型再编一个新场景）。
    if tasks_path and review_due(tasks_path, profile=profile, stale_days=stale_days):
        stale = pick_review_point(profile, stale_days=stale_days)
        if stale:
            return render_review_task(stale)

    scoped = filter_profile_by_topics(profile, topics)
    mastered = [p for p in scoped.points if p.level in MASTERED_LEVELS]
    if len(mastered) < MIN_POINTS:
        # 实测：真实画像可能整份都是「存疑」（笔记只有主题、没有解释和代码）。
        # 「存疑」不得当作已掌握，否则任务会直接用还没学会的东西，违反 A-03。
        if len(profile.points) < MIN_POINTS:
            raise PlannerError(
                f"画像里只有 {len(profile.points)} 个知识点，少于 {MIN_POINTS} 个，先多记几篇笔记再出题"
            )
        raise PlannerError(
            f"画像里已掌握（{'/'.join(MASTERED_LEVELS)}）的知识点只有 {len(mastered)} 个，少于 {MIN_POINTS} 个，"
            "不足以出题：请先把「存疑」的知识点补学后确认状态，或再记几篇有解释/示例的笔记"
        )

    # T-042：**选书/选点只算一次**，然后同时用于「prompt 里的地图」和「A-06 校验」。
    # 曾经是：prompt 塞 books_map[0]（C++ Primer 全章节），校验却按"最相关的书"（HTML），
    # 于是 LLM 看到的地图跟它被要求遵守的点对不上。
    picked_book = None
    focus_point = None
    if books:
        picked = pick_book_and_point(books, scoped, raw_books=raw_books, topics=topics)
        if picked is not None:
            picked_book, focus_point = picked

    if assignments:
        # 延迟导入：planner 不反向依赖 assignments 模块的加载逻辑
        from .assignments import assignment_to_task, pick_assignment

        picked = pick_assignment(assignments, scoped, already_given=given_idents)
        if picked is not None:
            candidate = assignment_to_task(picked, profile)
            # A-06：有地图时，任务的新点必须是地图里按书序的下一个未掌握点。
            # 题库条目自带 new_skill，可能与地图要求不一致 —— 那种情况下不能直接采用，
            # 必须回退 LLM 出题（LLM 路径下面会校验并重试）。
            # T-042：与 prompt 用**同一个**选择（见下面 picked_book/focus_point）
            expected_new = focus_point or (
                next_unmet_point_for_books(books, scoped, raw_books=raw_books, topics=topics)
                if books
                else next_unmet_point(syllabus, scoped)
            )
            if not (candidate.new_skill and expected_new and candidate.new_skill != expected_new):
                return candidate

    violations: list[str] | None = None
    last_error: Exception | None = None

    for _ in range(max(1, attempts)):
        messages = build_next_messages(
            scoped,
            syllabus=syllabus,
            violations=violations,
            recent_goals=recent_goals,
            weaknesses=weaknesses,
            book=picked_book,
            focus_point=focus_point,
        )
        try:
            raw = completer.complete(messages)
        except LLMError as exc:
            raise PlannerError(f"LLM 调用失败：{exc}") from None
        except Exception as exc:
            raise PlannerError(f"LLM 调用失败：{type(exc).__name__}") from None

        try:
            task = parse_task(raw)
        except PlannerError as exc:
            last_error = exc
            violations = None
            continue

        # T-029：越界校验必须对着**裁剪后的**画像，否则 LLM 塞一个被排除主题的点
        # 会被判成"画像里有、合法"，过滤就形同虚设。
        task = _align_skills(task, scoped)
        violations = out_of_scope_skills(task, scoped)
        if violations:
            last_error = PlannerError(
                "出题越界：声明的知识点不在画像里，也没有标成新知识点：" + "、".join(violations)
            )
            continue

        expected_new = (
            next_unmet_point_for_books(books, scoped, raw_books=raw_books, topics=topics)
            if books
            else next_unmet_point(syllabus, scoped)
        )
        if (syllabus or books) and expected_new and task.new_skill and task.new_skill != expected_new:
            # 有地图且地图里还有未掌握点：新点必须是那个点
            last_error = PlannerError(
                f"新知识点「{task.new_skill}」不是地图中按书序的下一个未掌握点（应为「{expected_new}」）"
            )
            violations = [task.new_skill]
            continue

        return task

    detail = str(last_error) if last_error else "原因未知"
    raise PlannerError(
        f"{detail}（已重试，仍未通过画像/地图约束；可先补充笔记或调整地图）"
    ) from None


_GIVEN_IDENT_RE = re.compile(r"[（(]\s*(?P<ident>[A-Za-z]+-\d+)\s")


def read_given_idents(tasks_path) -> set[str]:
    """从 tasks.md 里读出**已经出过**的题库条目编号（T-023 L-02）。

    留档里出处行形如：`**题目出处**：哈佛 CS50（A-01 个人名片页） ｜ 来自题库`。
    """
    text = read_text_or_none(tasks_path) or ""
    return {match.group("ident") for match in _GIVEN_IDENT_RE.finditer(text)}


def read_latest_task_points(tasks_path) -> list[str]:
    """取 tasks.md 里**最近一次任务**涉及的知识点（用到的 + 新点）。

    T-024 M-01：看板「回写」按钮的下拉候选就来自这里——按最近任务回写最顺手。
    """
    text = read_text_or_none(tasks_path) or ""
    blocks = re.split(r"^##\s+\d{4}-\d{2}-\d{2}", text, flags=re.M)
    if len(blocks) < 2:
        return []
    latest = blocks[-1]
    points: list[str] = []
    for label in ("用到的知识点", "新知识点"):
        value = _field(latest, label)
        if not value:
            continue
        value = re.sub(r"（[^（）]*）", "", value)          # 去掉「（本次唯一的新点）」
        for item in re.split(r"[、,，]", value):
            name = item.strip()
            if name and name not in points:
                points.append(name)
    return points


def read_recent_goals(tasks_path, limit: int = 5) -> list[str]:
    """从 tasks.md 里读出最近几个任务目标，喂给出题 prompt 避免重复。"""
    text = read_text_or_none(tasks_path) or ""
    goals = re.findall(r"^\*\*目标\*\*[：:]\s*(?P<goal>.+?)\s*$", text, re.M)
    return [goal.strip() for goal in goals if goal.strip()][-max(1, limit):]


@dataclass(frozen=True)
class TaskRecord:
    """tasks.md 里的一个任务块（T-027 任务卡片用）。"""

    when: str
    goal: str
    skills: list[str] = field(default_factory=list)
    new_skill: str | None = None
    acceptance: str = ""
    source: str | None = None
    steps: list[str] = field(default_factory=list)
    raw: str = ""
    reviews: list["ReviewRecord"] = field(default_factory=list)
    # 文件内出现次序（T-030）：时间戳相同时用它保持"后写入的更靠上"
    order: int = 0


_RECORD_SPLIT_RE = re.compile(r"^##\s+(?P<when>\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2})?)\s*$", re.M)


def read_task_records(path) -> list[TaskRecord]:
    """把 tasks.md 解析成结构化任务块（供看板渲染卡片）。

    只认「## <时间戳>」分隔的块；解析不出的字段留空，不抛异常（页面要能打开）。
    """
    text = read_text_or_none(path) or ""
    marks = list(_RECORD_SPLIT_RE.finditer(text))
    records: list[TaskRecord] = []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        block = text[mark.end():end].strip()
        records.append(_parse_record(mark.group("when").strip(), block, index))
    return records


def _field(block: str, label: str) -> str:
    """取任务块里「**标签**：值」那一行的值（没有就空串）。任务记录与点评留档共用。"""
    match = re.search(rf"^\*\*{re.escape(label)}\*\*[：:]\s*(?P<value>.+?)\s*$", block, re.M)
    return match.group("value").strip() if match else ""


def _parse_record(when: str, block: str, index: int = 0) -> TaskRecord:
    goal = _field(block, "目标")
    skills_raw = _field(block, "用到的知识点")
    skills = [item.strip() for item in re.split(r"[、,，]", skills_raw) if item.strip()]
    # 只剥掉标注性后缀（「（本次唯一的新点）」），**不能**把名称里本来就有的括号一起剥了
    # （实测：「超链接 a 标签（href/target）」曾被剥成「超链接 a 标签」）
    new_skill = re.sub(r"（\s*本次[^（）]*）\s*$", "", _field(block, "新知识点")).strip() or None
    acceptance = _field(block, "验收方式")
    source = _field(block, "题目出处") or None

    steps: list[str] = []
    for line in block.splitlines():
        step = re.match(r"^\s*\d+[.、]\s*(?P<text>.+?)\s*$", line)
        if step:
            steps.append(step.group("text"))

    return TaskRecord(
        when=when,
        goal=goal,
        reviews=parse_reviews(block),
        skills=skills,
        new_skill=new_skill,
        acceptance=acceptance,
        source=source,
        steps=steps,
        raw=block,
        order=index,
    )


@dataclass(frozen=True)
class ReviewRecord:
    """一次作业提交的留档（T-028）。"""

    submitted_at: str
    feedback: str
    suggestion: str = ""
    truncated: bool = False
    # T-031：把当时提交的代码也读回来——DSH 接力要把这份代码带进上下文。
    # 之前 append_review 写进了 <details> 块，但 parse_reviews 没读回来，
    # 于是"接力上下文里没有学生的代码"。
    code: str = ""


REVIEW_HEADING = "### 作业点评"


# 提交的代码写在 details 块里的一对围栏之间（append_review 的格式）
_CODE_FENCE_RE = re.compile(
    r"<details><summary>本次提交的代码</summary>\s*\n```[^\n]*\n(?P<code>.*?)\n```",
    re.S,
)


def parse_reviews(block: str) -> list[ReviewRecord]:
    """从任务块里读回历次点评（可能多份，按出现顺序）。"""
    records: list[ReviewRecord] = []
    parts = block.split(REVIEW_HEADING)
    for part in parts[1:]:
        submitted = _field(part, "提交时间")
        feedback = _field(part, "评价")
        suggestion = _field(part, "建议")
        if not (submitted or feedback):
            continue
        records.append(
            ReviewRecord(
                submitted_at=submitted,
                feedback=feedback,
                suggestion=suggestion,
                truncated="已截断" in part,
                code=(match.group("code") if (match := _CODE_FENCE_RE.search(part)) else ""),
            )
        )
    return records


def _locate_task_block(target: Path, stamp: str) -> tuple[str, int, int]:
    """读 tasks.md 并定位时间戳为 stamp 的任务块，返回 (全文, 块起点, 块终点)。

    append_review / delete_task_record 共用：**只动目标块**的前提是先准确找到它。
    """
    if not target.is_file():
        raise PlannerError(f"找不到任务记录：{target}")
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise PlannerError(f"读取任务记录失败：{target}（{type(exc).__name__}）") from None

    marks = list(_RECORD_SPLIT_RE.finditer(text))
    for position, mark in enumerate(marks):
        if mark.group("when").strip() == stamp:
            end = marks[position + 1].start() if position + 1 < len(marks) else len(text)
            return text, mark.start(), end
    raise PlannerError(f"任务记录里没有时间戳为「{stamp}」的块")


def _write_task_file(target: Path, text: str) -> Path:
    try:
        return write_text_atomic(target, text)
    except OSError as exc:
        raise PlannerError(f"写入任务记录失败：{target}（{type(exc).__name__}）") from None


def append_review(
    path,
    when: str,
    *,
    code: str,
    feedback: str,
    suggestion: str = "",
    truncated: bool = False,
    submitted_at: str | None = None,
) -> Path:
    """把一次点评追加到对应任务块末尾（**只动目标块**），临时文件 + 替换落盘。

    代码上限由本函数把关（T-028）：超过 8000 字符就截断并在留档里注明，
    调用方不用自己裁——省得某条调用路径忘了裁而把整份代码塞进 tasks.md。
    """
    from .review import MAX_CODE_CHARS, prepare_code

    code, was_truncated = prepare_code(code)
    truncated = bool(truncated) or was_truncated

    target = Path(path)
    stamp = str(when or "").strip()
    if not stamp:
        raise PlannerError("提交作业需要给出任务时间戳")
    text, _start, end = _locate_task_block(target, stamp)
    moment = submitted_at or datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "",
        REVIEW_HEADING,
        "",
        f"**提交时间**：{moment}",
        f"**评价**：{feedback.strip() or '(空)'}",
    ]
    if suggestion.strip():
        lines.append(f"**建议**：{suggestion.strip()}")
    if truncated:
        lines.append(f"**说明**：代码超过 {MAX_CODE_CHARS} 字符，已截断后点评（已截断）")
    if code:
        lines.extend(["", "<details><summary>本次提交的代码</summary>", "", "```", code.rstrip(), "```", "", "</details>"])
    addition = "\n".join(lines) + "\n"

    return _write_task_file(target, text[:end].rstrip() + "\n" + addition + text[end:])


def delete_task_record(path, when: str) -> Path:
    """按时间戳删掉一个任务块（**只动目标块**），临时文件 + 替换落盘。"""
    target = Path(path)
    stamp = str(when or "").strip()
    if not stamp:
        raise PlannerError("删除任务需要给出时间戳")
    text, start, end = _locate_task_block(target, stamp)
    return _write_task_file(target, (text[:start] + text[end:]).rstrip() + "\n")


def render_task(task: GeneratedTask) -> str:
    lines = ["## 下一步任务", "", f"**目标**：{task.goal}", ""]
    # T-035：复习标记要落进留档——计数靠它判断"上一道是复习题"，
    # 不写的话复习节奏永远重置不了（会连着出复习题）。
    if getattr(task, "is_review", False):
        lines.append(REVIEW_FLAG)
        lines.append("")
    if task.source:
        label = f"（{task.source_label}）" if task.source_label else ""
        lines.append(f"**题目出处**：{task.source}{label} ｜ 来自题库 [[assignments]]")
        lines.append("")
    lines.append("**用到的知识点**：" + "、".join(task.skills or ["（未声明）"]))
    if task.new_skill:
        lines.append(f"**新知识点**：{task.new_skill}（本次唯一的新点）")
    if task.steps:
        lines.append("")
        lines.append("**实现要点**：")
        lines += [f"{index}. {step}" for index, step in enumerate(task.steps, start=1)]
    lines += ["", f"**验收方式**：{task.acceptance}"]
    return "\n".join(lines)


def append_task_record(path: Path | str, task: GeneratedTask, *, when: datetime | None = None) -> Path:
    """把任务追加到 tasks.md 留档（追加式，不覆盖历史）。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    stamp = (when or datetime.now()).strftime("%Y-%m-%d %H:%M")
    block = f"\n## {stamp}\n\n{render_task(task)}\n"
    try:
        with target.open("a", encoding="utf-8") as handle:
            if target.stat().st_size == 0:
                handle.write("# 任务记录\n")
            handle.write(block)
    except OSError as exc:
        raise PlannerError(f"写入任务记录失败：{target}（{type(exc).__name__}）") from None
    return target