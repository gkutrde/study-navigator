"""T-035 失败测试（一）：画像层的 last_touched 与薄弱点清单。

F-15 两件事的数据源都是既有文件：
- 复习题：画像每个点要记 last_touched（distill / done / review 时刷新），
  好让 next 挑出「学过但 N 天没碰」的点；
- 错题本：profile/weaknesses.md，去重合并、可移除、可读回。
"""

from __future__ import annotations

import pathlib

import pytest

from src.profile import KnowledgeProfile, KnowledgePoint, write_profile_atomic


def test_point_has_last_touched_field():
    point = KnowledgePoint("列表", "学过", "e")

    assert hasattr(point, "last_touched")
    assert point.last_touched == ""


def test_render_and_parse_roundtrip_keeps_last_touched(tmp_path):
    profile = KnowledgeProfile(points=[
        KnowledgePoint("列表", "学过", "e", last_touched="2026-09-01"),
        KnowledgePoint("字典", "存疑", "e", last_touched="2026-09-20"),
    ])
    path = tmp_path / "knowledge.md"
    write_profile_atomic(path, profile)

    back = KnowledgeProfile.load(path)

    assert back.points[0].last_touched == "2026-09-01"
    assert back.points[1].last_touched == "2026-09-20"


def test_render_puts_last_touched_in_markdown(tmp_path):
    profile = KnowledgeProfile(points=[KnowledgePoint("列表", "学过", "e", last_touched="2026-09-01")])
    path = tmp_path / "knowledge.md"
    write_profile_atomic(path, profile)

    text = path.read_text(encoding="utf-8")

    assert "2026-09-01" in text
    assert "last_touched" in text or "最近" in text


def test_merge_points_preserves_last_touched():
    from src.profile import merge_points

    old = KnowledgeProfile(points=[KnowledgePoint("列表", "学过", "e", last_touched="2026-09-01")])
    new = KnowledgeProfile(points=[KnowledgePoint("列表", "学过", "e2")])

    merged = merge_points(old, new.points)

    assert merged.points[0].last_touched == "2026-09-01", "提炼不应该抹掉时间戳"


def test_touch_points_sets_today(tmp_path):
    from src.profile import touch_points

    profile = KnowledgeProfile(points=[
        KnowledgePoint("列表", "学过", "e"),
        KnowledgePoint("字典", "学过", "e"),
    ])

    updated = touch_points(profile, ["列表"], when="2026-09-29")

    assert updated.points[0].last_touched == "2026-09-29"
    assert updated.points[1].last_touched == "", "没碰的点不该被刷新"


def test_touch_points_ignores_unknown_names():
    from src.profile import touch_points

    profile = KnowledgeProfile(points=[KnowledgePoint("列表", "学过", "e")])

    updated = touch_points(profile, ["不存在的点"], when="2026-09-29")

    assert updated.points[0].last_touched == ""


# ---------- 薄弱点清单 ----------


def test_weaknesses_empty_when_file_absent(tmp_path):
    from src.weaknesses import load_weaknesses, weaknesses_path

    directory = tmp_path / "profile"
    directory.mkdir(parents=True)

    assert load_weaknesses(directory) == []
    assert weaknesses_path(directory).name == "weaknesses.md"


def test_merge_weaknesses_dedupes_and_caps(tmp_path):
    from src.weaknesses import load_weaknesses, merge_weaknesses

    directory = tmp_path / "profile"
    directory.mkdir(parents=True)

    merge_weaknesses(directory, ["缩进混乱", "忘记空格"], when="2026-09-29")
    merge_weaknesses(directory, ["缩进混乱", "标点全角"], when="2026-09-29")

    items = load_weaknesses(directory)
    texts = [item.text for item in items]

    assert texts == ["缩进混乱", "忘记空格", "标点全角"], "去重且保序"


def test_merge_weaknesses_caps_three_per_submission(tmp_path):
    from src.weaknesses import merge_weaknesses

    directory = tmp_path / "profile"
    directory.mkdir(parents=True)

    merge_weaknesses(directory, ["a", "b", "c", "d", "e"], when="2026-09-29")

    assert len(load_weaknesses_after(directory)) == 3


def load_weaknesses_after(directory):
    from src.weaknesses import load_weaknesses

    return load_weaknesses(directory)


