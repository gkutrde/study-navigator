"""T-044 周报复盘：把窗口内的学习活动汇总成 markdown。

数据来源（实测仓库只有 1 次提交、大量工作区改动未提交，所以两条都覆盖）：
- **文件状态**：profile/ 里的 last_touched / 任务时间戳 / 薄弱点时间戳 —— 这些才是"真的发生了什么"；
- **git**：窗口内的提交数，只作为补充（没有就如实说"本周无提交"）。
"""
from __future__ import annotations

import datetime
import os
from pathlib import Path
import subprocess
import sys

from .planner import is_review_record, read_task_records
from .profile import LEVELS, KnowledgeProfile
from .silent import silent_kwargs
from .weaknesses import load_weaknesses


DEFAULT_DAYS = 7


def _today(today=None) -> datetime.date:
    return today or datetime.date.today()


def _parse_date(text: str):
    raw = str(text or "").strip()
    if not raw:
        return None
    for chunk in (raw[:10], raw[:16]):
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M"):
            try:
                return datetime.datetime.strptime(chunk, fmt).date()
            except ValueError:
                continue
    return None


def _in_window(stamp: str, since: datetime.date, until: datetime.date) -> bool:
    day = _parse_date(stamp)
    return day is not None and since <= day <= until


def collect_stats(profile_dir: Path | str, *, days: int = DEFAULT_DAYS, today=None, repo_root=None) -> dict:
    """把窗口内的活动收集成结构化统计。"""
    directory = Path(profile_dir)
    now = _today(today)
    since = now - datetime.timedelta(days=max(0, int(days)) - 1)

    profile = KnowledgeProfile.load(directory / "knowledge.md")
    mastered = ("学过", "做过", "输出")

    moved: list = []
    for point in profile.points:
        if _in_window(getattr(point, "last_touched", ""), since, now):
            moved.append(point)

    tasks = read_task_records(directory / "tasks.md")
    fresh_tasks = [t for t in tasks if _in_window(t.when, since, now)]
    review_tasks = [t for t in fresh_tasks if is_review_record(t)]

    # 复习完成率：窗口内的复习题里，有多少道的知识点已经被做掉（做成"做过/输出"）
    done_names = {
        p.name for p in profile.points if p.level in ("做过", "输出")
    }
    completed_reviews = 0
    for task in review_tasks:
        skills = getattr(task, "skills", None) or []
        if any(str(name).strip() in done_names for name in skills):
            completed_reviews += 1

    weaknesses = load_weaknesses(directory)
    fresh_weaknesses = [
        w for w in weaknesses if _in_window(w.last_seen or w.first_seen, since, now)
    ]

    commits = _commits_in_window(repo_root or directory.parent, since, now)

    return {
        "days": int(days),
        "since": since,
        "until": now,
        "moved": moved,
        "moved_by_level": {
            level: len([p for p in moved if p.level == level]) for level in LEVELS
        },
        "tasks": fresh_tasks,
        "review_tasks": review_tasks,
        "completed_reviews": completed_reviews,
        "weaknesses": weaknesses,
        "fresh_weaknesses": fresh_weaknesses,
        "commits": commits,
        "mastered_total": len([p for p in profile.points if p.level in mastered]),
        "points_total": len(profile.points),
    }


def _commits_in_window(repo_root, since: datetime.date, until: datetime.date) -> list:
    """窗口内的 git 提交主题；不是 git 仓库 / 没装 git 就返回空。"""
    root = Path(repo_root)
    if not (root / ".git").exists():
        return []
    command = [
        "git",
        "log",
        "--since=" + since.isoformat(),
        "--until=" + (until + datetime.timedelta(days=1)).isoformat(),
        "--pretty=format:%h %ad %s",
        "--date=short",
    ]
    try:
        done = subprocess.run(
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            **silent_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if done.returncode != 0:
        return []
    return [line.strip() for line in (done.stdout or "").splitlines() if line.strip()]


def build_report(
    profile_dir: Path | str,
    *,
    days: int = DEFAULT_DAYS,
    today=None,
    repo_root=None,
) -> str:
    """生成 markdown 周报（四个板块 + 全图摘要）。"""
    stats = collect_stats(profile_dir, days=days, today=today, repo_root=repo_root)
    lines: list[str] = []

    lines.append("# 学习周报复盘 · 最近 " + str(stats["days"]) + " 天")
    lines.append("")
    lines.append(
        "窗口：**" + stats["since"].isoformat() + " → " + stats["until"].isoformat() + "**"
        " ｜ 画像共 " + str(stats["points_total"]) + " 个点（已掌握 " + str(stats["mastered_total"]) + "）"
    )
    lines.append("")

    # --- 状态迁移 ---
    lines.append("## 状态迁移")
    lines.append("")
    moved = stats["moved"]
    if not moved:
        lines.append("- 窗口内没有知识点被碰到。")
    else:
        lines.append("- 共 **" + str(len(moved)) + "** 个知识点在窗口内被推进（moved=" + str(len(moved)) + "）：")
        by_level = stats["moved_by_level"]
        detail = "、".join(
            str(level) + " " + str(count) for level, count in by_level.items() if count
        )
        lines.append("  - 现在状态分布：" + (detail or "无"))
        lines.append("")
        lines.append("| 知识点 | 现在状态 | 最近 |")
        lines.append("| --- | --- | --- |")
        for point in moved:
            lines.append(
                "| " + point.name + " | " + point.level + " | "
                + (getattr(point, "last_touched", "") or "-") + " |"
            )
    lines.append("")

    # --- 任务完成 ---
    lines.append("## 任务完成")
    lines.append("")
    tasks = stats["tasks"]
    lines.append("- 窗口内新增 **" + str(len(tasks)) + "** 道任务。")
    if tasks:
        lines.append("")
        for task in tasks:
            flag = "【复习】" if is_review_record(task) else ""
            lines.append("- " + task.when + "　" + flag + str(task.goal))
    lines.append("")
    commits = stats["commits"]
    if commits:
        lines.append("- git 提交 " + str(len(commits)) + " 次：")
        lines.extend("  - " + item for item in commits)
    else:
        lines.append("- git：窗口内**没有提交**（活动都还在工作区里）。")
    lines.append("")

    # --- 薄弱点 ---
    lines.append("## 薄弱点")
    lines.append("")
    weaknesses = stats["weaknesses"]
    if not weaknesses:
        lines.append("- 错题本是空的——没有反复犯的问题。")
    else:
        lines.append("- 当前清单 " + str(len(weaknesses)) + " 条：")
        for item in weaknesses:
            stamp = ("（最近 " + item.last_seen + "）") if item.last_seen else ""
            lines.append("- " + item.text + stamp)
        fresh = stats["fresh_weaknesses"]
        lines.append("")
        lines.append("- 窗口内新增/复现：" + str(len(fresh)) + " 条")
    lines.append("")

    # --- 复习完成率 ---
    lines.append("## 复习完成率")
    lines.append("")
    review_tasks = stats["review_tasks"]
    completed = stats["completed_reviews"]
    if not review_tasks:
        lines.append("- 窗口内没有复习题。")
    else:
        rate = int(round(completed * 100 / len(review_tasks)))
        lines.append(
            "- 复习题 **" + str(completed) + "/" + str(len(review_tasks)) + "**"
            + " 已完成（完成率 " + str(rate) + "%）。"
        )
    lines.append("")

    return chr(10).join(lines).rstrip() + chr(10)
