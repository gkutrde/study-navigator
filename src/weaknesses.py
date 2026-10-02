"""T-035 错题本：把 LLM 点评里抽出的「问题点」累积成一份可注入 prompt 的清单。

存 profile/weaknesses.md（人可读）。去重、保序、单次最多 3 条、条目截断；
被后续任务做掉时可以移除（done 碰到对应知识点）。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import time

from .fileio import read_text_or_none, write_text_atomic


class WeaknessError(Exception):
    """错题本读写失败。"""


MAX_PER_SUBMISSION = 3
MAX_ITEM_CHARS = 40
FILENAME = "weaknesses.md"
HEADER = "# 薄弱点清单"

_ITEM_RE = re.compile(r"^\s*-\s*(?P<body>.+?)\s*$")
# 行尾的时间戳段：「 — 首次：A，最近：B」，两段都可缺省、顺序不限（render_weaknesses 写的就是这个格式）
_STAMPS_RE = re.compile(r"\s*[—-]\s*(?P<stamps>(?:(?:首次|最近)：\d{4}-\d{2}-\d{2}[，,\s]*)+)$")
_STAMP_RE = re.compile(r"(?P<kind>首次|最近)：(?P<day>\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True)
class Weakness:
    text: str
    first_seen: str = ""
    last_seen: str = ""


def weaknesses_path(profile_dir: Path | str) -> Path:
    return Path(profile_dir) / FILENAME


def _clean(items) -> list:
    """清洗：去空白、截断、过长/过短/重复的丢掉。"""
    result: list = []
    for item in items or []:
        text = re.sub(r"\s+", " ", str(item or "")).strip(" \t-—、,，。.;；")
        if not text:
            continue
        if len(text) > MAX_ITEM_CHARS:
            text = text[:MAX_ITEM_CHARS].rstrip()
        if text not in result:
            result.append(text)
    return result


def load_weaknesses(profile_dir: Path | str) -> list:
    """读清单；文件不存在或读不了就返回空列表（绝不因为错题本坏了挡住出题）。

    时间戳段按整段解析：以前先按「首次」切掉行尾、再找「最近」，而写出的格式是
    「首次：A，最近：B」——「最近」跟着「首次」一起被切掉，last_seen 每读一次就丢一次，
    下次保存时也就从文件里消失了（周报的「窗口内复现」因此只能看首次时间）。
    """
    text = read_text_or_none(weaknesses_path(profile_dir))
    if text is None:
        return []

    items: list = []
    seen: set = set()
    for line in text.splitlines():
        match = _ITEM_RE.match(line)
        if not match:
            continue
        body = match.group("body").strip()
        first = last = ""
        stamps = _STAMPS_RE.search(body)
        if stamps:
            for stamp in _STAMP_RE.finditer(stamps.group("stamps")):
                if stamp.group("kind") == "首次":
                    first = stamp.group("day")
                else:
                    last = stamp.group("day")
            body = body[: stamps.start()].rstrip()
        body = re.sub(r"\s+", " ", body).strip()
        if not body or body in seen:
            continue
        seen.add(body)
        items.append(Weakness(text=body, first_seen=first, last_seen=last))
    return items


def render_weaknesses(items) -> str:
    lines = [HEADER, "", "> 由作业点评自动累积；被后续任务做掉（done 涉及该知识点）会自动移除。", ""]
    for item in items:
        stamps = []
        if item.first_seen:
            stamps.append("首次：" + item.first_seen)
        if item.last_seen:
            stamps.append("最近：" + item.last_seen)
        tail = (" — " + "，".join(stamps)) if stamps else ""
        lines.append("- " + item.text + tail)
    lines.append("")
    return "\n".join(lines)


def save_weaknesses(profile_dir: Path | str, items) -> Path:
    try:
        return write_text_atomic(weaknesses_path(profile_dir), render_weaknesses(items))
    except OSError as exc:
        raise WeaknessError("写薄弱点清单失败：" + type(exc).__name__) from None


def merge_weaknesses(profile_dir: Path | str, problems, *, when: str = "") -> list:
    """把一次点评的「问题点」并进清单（本次最多 3 条），返回合并后的清单。"""
    fresh = _clean(problems)[:MAX_PER_SUBMISSION]
    moment = when or time.strftime("%Y-%m-%d")
    existing = load_weaknesses(profile_dir)
    known = {item.text: item for item in existing}
    for text in fresh:
        current = known.get(text)
        if current is None:
            item = Weakness(text=text, first_seen=moment, last_seen=moment)
            existing.append(item)
            known[text] = item
        else:
            index = existing.index(current)
            updated = Weakness(
                text=current.text,
                first_seen=current.first_seen or moment,
                last_seen=moment,
            )
            existing[index] = updated
            known[text] = updated
    save_weaknesses(profile_dir, existing)
    return existing


def remove_weaknesses(profile_dir: Path | str, targets) -> list:
    """移除给定条目，返回真正被移除的文本列表。"""
    wanted = {re.sub(r"\s+", " ", str(t or "")).strip() for t in (targets or [])}
    wanted.discard("")
    if not wanted:
        return []
    existing = load_weaknesses(profile_dir)
    removed = [item.text for item in existing if item.text in wanted]
    if removed:
        # 全删光也照常写（写出只有标题的空清单），与普通保存走同一条原子写路径
        save_weaknesses(profile_dir, [item for item in existing if item.text not in wanted])
    return removed


def weaknesses_text(profile_dir: Path | str) -> list:
    """只要文本，便于注入 prompt 与页面展示。"""
    return [item.text for item in load_weaknesses(profile_dir)]