def test_remove_weakness(tmp_path):
    from src.weaknesses import load_weaknesses, merge_weaknesses, remove_weaknesses

    directory = tmp_path / "profile"
    directory.mkdir(parents=True)
    merge_weaknesses(directory, ["缩进混乱", "忘记空格"], when="2026-09-29")

    removed = remove_weaknesses(directory, ["缩进混乱"])

    assert removed == ["缩进混乱"]
    assert [w.text for w in load_weaknesses(directory)] == ["忘记空格"]


def test_weaknesses_file_is_human_readable(tmp_path):
    from src.weaknesses import merge_weaknesses, weaknesses_path

    directory = tmp_path / "profile"
    directory.mkdir(parents=True)
    merge_weaknesses(directory, ["忘记空格"], when="2026-09-29")

    text = weaknesses_path(directory).read_text(encoding="utf-8")

    assert "忘记空格" in text
    assert "2026-09-29" in text


def test_weaknesses_atomic_no_tmp(tmp_path):
    from src.weaknesses import merge_weaknesses

    directory = tmp_path / "profile"
    directory.mkdir(parents=True)
    merge_weaknesses(directory, ["x"], when="2026-09-29")

    assert not list(directory.glob("*.tmp"))


def test_weaknesses_rejects_blank_and_long(tmp_path):
    from src.weaknesses import merge_weaknesses, weaknesses_path

    directory = tmp_path / "profile"
    directory.mkdir(parents=True)
    merge_weaknesses(directory, ["  ", "a" * 200, "正常的一条"], when="2026-09-29")

    text = weaknesses_path(directory).read_text(encoding="utf-8")
    assert "正常的一条" in text
    assert "a" * 60 not in text, "过长的条目要被截到合理长度"


# ---------- LLM 解析问题点 ----------


def test_review_parses_problem_points_from_llm_reply():
    from src.review import parse_review

    raw = (
        "【评价】结构还行。\n"
        "【建议】补上头像。\n"
        "【问题点】缩进混乱、忘记空格\n"
    )

    feedback, suggestion, problems = parse_review(raw, with_problems=True)

    assert "结构还行" in feedback
    assert "补上头像" in suggestion
    assert problems == ["缩进混乱", "忘记空格"]


def test_review_without_problems_section_gives_empty_list():
    from src.review import parse_review

    feedback, suggestion, problems = parse_review("【评价】好\n【建议】改", with_problems=True)

    assert problems == []


def test_review_prompt_asks_for_problem_points():
    from src.review import build_review_messages

    messages = build_review_messages(goal="g", acceptance="a", code="c", with_problems=True)
    blob = str(messages)

    assert "问题点" in blob
    assert "3" in blob, "要明确最多 3 条"

# ---------- T-035 失败测试（二）：复习题节奏 + 薄弱点联动 ----------


def make_profile_dir(tmp_path, *, touched_days_ago=None):
    """造一个画像：列表=学过（可指定多久没碰），字典=存疑。"""
    import datetime

    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    when = ""
    if touched_days_ago is not None:
        day = datetime.date.today() - datetime.timedelta(days=touched_days_ago)
        when = day.isoformat()
    # 三个「学过」是为了满足出题的 MIN_POINTS=3（少了会先报"知识点不够"）
    profile = KnowledgeProfile(points=[
        KnowledgePoint("列表（ul/ol/li）", "学过", "e", topic="网页基础", last_touched=when),
        KnowledgePoint("表格（table/tr/th/td）", "存疑", "e", topic="网页基础"),
        KnowledgePoint("超链接 a 标签", "学过", "e", topic="网页基础", last_touched=when),
        KnowledgePoint("表单 input 标签", "学过", "e", topic="网页基础", last_touched=when),
    ])
    write_profile_atomic(directory / "knowledge.md", profile)
    return directory


# ---------- 复习题的节奏 ----------


def test_review_due_after_three_new_tasks(tmp_path):
    """出满 3 道新题后，第 4 道应该是复习题。"""
    from src.planner import review_due, count_new_tasks

    tasks = "# 任务记录\n\n"
    for index in range(3):
        tasks += f"## 2026-09-2{index} 10:00\n\n**目标**：新题 {index}\n\n**新知识点**：x\n\n**验收方式**：a\n\n"
    path = tmp_path / "tasks.md"
    path.write_text(tasks, encoding="utf-8")

    assert count_new_tasks(path) == 3
    assert review_due(path) is True


def test_review_not_due_before_three(tmp_path):
    from src.planner import review_due

    path = tmp_path / "tasks.md"
    path.write_text("# 任务记录\n\n## 2026-09-27 10:00\n\n**目标**：新题\n", encoding="utf-8")

    assert review_due(path) is False


