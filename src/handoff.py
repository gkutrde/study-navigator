"""T-031：DSH 接力上下文（F-14）。

学生提交完作业后点「在 DSH 中继续」——本模块负责把**这一个任务**的全部上下文
组装成一份 markdown，落到 profile/handoff/<任务id>.md，供人在 DSH 里接着深聊。

一任务一文件（任务 id = 任务时间戳的文件名安全形式），**重复点击覆盖同一份文件**。

文件固定五段（顺序不可变）：

1. 任务卡：目标 / 验收方式 / 用到的知识点（含新知识点）
2. 本次提交的代码（复用 review.prepare_code 截断，并注明是否截断）
3. 画像相关点：各知识点在画像里的状态与证据（画像里没有的明确注明）
4. 书籍出处与章节：知识点在知识地图里属于哪本书哪一章（找不到的明确注明）
5. 提问引导：至少两条可直接复制的提问

设计要点（与项目其它模块一致）：

- **缺数据给占位说明，绝不静默留空**：没提交代码、没画像、没地图都要说清楚；
- **查不到不是崩溃**：地图/画像里没有该点只注明「找不到」；
- 任务时间戳缺失 → 明确报错（中文），不生成文件；
- 落盘走「临时文件 + 替换」，失败清理 .tmp，不留半个文件。
"""

from __future__ import annotations

from pathlib import Path
import re

from .planner import TaskRecord
from .profile import KnowledgeProfile, normalize_point_name
from .review import MAX_CODE_CHARS, prepare_code
from .syllabus import BookMap

__all__ = [
    "DEFAULT_HANDOFF_DIRNAME",
    "SECTION_HEADINGS",
    "HandoffError",
    "build_handoff_markdown",
    "build_questions",
    "handoff_dir",
    "handoff_path",
    "task_file_id",
    "write_handoff",
]


class HandoffError(RuntimeError):
    """接力上下文组装/落盘失败（多半是没给任务时间戳，或写文件出错）。"""


DEFAULT_HANDOFF_DIRNAME = "handoff"

# 五段标题：顺序即文件里的顺序（测试与看板都依赖它）
SECTION_TASK_CARD = "## 一、任务卡"
SECTION_CODE = "## 二、本次提交的代码"
SECTION_PROFILE = "## 三、画像相关点"
SECTION_BOOKS = "## 四、书籍出处与章节"
SECTION_QUESTIONS = "## 五、提问引导"
SECTION_HEADINGS = (
    SECTION_TASK_CARD,
    SECTION_CODE,
    SECTION_PROFILE,
    SECTION_BOOKS,
    SECTION_QUESTIONS,
)

# 「已掌握」口径与 planner/review 一致：存疑不算已掌握
MASTERED_LEVELS = ("学过", "做过", "输出")

NO_TASK_RECORD = "（找不到任务记录：任务卡内容缺失，请在看板上从任务卡片重新进入）"
NO_TIMESTAMP = "（没有任务时间戳）"

_TICK = chr(96)          # 反引号：写成 chr(96) 是为了不让文档里的代码围栏干扰源码可读性
_FENCE_RE = re.compile(_TICK + r"+")

# 时间戳 → 文件名安全形式：冒号直接去掉（10:30 → 1030），其余危险字符压成 "-"
_UNSAFE_ID_RE = re.compile(r"[^\w\u4e00-\u9fff.-]+")


# --- 文件名与路径 ---------------------------------------------------------


def task_file_id(when: str) -> str:
    """把任务时间戳转成文件名安全形式：2026-09-27 10:30 → 2026-09-27-1030。

    时间戳为空 → HandoffError（不知道是哪一个任务，就不能生成文件）。
    """
    text = str(when or "").strip()
    if not text:
        raise HandoffError("组装接力上下文需要给出任务时间戳：没有时间戳就分不清是哪一个任务")
    safe = _UNSAFE_ID_RE.sub("-", text.replace(":", "").replace("：", "")).strip("-._")
    if not safe:
        raise HandoffError(
            f"任务时间戳「{text}」转不出文件名安全形式，请用形如 2026-09-27 10:30 的写法"
        )
    return safe


def handoff_dir(profile_dir: Path | str) -> Path:
    """接力上下文目录：<profile_dir>/handoff。"""
    return Path(profile_dir) / DEFAULT_HANDOFF_DIRNAME


def handoff_path(profile_dir: Path | str, when: str) -> Path:
    """某个任务对应的上下文文件路径（同一个任务永远是同一个路径 → 覆盖）。"""
    return handoff_dir(profile_dir) / f"{task_file_id(when)}.md"


# --- 小工具 ---------------------------------------------------------------


def _clean(value) -> str:
    return str(value or "").strip()


