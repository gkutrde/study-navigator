"""T-004：知识画像文件的结构、解析与合并。

画像 = 客户「我会什么」的本地 markdown 档案（[[模块-知识画像]]）。本模块负责：

- 解析既有画像（服务端不认识的行一律忽略，绝不猜）；
- 渲染成稳定、可读、可 git 管理的 markdown；
- 合并新提炼的知识点：同名去重、状态只升不降（存疑例外，可下降提醒复核）、证据追加；
- 落盘走「临时文件 + 替换」，失败不动旧文件。

不做（边界）：不调用 LLM、不生成任务、不做知识地图（syllabus）。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
import re
import time
from typing import Iterable, Sequence

from .distill import KnowledgePoint
from .fileio import write_text_atomic

# 四态与 [[模块-知识画像]] 一致；rank 越大表示掌握程度越高。
# 「输出」= 能用自己的话把知识讲清楚（费曼复述），是 T-019 新增的最高态。
LEVEL_RANK = {"存疑": 0, "学过": 1, "做过": 2, "输出": 3}
LEVELS = ("学过", "做过", "输出", "存疑")
# 「已掌握」的唯一口径：除「存疑」之外的三态（出题、接力上下文、周报都用它）。
# 以前 planner 自己写了一份 ("学过", "做过")，漏了 T-019 加的最高态「输出」——
# 结果复述过的点在出题 prompt 里被当成「仍存疑」，甚至会被选成「下一个新点」。
MASTERED_LEVELS = ("学过", "做过", "输出")

DEFAULT_TOPIC = "未分类"
DEFAULT_HEADER = "# 知识画像"
PROFILE_FRONTMATTER = "---\ntitle: 知识画像\ntags:\n  - profile\n---\n"

_POINT_RE = re.compile(r"^\s*-\s*\[(?P<level>[^\]]+)\]\s*(?P<rest>.+?)\s*$")
_TOPIC_SUFFIX_RE = re.compile(r"（(?P<topic>[^（）]+)）\s*$")
# T-035：行尾的「— 最近：YYYY-MM-DD」段（旧的画像文件没有这段，必须能缺省）
_LAST_TOUCHED_RE = re.compile(r"\s*[—-]\s*最近：(?P<when>\d{4}-\d{2}-\d{2})\s*$")


class ProfileError(RuntimeError):
    """画像读写失败：结构不合法、合并冲突或落盘失败。旧文件保持不变。"""


class PointNotFoundError(ProfileError):
    """画像里没有这个知识点（与「同名歧义」区分开：done / 改状态遇到它会新增条目）。"""


@dataclass
class KnowledgeProfile:
    points: list[KnowledgePoint] = field(default_factory=list)
    header: str = DEFAULT_HEADER

    # --- 读写 ---

    @classmethod
    def load(cls, path: Path | str) -> "KnowledgeProfile":
        target = Path(path)
        if not target.is_file():
            return cls()
        try:
            return parse_profile(target.read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            raise ProfileError(f"读取画像失败：{target}（{type(exc).__name__}）") from None

    # --- 查询 ---

    def find(self, name: str, topic: str = "") -> KnowledgePoint | None:
        for point in self.points:
            if point.name == name and (not topic or (point.topic or DEFAULT_TOPIC) == topic):
                return point
        return None

    def counts(self) -> dict[str, int]:
        counts = {level: 0 for level in LEVELS}
        for point in self.points:
            counts[point.level] = counts.get(point.level, 0) + 1
        return counts


def parse_profile(markdown: str) -> KnowledgeProfile:
    """解析画像 markdown。只认「- [状态] 名称 — 证据：...」这种行，其余一律忽略。"""
    text = markdown or ""
    header = DEFAULT_HEADER
    topic = ""
    points: list[KnowledgePoint] = []

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("# ") and not line.startswith("## "):
            header = line.strip()
            continue
        if line.startswith("## "):
            name = line[3:].strip()
            topic = "" if name in {"统计", "说明"} else name
            continue
        match = _POINT_RE.match(line)
        if not match:
            continue
        level = match.group("level").strip()
        if level not in LEVEL_RANK:
            continue  # 不是我们写的行，不猜
        rest = match.group("rest").strip()
        last_touched = ""
        touched_match = _LAST_TOUCHED_RE.search(rest)
        if touched_match:
            last_touched = touched_match.group("when")
            rest = rest[: touched_match.start()].rstrip()
        name, evidence = _split_point(rest, topic)
        if not name:
            continue
        points.append(
            KnowledgePoint(
                name=name,
                level=level,
                evidence=evidence,
                topic="" if topic == DEFAULT_TOPIC else topic,
                last_touched=last_touched,
            )
        )

    return KnowledgeProfile(points=points, header=header)


def _split_point(rest: str, topic: str = "") -> tuple[str, str]:
    """把「列表（Python 基础） — 证据：xxx」拆成 (名称, 证据)。

    顺序很重要：先切掉「证据：」之后的内容，再去掉名称末尾的主题括号。

    **T-010 实测修复**：只有当末尾括号**确实等于本节主题**时才剥掉它。
    旧实现无条件剥掉末尾括号，于是「列表（ul/ol/li）」（未分类）会被读成「列表」——
    与另一条知识点撞名，画像每次读写都静默失真，题库标签也再也匹配不上。
    """
    if "证据：" in rest:
        head, _, evidence = rest.partition("证据：")
    else:
        head, evidence = rest, ""
    head = head.rstrip(" —-").strip()
    topic_match = _TOPIC_SUFFIX_RE.search(head)
    if topic_match:
        suffix = topic_match.group("topic").strip()
        # topic 为空或等于「未分类」时，只接受括号内容恰好是「未分类」的写法
        expected = topic or DEFAULT_TOPIC
        if suffix == expected:
            head = head[: topic_match.start()].strip()
    return head, evidence.strip()


def render_profile(profile: KnowledgeProfile) -> str:
    """渲染成 markdown：frontmatter + 统计表 + 按主题分组的知识点。"""
    points = _normalize_points(profile.points)
    counts = {level: 0 for level in LEVELS}
    for point in points:
        counts[point.level] += 1

    lines = [PROFILE_FRONTMATTER.rstrip("\n"), "", profile.header or DEFAULT_HEADER, "", "## 统计", ""]
    lines.append("| 状态 | 数量 |")
    lines.append("| --- | --- |")
    for level in LEVELS:
        lines.append(f"| {level} | {counts[level]} |")
    lines.append("")

    grouped: dict[str, list[KnowledgePoint]] = {}
    for point in points:
        grouped.setdefault(point.topic or DEFAULT_TOPIC, []).append(point)

    for topic in sorted(grouped):
        lines.append(f"## {topic}")
        lines.append("")
        for point in grouped[topic]:
            suffix = f"（{point.topic}）" if point.topic else ""
            touched = f" — 最近：{point.last_touched}" if getattr(point, "last_touched", "") else ""
            lines.append(f"- [{point.level}] {point.name}{suffix} — 证据：{point.evidence}{touched}")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def touch_points(profile: KnowledgeProfile, names, *, when: str = "") -> KnowledgeProfile:
    """把给定知识点的 last_touched 刷成 when（默认今天）。不认识的名字忽略。"""
    wanted = {str(name).strip() for name in (names or []) if str(name).strip()}
    if not wanted:
        return KnowledgeProfile(points=list(profile.points), header=profile.header)
    moment = when or time.strftime("%Y-%m-%d")
    updated = [
        replace(point, last_touched=moment) if point.name in wanted else point
        for point in profile.points
    ]
    return KnowledgeProfile(points=updated, header=profile.header)


def merge_points(
    profile: KnowledgeProfile,
    incoming: Sequence[KnowledgePoint],
) -> KnowledgeProfile:
    """把新提炼的知识点合并进画像。"""
    existing = list(_normalize_points(profile.points))
    fresh = _normalize_points(incoming)
    # 知识点身份按「名称」判定：实测 LLM 对同一知识点的 topic 会漂移
    # （Markdown 一次「工具使用」、一次「工具」），若把 topic 也算进身份，
    # 每跑一次提炼，画像就会多出重复条目。
    index: dict[str, int] = {}
    for position, point in enumerate(existing):
        index.setdefault(point.name, position)

    for point in fresh:
        position = index.get(point.name)
        if position is None:
            index[point.name] = len(existing)
            existing.append(point)
            continue
        current = existing[position]
        existing[position] = replace(
            current,
            level=_merge_level(current.level, point.level),
            evidence=_merge_evidence(current.evidence, point.evidence),
            topic=current.topic or point.topic,
            # T-035：提炼不该抹掉"最近碰过"的时间戳（否则复习队列每次提炼都重置）
            last_touched=current.last_touched or point.last_touched,
        )

    return KnowledgeProfile(points=existing, header=profile.header)


def _normalize_points(points: Iterable[KnowledgePoint] | None) -> list[KnowledgePoint]:
    if points is None:
        raise ProfileError("知识点列表缺失或不是列表")
    result: list[KnowledgePoint] = []
    for item in points:
        if not isinstance(item, KnowledgePoint):
            raise ProfileError(f"知识点类型不合法：{type(item).__name__}")
        if item.level not in LEVEL_RANK:
            raise ProfileError(
                f"知识点「{item.name}」的 level 不合法：{item.level}；只能是 {'/'.join(LEVELS)}"
            )
        if not str(item.name).strip():
            raise ProfileError("知识点缺少名称")
        result.append(item)
    return result


def _merge_level(current: str, incoming: str) -> str:
    """只升不降；但 incoming 为「存疑」时允许下降（信息不足，提醒客户复核）。"""
    if incoming == "存疑":
        return "存疑"
    if LEVEL_RANK.get(current, 0) >= LEVEL_RANK.get(incoming, 0):
        return current
    return incoming


def _merge_evidence(current: str, incoming: str) -> str:
    current = (current or "").strip()
    incoming = (incoming or "").strip()
    if not incoming:
        return current
    if not current:
        return incoming
    if incoming in current:
        return current
    return f"{current}；{incoming}"


def normalize_point_name(name: str) -> str:
    """去掉结尾的「（主题）」：客户/模型常照抄画像里的显示形式。"""
    return _TOPIC_SUFFIX_RE.sub("", str(name or "")).strip()


def _candidate_label(point: KnowledgePoint) -> str:
    topic = point.topic or DEFAULT_TOPIC
    return f"{point.name}（{topic}）"


def _resolve_point_index(points: list[KnowledgePoint], name: str) -> int:
    """定位知识点下标。

    T-014 修复的歧义问题：归一化后可能撞车（实测真实画像里同时存在
    「列表（ul/ol/li）」与「列表」，两者归一化都是「列表」）。
    匹配顺序：

    1. **精确同名**优先（输入就等于条目全名）；
    2. 其次按归一化名匹配，但**必须唯一**；
    3. 匹配到多条 → 报歧义并列出候选（带主题），让调用方带完整名称重试；
    4. 完全匹配不到 → 报错并列出全部候选。

    绝不「模糊命中后报成功」。
    """
    wanted = normalize_point_name(name)
    if not wanted:
        raise ProfileError("知识点名称不能为空")

    exact = [index for index, point in enumerate(points) if point.name == name]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        labels = "、".join(_candidate_label(points[i]) for i in exact)
        raise ProfileError(f"「{name}」在画像里有 {len(exact)} 条同名记录，请先手工合并：{labels}")

    fuzzy = [index for index, point in enumerate(points) if normalize_point_name(point.name) == wanted]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if len(fuzzy) > 1:
        labels = "、".join(_candidate_label(points[i]) for i in fuzzy)
        raise ProfileError(
            f"「{name}」无法唯一确定，画像里有多条候选（相同名称、不同主题）：{labels}。"
            f"请改用完整名称（带主题）重试"
        )

    everything = "、".join(_candidate_label(point) for point in points) or "（画像为空）"
    raise PointNotFoundError(f"画像里没有知识点「{wanted}」；可选：{everything}")


def resolve_point_name(profile: KnowledgeProfile, name: str) -> str | None:
    """把用户给的名字（可能是缩略名，如「列表」）解析成画像里的完整点名（「列表（ul/ol/li）」）。

    解析规则与 done / 改状态完全一致（精确优先、归一化唯一）；不存在或有歧义时返回 None。
    """
    try:
        return profile.points[_resolve_point_index(list(profile.points), name)].name
    except ProfileError:
        return None


def _with_recital(evidence: str, spoken: str) -> str:
    """有费曼复述时把「复述：…」并进证据（T-019）。"""
    return _merge_evidence(evidence, f"复述：{spoken}") if spoken else evidence


def mark_done(
    profile: KnowledgeProfile,
    name: str,
    product_path: str,
    recite: str = "",
) -> KnowledgeProfile:
    """把某知识点标记为「做过」并记录产出路径（T-006 / A-04）。

    T-019：带上 `recite`（费曼复述：用自己的话讲清这个知识点）时，状态升到最高态
    「输出」，复述文字追加进证据。复述为空（或只有空白）时行为与原来完全一致。
    不改动其他知识点。
    """
    wanted = normalize_point_name(name)
    if not wanted:
        raise ProfileError("知识点名称不能为空")

    product = str(product_path or "").strip()
    if not product:
        raise ProfileError(f"知识点「{wanted}」缺少产出路径：请给出产出文件或目录")

    spoken = str(recite or "").strip()
    # 复述本身就是输出能力的证据，所以带复述时升到「输出」态
    level = "输出" if spoken else "做过"
    produced = f"产出：{product}"

    points = list(_normalize_points(profile.points))
    try:
        target_index = _resolve_point_index(points, name)
    except PointNotFoundError:
        # T-023 L-01：画像里没有这个点就**新增条目**，不要报错。
        # 否则核心闭环会断裂——出题/讲解里遇到的新知识点，做完根本没法回写。
        # （同名歧义等其它 ProfileError 仍然抛出：那是真需要人工判断的。）
        points.append(
            KnowledgePoint(name=str(name).strip(), level=level, evidence=_with_recital(produced, spoken))
        )
        return KnowledgeProfile(points=points, header=profile.header)

    current = points[target_index]
    # done 只升不降：它记录的是"又做了一次产出"，不是"我要改状态"。
    # 实测回归：已是「输出」的知识点再跑一次普通 done，会被错误降回「做过」。
    # 想显式下调请用 set_level（手工选择优先）。
    if LEVEL_RANK.get(current.level, 0) > LEVEL_RANK.get(level, 0):
        level = current.level

    # replace 保留其余字段——T-035：回写不能把「最近碰过」抹掉（复习队列靠它判断超期）
    points[target_index] = replace(
        current,
        level=level,
        evidence=_with_recital(_merge_evidence(current.evidence, produced), spoken),
    )
    return KnowledgeProfile(points=points, header=profile.header)


def set_level(
    profile: KnowledgeProfile,
    name: str,
    level: str,
    note: str = "",
) -> KnowledgeProfile:
    """手工把某知识点改成指定状态（T-013 看板交互）。

    - level 必须来自白名单 LEVELS，不允许任意字符串；
    - note 非空时追加进证据（如产出路径或复核说明）；
    - 只改动目标知识点；找不到则报错并列出候选。
    """
    wanted = normalize_point_name(name)
    if not wanted:
        raise ProfileError("知识点名称不能为空")

    if level not in LEVELS:
        raise ProfileError(
            f"状态不合法：{level or '（空）'}；只能是 {'/'.join(LEVELS)}"
        )

    points = list(_normalize_points(profile.points))
    try:
        target_index = _resolve_point_index(points, name)
    except PointNotFoundError:
        # T-023 L-01：看板手工改状态时也可以**新增**一个画像里没有的知识点
        # （与 done 一致；否则"我学了但笔记里没记"的点永远进不了画像）
        points.append(
            KnowledgePoint(
                name=str(name).strip(),
                level=level,
                evidence=note.strip() or "手工新增（来自看板）",
            )
        )
        return KnowledgeProfile(points=points, header=profile.header)

    current = points[target_index]
    evidence = _merge_evidence(current.evidence, note.strip()) if note else current.evidence
    # replace 保留 last_touched：手工改状态以前会把它抹掉（与 T-035 修过的 mark_done 同一类问题）
    points[target_index] = replace(current, level=level, evidence=evidence)
    return KnowledgeProfile(points=points, header=profile.header)


def write_profile_atomic(path: Path | str, profile: KnowledgeProfile) -> Path:
    """先渲染、再写临时文件、最后替换；任何一步失败都保留旧画像。"""
    target = Path(path)
    try:
        content = render_profile(profile)
    except ProfileError:
        raise
    except Exception as exc:
        raise ProfileError(f"渲染画像失败：{type(exc).__name__}") from None

    try:
        return write_text_atomic(target, content)
    except OSError as exc:
        raise ProfileError(f"写入画像失败：{target}（{type(exc).__name__}）") from None