def test_review_task_resets_the_counter(tmp_path):
    """出过复习题后，计数重新开始（不然会连着出复习）。"""
    from src.planner import count_new_tasks, review_due

    path = tmp_path / "tasks.md"
    body = ""
    for index in range(3):
        body += f"## 2026-09-2{index} 10:00\n\n**目标**：新题 {index}\n\n"
    body += "## 2026-09-26 10:00\n\n**目标**：复习：列表\n\n**复习**：是\n\n"
    path.write_text("# 任务记录\n\n" + body, encoding="utf-8")

    assert count_new_tasks(path) == 0
    assert review_due(path) is False


def test_pick_review_point_prefers_stale_studied(tmp_path):
    """复习点要从「学过且超期没碰」的里挑。"""
    from src.planner import pick_review_point

    directory = make_profile_dir(tmp_path, touched_days_ago=30)
    profile = KnowledgeProfile.load(directory / "knowledge.md")

    picked = pick_review_point(profile, stale_days=14)

    assert picked in {"列表（ul/ol/li）", "超链接 a 标签"}
    assert picked != "表格（table/tr/th/td）", "存疑的点不是复习候选"


def test_pick_review_point_skips_recently_touched(tmp_path):
    from src.planner import pick_review_point

    directory = make_profile_dir(tmp_path, touched_days_ago=1)
    profile = KnowledgeProfile.load(directory / "knowledge.md")

    assert pick_review_point(profile, stale_days=14) is None


def test_pick_review_point_treats_missing_timestamp_as_stale(tmp_path):
    """没有 last_touched 的老画像：当作超期（否则复习题永远挑不出来）。"""
    from src.planner import pick_review_point

    directory = make_profile_dir(tmp_path, touched_days_ago=None)
    profile = KnowledgeProfile.load(directory / "knowledge.md")

    assert pick_review_point(profile, stale_days=14) is not None


def test_stale_days_is_configurable(tmp_path):
    from src.planner import pick_review_point

    directory = make_profile_dir(tmp_path, touched_days_ago=5)
    profile = KnowledgeProfile.load(directory / "knowledge.md")

    assert pick_review_point(profile, stale_days=3) is not None, "5 天前碰过，按 3 天算就是超期"
    assert pick_review_point(profile, stale_days=30) is None, "按 30 天算还不算超期"


def test_generate_task_marks_review(tmp_path, monkeypatch):
    """复习题要在任务里标注出来（看板靠它画角标）。"""
    from src.planner import GeneratedTask, mark_review

    task = GeneratedTask(goal="复习：列表", skills=["列表"], acceptance="a", steps=["s"])

    marked = mark_review(task, "列表（ul/ol/li）")
    assert marked.is_review is True
    assert marked.goal.startswith("复习")


# ---------- 薄弱点注入与移除 ----------


def test_build_next_messages_includes_weaknesses():
    from src.planner import build_next_messages

    profile = KnowledgeProfile(points=[
        KnowledgePoint("列表", "学过", "e"),
        KnowledgePoint("字典", "学过", "e"),
        KnowledgePoint("循环", "学过", "e"),
    ])

    messages = build_next_messages(profile, weaknesses=["缩进混乱", "忘记空格"])
    blob = str(messages)

    assert "缩进混乱" in blob and "忘记空格" in blob
    assert "薄弱" in blob or "问题点" in blob


def test_build_next_messages_without_weaknesses_has_no_section():
    from src.planner import build_next_messages

    profile = KnowledgeProfile(points=[KnowledgePoint("列表", "学过", "e")])

    blob = str(build_next_messages(profile))
    assert "缩进混乱" not in blob


def test_done_removes_matching_weaknesses(tmp_path):
    """done 回写涉及的知识点，要把它相关的薄弱点从清单移除。"""
    from src import cli
    from src.weaknesses import load_weaknesses, merge_weaknesses

    directory = make_profile_dir(tmp_path, touched_days_ago=1)
    # 薄弱点文案里含完整点名时才能对上（真实形态：点评里会写清是哪个知识点）
    merge_weaknesses(directory, ["列表（ul/ol/li） 缩进混乱", "忘记空格"], when="2026-09-29")

    board = cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )
    # 位置参数按位置传（看板动作的名字与顺序由 ACTION_PARAM_KEYS 决定）
    result = board.run_action("done", {"name": "列表（ul/ol/li）", "path": "x.html", "recite": ""})

    assert result.ok, result.output
    left = [w.text for w in load_weaknesses(directory)]
    assert "列表（ul/ol/li） 缩进混乱" not in left, "涉及该知识点的薄弱点应被移除"
    assert "忘记空格" in left, "无关的薄弱点要留着"