def _task_points(record: TaskRecord | None) -> list[str]:
    """任务卡里用到的知识点（含新知识点），去重保序。"""
    if record is None:
        return []
    names = list(record.skills or [])
    if record.new_skill:
        names.append(record.new_skill)
    points: list[str] = []
    for name in names:
        text = _clean(name)
        if text and text not in points:
            points.append(text)
    return points


def _find_profile_point(profile: KnowledgeProfile | None, name: str):
    """在画像里找同名知识点：先精确匹配，再按「去掉（主题）后缀」归一化匹配。"""
    if profile is None:
        return None
    text = _clean(name)
    normalized = normalize_point_name(text)
    fallback = None
    for point in getattr(profile, "points", []) or []:
        if point.name == text:
            return point
        if fallback is None and normalize_point_name(point.name) == normalized:
            fallback = point
    return fallback


def _find_map_location(point: str, books: list[BookMap] | None):
    """在地图里定位知识点（复用 explain 的查找逻辑），返回带 book/chapter 的对象。"""
    if not books:
        return None
    text = _clean(point)
    if not text:
        return None
    try:
        from .explain import _find_point_in_books
    except ImportError:  # pragma: no cover - 理论上不会发生
        return None
    try:
        return _find_point_in_books(text, books)
    except Exception:  # 地图格式再怪也不该让接力文件生成失败
        return None


def _fenced_code(code: str) -> str:
    """用比代码里最长反引号更长的围栏包住代码，避免代码里的围栏提前收尾。"""
    longest = max((len(match.group(0)) for match in _FENCE_RE.finditer(code)), default=0)
    fence = _TICK * max(3, longest + 1)
    return f"{fence}\n{code.rstrip()}\n{fence}"


# --- 第 1 段：任务卡 ------------------------------------------------------


def _render_task_card(record: TaskRecord | None, stamp: str) -> list[str]:
    lines = [SECTION_TASK_CARD, ""]
    if record is None:
        lines += [NO_TASK_RECORD, ""]
    lines.append(f"- **时间戳**：{stamp or NO_TIMESTAMP}")
    goal = _clean(record.goal) if record is not None else ""
    lines.append(f"- **目标**：{goal or '（任务卡里没记目标）'}")
    acceptance = _clean(record.acceptance) if record is not None else ""
    lines.append(f"- **验收方式**：{acceptance or '（任务卡里没记验收方式）'}")

    skills = "、".join(record.skills or []) if record is not None else ""
    lines.append(f"- **用到的知识点**：{_clean(skills) or '（任务卡里没记用到的知识点）'}")
    new_skill = _clean(record.new_skill) if record is not None else ""
    if new_skill:
        lines.append(f"- **新知识点**：{new_skill}（本次唯一的新点）")
    else:
        lines.append("- **新知识点**：（本次没有新知识点）")

    steps = [_clean(step) for step in (record.steps or [])] if record is not None else []
    steps = [step for step in steps if step]
    if steps:
        lines.append("")
        lines.append("**实现要点**：")
        lines += [f"{index}. {step}" for index, step in enumerate(steps, start=1)]
    lines.append("")
    return lines


# --- 第 2 段：提交的代码 --------------------------------------------------


def _render_code(code: str) -> list[str]:
    raw = str(code or "")
    prepared, truncated = prepare_code(raw)
    lines = [SECTION_CODE, ""]
    if not raw.strip():
        lines += ["（本次没有提交代码：请让 DSH 先看你贴的代码，或回到看板补交后再来）", ""]
        return lines
    if truncated:
        lines.append(
            f"**代码已截断**：原文 {len(raw)} 字符，超过上限 {MAX_CODE_CHARS} 字符，"
            f"本文件只保留前 {len(prepared)} 字符（完整原文见 profile/tasks.md 的作业留档）。"
        )
    else:
        lines.append(f"**代码未截断**：全文 {len(raw)} 字符（上限 {MAX_CODE_CHARS} 字符）。")
    lines += ["", _fenced_code(prepared), ""]
    return lines


# --- 第 3 段：画像相关点 --------------------------------------------------


def _render_profile_section(record: TaskRecord | None, profile: KnowledgeProfile | None) -> list[str]:
    lines = [SECTION_PROFILE, ""]
    points = _task_points(record)
    if profile is None:
        lines += ["（没有读取到画像文件：以下知识点一律按「画像里没有」处理）", ""]
    if not points:
        lines += ["（任务卡里没有记录知识点，无法对照画像）", ""]
        return lines

    for name in points:
        point = _find_profile_point(profile, name)
        if point is None:
            lines.append(f"- 「{name}」：**画像里没有这个知识点**（属于画像外的新点，先补基础再做）")
            continue
        topic = _clean(point.topic)
        topic_note = f"（{topic}）" if topic else ""
        evidence = _clean(point.evidence) or "（画像里没记证据）"
        lines.append(f"- 「{name}」{topic_note}：**{_clean(point.level)}** —— 证据：{evidence}")
    lines.append("")
    return lines


