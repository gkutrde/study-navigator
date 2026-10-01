"""T-044 失败测试：周报复盘（report 命令 + 看板最近 7 天卡）。

数据来源（实测只有 1 次提交，工作区大量未提交，所以两条都覆盖）：
- **文件状态**：profile/ 的 last_touched / 任务时间戳 / 薄弱点首次最近时间；
- **git**：窗口内的提交数（有就报，没有就说明"本周无提交"）。

输出：markdown 周报；看板首页加「最近 7 天」摘要卡。
"""
from __future__ import annotations

import datetime
import pathlib

import pytest

from src.profile import KnowledgeProfile, KnowledgePoint, write_profile_atomic
from src.weaknesses import merge_weaknesses


TODAY = datetime.date(2026, 9, 29)


def ago(days: int) -> str:
    return (TODAY - datetime.timedelta(days=days)).isoformat()


def make_profile(tmp_path, *, points, tasks_text="", weaknesses=()):
    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    write_profile_atomic(directory / "knowledge.md", KnowledgeProfile(points=points))
    (directory / "tasks.md").write_text(
        tasks_text or "# 任务记录\n", encoding="utf-8"
    )
    if weaknesses:
        merge_weaknesses(directory, list(weaknesses), when=TODAY.isoformat())
    return directory


def task_block(when: str, goal: str, *, review: bool = False, skills: str = "列表（ul/ol/li）") -> str:
    flag = "**复习**：是\n\n" if review else ""
    return (
        f"## {when}\n\n{flag}**目标**：{goal}\n\n"
        f"**用到的知识点**：{skills}\n\n**验收方式**：能看到列表\n\n"
    )


def tasks_file(*blocks: str) -> str:
    return "# 任务记录\n\n" + "".join(blocks)


# ---------- 报告的四个板块 ----------


def test_report_has_four_sections(tmp_path):
    from src.report import build_report

    directory = make_profile(tmp_path, points=[
        KnowledgePoint("列表（ul/ol/li）", "学过", "e", last_touched=ago(2)),
        KnowledgePoint("表格（table/tr/th/td）", "做过", "e", last_touched=ago(1)),
        KnowledgePoint("CSS 选择器", "存疑", "e"),
    ])

    text = build_report(directory, days=7, today=TODAY)

    for heading in ("状态迁移", "任务完成", "薄弱点", "复习完成率"):
        assert heading in text, "周报缺板块：" + heading


def test_report_counts_state_migrations_in_window(tmp_path):
    """窗口内被碰过（last_touched 在窗口内）的点，就是发生过迁移的。"""
    from src.report import build_report

    directory = make_profile(tmp_path, points=[
        KnowledgePoint("窗口内学过", "学过", "e", last_touched=ago(2)),
        KnowledgePoint("窗口内做过", "做过", "e", last_touched=ago(1)),
        KnowledgePoint("窗口外", "学过", "e", last_touched=ago(30)),
        KnowledgePoint("从没碰过", "存疑", "e"),
    ])

    text = build_report(directory, days=7, today=TODAY)

    assert "moved=2" in text, "窗口内应当统计到 2 个点的迁移"
    assert "窗口内做过" in text, "迁移表里要列出具体点"


def test_report_counts_tasks_in_window(tmp_path):
    from src.report import build_report

    directory = make_profile(
        tmp_path,
        points=[KnowledgePoint("列表（ul/ol/li）", "学过", "e", last_touched=ago(1))],
        tasks_text=tasks_file(
            task_block(ago(1) + " 10:00", "窗口内任务 A"),
            task_block(ago(2) + " 10:00", "窗口内任务 B"),
            task_block(ago(30) + " 10:00", "窗口外任务 C"),
        ),
    )

    text = build_report(directory, days=7, today=TODAY)

    assert "窗口内任务 A" in text
    assert "窗口内任务 B" in text
    assert "窗口外任务 C" not in text


def test_report_counts_review_completion(tmp_path):
    """复习完成率 = 窗口内复习题里，有多少道已经做掉（done 过）。"""
    from src.report import build_report

    directory = make_profile(
        tmp_path,
        points=[KnowledgePoint("列表（ul/ol/li）", "做过", "e", last_touched=ago(1))],
        tasks_text=tasks_file(
            task_block(
                ago(3) + " 10:00",
                "复习：列表（ul/ol/li）",
                review=True,
                skills="列表（ul/ol/li）",
            ),
            task_block(
                ago(2) + " 10:00",
                "复习：表格（table/tr/th/td）",
                review=True,
                skills="表格（table/tr/th/td）",
            ),
            task_block(ago(1) + " 10:00", "新题", review=False),
        ),
    )

    text = build_report(directory, days=7, today=TODAY)

    assert "复习完成率" in text
    assert "1/2" in text, "两道复习题、只有一道对应点被做掉"
    assert "50%" in text