def test_cli_next_passes_stale_days_through(tmp_path, monkeypatch, capsys):
    """--stale-days 要原样传到 _run_next（和 --topic 一样的路径）。"""
    from src import cli

    seen = {}
    monkeypatch.setattr(cli, "_run_next", lambda rest, env_path, **kw: seen.update(kw, rest=rest) or 0)
    directory = make_profile_dir(tmp_path, touched_days_ago=1)

    cli.main(["next", "--stale-days", "7"], env_path=tmp_path / ".env",
             profile_path=directory / "knowledge.md")
    capsys.readouterr()

    assert seen.get("rest") == ["--stale-days", "7"], seen


def test_run_next_parses_stale_days_into_generate_task(tmp_path, monkeypatch, capsys):
    """真正解析 --stale-days 的那一层：它要影响挑复习点的口径。"""
    from src import cli
    from src.planner import GeneratedTask

    directory = make_profile_dir(tmp_path, touched_days_ago=5)
    seen = {}

    def fake_generate(profile, **kwargs):
        seen.update(kwargs)
        return GeneratedTask(goal="新题", skills=["列表（ul/ol/li）"], acceptance="a", steps=["s"])

    monkeypatch.setattr(cli, "generate_task", fake_generate)
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kw: object())

    code = cli.main(
        ["next", "--stale-days", "3"],
        env_path=tmp_path / ".env",
        profile_path=directory / "knowledge.md",
        tasks_path=directory / "tasks.md",
    )
    capsys.readouterr()

    assert code == 0
    assert seen.get("stale_days") == 3, seen

# ---------- 看板展示 ----------


def test_task_card_shows_review_badge(tmp_path):
    from src.dashboard import TaskBoard

    directory = make_profile_dir(tmp_path, touched_days_ago=1)
    (directory / "tasks.md").write_text(
        "# 任务记录\n\n## 2026-09-27 10:00\n\n**目标**：复习：列表\n\n**复习**：是\n\n**验收方式**：a\n",
        encoding="utf-8",
    )
    page = TaskBoard(directory).pages()["tasks"]

    assert "badge-review" in page
    assert "复习" in page
    assert 'data-review="1"' in page


def test_normal_task_has_no_review_badge(tmp_path):
    from src.dashboard import TaskBoard

    directory = make_profile_dir(tmp_path, touched_days_ago=1)
    (directory / "tasks.md").write_text(
        "# 任务记录\n\n## 2026-09-27 10:00\n\n**目标**：做名片页\n\n**验收方式**：a\n",
        encoding="utf-8",
    )
    page = TaskBoard(directory).pages()["tasks"]

    assert 'data-review="0"' in page
    # 只看卡片里的角标（CSS 里本来就有 .badge-review 类名，不能拿它当"出现了角标"）
    card = page.split('data-task="2026-09-27 10:00"', 1)[1].split("task-card", 1)[0]
    assert "badge-review" not in card


def test_knowledge_page_lists_weaknesses(tmp_path):
    from src.dashboard import TaskBoard
    from src.weaknesses import merge_weaknesses

    directory = make_profile_dir(tmp_path, touched_days_ago=1)
    merge_weaknesses(directory, ["缩进混乱", "忘记空格"], when="2026-09-29")

    page = TaskBoard(directory).pages()["knowledge"]

    assert "薄弱点清单" in page
    assert "缩进混乱" in page and "忘记空格" in page


def test_knowledge_page_hides_empty_weakness_block(tmp_path):
    from src.dashboard import TaskBoard

    directory = make_profile_dir(tmp_path, touched_days_ago=1)
    page = TaskBoard(directory).pages()["knowledge"]

    assert "薄弱点清单 <span" not in page, "没有薄弱点时不该渲染这个区块"


# ---------- 验收 A/B/C ----------


def _stub_completer():
    import json as _json

    class Stub:
        def __init__(self):
            self.calls = []

        def complete(self, messages):
            self.calls.append(str(messages))
            return _json.dumps({
                "goal": "做一个小页面",
                "skills": ["列表（ul/ol/li）"],
                "steps": ["写 ul"],
                "acceptance": "能看到列表",
                "reason": "r",
            }, ensure_ascii=False)

    return Stub()