# --- 第 4 段：书籍出处与章节 ----------------------------------------------


def _render_books_section(record: TaskRecord | None, books: list[BookMap] | None) -> list[str]:
    lines = [SECTION_BOOKS, ""]
    points = _task_points(record)
    if not books:
        lines += ["（没有知识地图：先跑 import 导入对应书籍、再 align 对齐，这里才能给出章节）", ""]
    if not points:
        lines += ["（任务卡里没有记录知识点，无法定位出处）", ""]
        return lines

    for name in points:
        located = _find_map_location(name, books)
        if located is None:
            lines.append(
                f"- 「{name}」：（知识地图里找不到这个知识点：先 import 导入对应书籍、再 align 对齐，"
                f"或直接问 DSH 该看哪本书）"
            )
            continue
        lines.append(f"- 「{name}」：《{_clean(located.book)}》· {_clean(located.chapter)}")
    lines.append("")
    return lines


# --- 第 5 段：提问引导 ----------------------------------------------------


def build_questions(
    record: TaskRecord | None = None,
    profile: KnowledgeProfile | None = None,
) -> list[str]:
    """生成可直接复制的提问（**至少两条**，前两条固定）。"""
    questions = [
        "我的代码哪里不足？请对照上面的验收方式逐条指出不达标的地方，并给出最小修改建议。",
        "我该看书的哪部分？请给出书名 + 章节，并说明这一章里重点看什么、跳过什么。",
    ]
    if record is not None and record.new_skill:
        questions.append(
            f"这次的新知识点「{_clean(record.new_skill)}」请先用最小可运行的例子讲清，再给我一道同类小练习。"
        )
    for name in _task_points(record):
        point = _find_profile_point(profile, name)
        if point is None or _clean(point.level) not in MASTERED_LEVELS:
            state = "画像里还没有" if point is None else f"画像里的状态是「{_clean(point.level)}」"
            questions.append(
                f"知识点「{name}」{state}，请从它解决什么问题讲起，给一个能跑的最小例子，"
                f"再指出我最容易踩的坑。"
            )
            break
    return questions


def _render_questions(record: TaskRecord | None, profile: KnowledgeProfile | None) -> list[str]:
    lines = [SECTION_QUESTIONS, ""]
    lines += ["把下面几句直接复制到 DSH 的对话框里（至少前两条永远适用）：", ""]
    lines += [f"{index}. {question}" for index, question in enumerate(build_questions(record, profile), start=1)]
    lines.append("")
    return lines


# --- 组装与落盘 -----------------------------------------------------------


def build_handoff_markdown(
    record: TaskRecord | None = None,
    *,
    when: str = "",
    code: str = "",
    profile: KnowledgeProfile | None = None,
    books: list[BookMap] | None = None,
) -> str:
    """组装接力上下文 markdown（五段固定顺序）。

    record 为 None、画像/地图查不到、代码为空……都只写**明确的占位说明**，
    绝不静默留空、也不抛异常——这是给人看的上下文文件，宁可啰嗦也不能缺信息。
    时间戳取 when，缺省回落到 record.when。
    """
    stamp = _clean(when) or (_clean(record.when) if record is not None else "")
    lines = [
        "# DSH 接力上下文",
        "",
        "> 由看板「在 DSH 中继续」生成：一个任务一个文件，重复点击会覆盖更新。",
        "> 用法：在 DSH 里新建会话（工作区选本项目目录），把本文件内容贴进去；或直接照抄第五段的提问。",
        "",
    ]
    lines += _render_task_card(record, stamp)
    lines += _render_code(code)
    lines += _render_profile_section(record, profile)
    lines += _render_books_section(record, books)
    lines += _render_questions(record, profile)
    return "\n".join(lines).rstrip("\n") + "\n"


def write_handoff(
    profile_dir: Path | str,
    *,
    when: str = "",
    record: TaskRecord | None = None,
    code: str = "",
    profile: KnowledgeProfile | None = None,
    books: list[BookMap] | None = None,
) -> Path:
    """组装并落盘到 <profile_dir>/handoff/<任务id>.md，返回文件路径。

    同一任务重复调用 → 同一个文件被**覆盖更新**（一任务一文件）。
    时间戳未知 → HandoffError；写失败 → HandoffError 且清理 .tmp。
    """
    stamp = _clean(when) or (_clean(record.when) if record is not None else "")
    path = handoff_path(profile_dir, stamp)
    text = build_handoff_markdown(record, when=stamp, code=code, profile=profile, books=books)

    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise HandoffError(f"写入接力上下文失败：{path}（{type(exc).__name__}）") from None
    return path