def test_report_lists_weaknesses(tmp_path):
    from src.report import build_report

    directory = make_profile(
        tmp_path,
        points=[KnowledgePoint("列表（ul/ol/li）", "学过", "e", last_touched=ago(1))],
        weaknesses=["缩进混乱", "忘记空格"],
    )

    text = build_report(directory, days=7, today=TODAY)

    assert "缩进混乱" in text
    assert "忘记空格" in text


def test_report_window_is_configurable(tmp_path):
    from src.report import build_report

    directory = make_profile(tmp_path, points=[
        KnowledgePoint("三天前碰过", "学过", "e", last_touched=ago(3)),
    ])

    narrow = build_report(directory, days=1, today=TODAY)
    wide = build_report(directory, days=7, today=TODAY)

    assert "三天前碰过" not in narrow, "1 天窗口不该包含 3 天前的"
    assert "三天前碰过" in wide


def test_report_empty_profile_does_not_crash(tmp_path):
    from src.report import build_report

    directory = make_profile(tmp_path, points=[])

    text = build_report(directory, days=7, today=TODAY)

    assert "周报" in text or "复盘" in text


def test_report_mentions_git_when_no_commits(tmp_path):
    """工作区没提交时要如实说明，而不是假装有活动。"""
    from src.report import build_report

    directory = make_profile(tmp_path, points=[
        KnowledgePoint("列表（ul/ol/li）", "学过", "e", last_touched=ago(1)),
    ])

    text = build_report(directory, days=7, today=TODAY, repo_root=tmp_path)

    assert "提交" in text, "要提一句 git 提交情况"


# ---------- CLI ----------


def test_cli_report_command_exists():
    from src.cli import KNOWN_COMMANDS

    assert "report" in KNOWN_COMMANDS


def test_cli_report_days_flag(tmp_path, monkeypatch, capsys):
    from src import cli

    seen = {}
    monkeypatch.setattr(cli, "_run_report", lambda rest, **kw: seen.update(kw) or 0)
    directory = make_profile(tmp_path, points=[
        KnowledgePoint("列表（ul/ul/li）", "学过", "e", last_touched=ago(1)),
    ])

    code = cli.main(["report", "--days", "14"], env_path=tmp_path / ".env",
                    profile_path=directory / "knowledge.md")
    capsys.readouterr()

    assert code == 0
    assert seen, "应当调用 _run_report"


def test_cli_report_prints_markdown(tmp_path, capsys):
    from src import cli

    directory = make_profile(tmp_path, points=[
        KnowledgePoint("列表（ul/ol/li）", "学过", "e", last_touched=ago(1)),
    ])

    code = cli.main(["report"], env_path=tmp_path / ".env",
                    profile_path=directory / "knowledge.md")
    out = capsys.readouterr().out

    assert code == 0
    assert "状态迁移" in out
    assert "复习完成率" in out


def test_cli_report_rejects_bad_days(tmp_path, capsys):
    from src import cli

    code = cli.main(["report", "--days", "abc"], env_path=tmp_path / ".env")
    err = capsys.readouterr().err

    assert code == 2
    assert "days" in err


def test_cli_usage_mentions_report():
    from src.cli import USAGE

    assert "report" in USAGE


# ---------- 看板「最近 7 天」卡 ----------


def test_dashboard_home_has_recent_card(tmp_path):
    from src.dashboard import TaskBoard

    directory = make_profile(tmp_path, points=[
        KnowledgePoint("列表（ul/ol/li）", "学过", "e", last_touched=datetime.date.today().isoformat()),
    ])

    page = TaskBoard(directory).pages()[""]

    assert "最近 7 天" in page
    assert "recent-card" in page


def test_dashboard_recent_card_hidden_when_nothing_recent(tmp_path):
    """最近 7 天什么都没发生时，卡片给一句"本周没有活动"而不是空表。"""
    from src.dashboard import TaskBoard

    directory = make_profile(tmp_path, points=[
        KnowledgePoint("列表（ul/ol/li）", "学过", "e", last_touched=ago(60)),
    ])

    page = TaskBoard(directory).pages()[""]

    assert "最近 7 天" in page
    assert "没有" in page or "暂无" in page