def test_acceptance_A_fourth_task_is_review(tmp_path, monkeypatch, capsys):
    """验收 A：连续出 4 题，第 4 题是复习题且来自超期未碰的学过点。"""
    from src import cli

    directory = make_profile_dir(tmp_path, touched_days_ago=30)
    # 让出题只用到「列表」这一个点，另外两个学过点保持"30 天没碰" →
    # 第 4 题真的挑得出复习候选（否则任务会把所有点都刷新成今天）
    class Stub:
        def complete(self, messages):
            import json as _json

            return _json.dumps({
                "goal": "练习列表标签",
                "skills": ["列表（ul/ol/li）"],
                "steps": ["写 ul"],
                "acceptance": "能看到列表",
                "reason": "r",
            }, ensure_ascii=False)

    monkeypatch.setattr(cli, "make_llm_completer", lambda **kw: Stub())

    outputs = []
    for _ in range(4):
        cli.main(["next"], env_path=tmp_path / ".env",
                 profile_path=directory / "knowledge.md", tasks_path=directory / "tasks.md")
        outputs.append(capsys.readouterr().out)

    assert "复习" not in outputs[0], "第 1 题不该是复习题"
    assert "复习" in outputs[3], "第 4 题必须是复习题"
    assert "重做" in outputs[3] or "凭记忆" in outputs[3], "复习题要是「重做一遍」的形态"
    text = (directory / "tasks.md").read_text(encoding="utf-8")
    assert text.count("**复习**") == 1, "复习标记要落进留档（计数靠它）"


def test_acceptance_B_weaknesses_enter_next_prompt(tmp_path, monkeypatch, capsys):
    """验收 B：交一份有问题的作业后，下次出题 prompt 含清单。"""
    from src import cli
    from src.review import review_code
    from src.weaknesses import load_weaknesses, merge_weaknesses

    directory = make_profile_dir(tmp_path, touched_days_ago=1)
    merge_weaknesses(directory, ["缩进混乱"], when="2026-09-29")

    stub = _stub_completer()
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kw: stub)
    (directory / "tasks.md").write_text(
        "# 任务记录\n\n## 2026-09-27 10:00\n\n**目标**：先有一道题\n\n**验收方式**：a\n",
        encoding="utf-8",
    )

    cli.main(["next"], env_path=tmp_path / ".env",
             profile_path=directory / "knowledge.md", tasks_path=directory / "tasks.md")
    capsys.readouterr()

    assert any("缩进混乱" in call for call in stub.calls), "出题 prompt 里要带上错题本"
    assert [w.text for w in load_weaknesses(directory)] == ["缩进混乱"]


def test_acceptance_C_done_clears_weakness(tmp_path):
    """验收 C：done 之后对应薄弱点消失。"""
    from src import cli
    from src.weaknesses import load_weaknesses, merge_weaknesses

    directory = make_profile_dir(tmp_path, touched_days_ago=1)
    merge_weaknesses(directory, ["列表（ul/ol/li） 缩进混乱", "另外一条"], when="2026-09-29")

    board = cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )
    result = board.run_action("done", {"name": "列表（ul/ol/li）", "path": "x.html", "recite": ""})

    assert result.ok, result.output
    left = [w.text for w in load_weaknesses(directory)]
    assert "列表（ul/ol/li） 缩进混乱" not in left
    assert "另外一条" in left
    # done 后 last_touched 应刷新成今天
    import datetime

    point = KnowledgeProfile.load(directory / "knowledge.md").find("列表（ul/ol/li）")
    assert point is not None
    assert point.last_touched == datetime.date.today().isoformat()

def test_review_due_requires_a_stale_candidate(tmp_path):
    """到节奏了但挑不出超期点，就不该出复习题（否则会出空复习）。"""
    from src.planner import review_due

    import datetime

    path = tmp_path / "tasks.md"
    body = ""
    for index in range(3):
        body += f"## 2026-09-2{index} 10:00\n\n**目标**：新题 {index}\n\n"
    path.write_text("# 任务记录\n\n" + body, encoding="utf-8")

    fresh = KnowledgeProfile(points=[
        KnowledgePoint("刚碰过", "学过", "e", last_touched=datetime.date.today().isoformat()),
    ])
    stale = KnowledgeProfile(points=[
        KnowledgePoint("很久没碰", "学过", "e", last_touched="2026-01-01"),
    ])

    assert review_due(path, profile=fresh, stale_days=14) is False
    assert review_due(path, profile=stale, stale_days=14) is True