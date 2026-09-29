"""T-005 失败测试：next 命令（读画像 [+ 地图] → 生成可验收的动手任务）。

验收（[[04-任务与验收清单]] T-005 / A-03；地图版 A-06）：

- 只用画像内已学知识 + 至多 1 个新知识点；
- 新点优先取地图中按书序的下一个未掌握点（地图不存在时降级为「仅画像版」）；
- 输出含目标、用到的知识点、验收方式；
- 画像知识点 < 3 时不出题，提示先积累笔记。

实现前编写（src/planner.py 尚不存在），必须全部失败。
"""

from __future__ import annotations

import json

import pytest

from src.distill import KnowledgePoint
from src.planner import (
    MIN_POINTS,
    GeneratedTask,
    PlannerError,
    build_next_messages,
    generate_task,
    next_unmet_point,
    parse_task,
    render_task,
)
from src.profile import KnowledgeProfile, write_profile_atomic

PY = "Python 基础"


def profile_with(*names, level="学过", topic=PY):
    return KnowledgeProfile(points=[KnowledgePoint(n, level, "来自笔记 " + n, topic) for n in names])


class FakeCompleter:
    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        if not self._replies:
            raise AssertionError("未预置的 LLM 调用")
        nxt = self._replies.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt() if callable(nxt) else nxt

    def prompt_text(self):
        return "\n".join(m.get("content", "") for m in self.calls[0])


def task_json(goal="写一个通讯录 CLI", skills=None, acceptance="运行后能增删查并存盘", new_skill=None, steps=None):
    payload = {
        "goal": goal,
        "skills": skills if skills is not None else ["列表", "字典"],
        "acceptance": acceptance,
        "steps": steps if steps is not None else ["定义数据结构", "实现增删查", "存盘"],
        "new_skill": new_skill,
    }
    return json.dumps(payload, ensure_ascii=False)


# --- 1. 画像不足 -------------------------------------------------------------


def test_generate_task_requires_min_points():
    profile = profile_with("列表", "字典")

    with pytest.raises(PlannerError) as exc:
        generate_task(profile, completer=FakeCompleter([]))

    assert str(MIN_POINTS) in str(exc.value)
    assert "笔记" in str(exc.value)


def test_generate_task_skips_llm_when_points_insufficient():
    completer = FakeCompleter([])

    with pytest.raises(PlannerError):
        generate_task(profile_with("列表"), completer=completer)

    assert completer.calls == []


# --- 2. prompt 约束 ---------------------------------------------------------


def test_prompt_lists_profile_points_with_levels():
    messages = build_next_messages(profile_with("列表", "字典", "循环"))

    text = "\n".join(m["content"] for m in messages)
    assert "列表" in text and "字典" in text and "循环" in text
    assert "学过" in text


def test_prompt_states_one_new_skill_limit_and_python_default():
    text = "\n".join(m["content"] for m in build_next_messages(profile_with("列表", "字典", "循环")))

    assert "1 个" in text or "至多一个" in text or "≤1" in text
    assert "Python" in text


def test_prompt_mentions_json_contract_with_acceptance():
    text = "\n".join(m["content"] for m in build_next_messages(profile_with("列表", "字典", "循环")))

    assert "JSON" in text.upper()
    assert "acceptance" in text
    assert "goal" in text


def test_prompt_asks_no_code_written_for_client():
    """模块边界：不替客户写代码。"""
    text = "\n".join(m["content"] for m in build_next_messages(profile_with("列表", "字典", "循环")))

    assert "不要" in text or "不得" in text


def test_prompt_includes_map_when_available():
    profile = profile_with("列表", "字典", "循环")
    syllabus = {"book": "Python 入门", "chapters": [{"chapter": "第 4 章", "points": ["函数", "文件读写"]}]}

    text = "\n".join(m["content"] for m in build_next_messages(profile, syllabus=syllabus))

    assert "Python 入门" in text
    assert "函数" in text
    assert "第 4 章" in text


def test_prompt_says_profile_only_when_no_map():
    text = "\n".join(m["content"] for m in build_next_messages(profile_with("列表", "字典", "循环")))

    assert "地图" in text  # 要说明地图缺失时的降级要求
    assert "不存在" in text or "没有" in text or "未导入" in text


# --- 3. 解析 -----------------------------------------------------------------


def test_parse_task_reads_required_fields():
    task = parse_task(task_json())

    assert task.goal == "写一个通讯录 CLI"
    assert task.skills == ["列表", "字典"]
    assert "存盘" in task.acceptance
    assert task.new_skill is None
    assert len(task.steps) == 3


def test_parse_task_rejects_missing_acceptance():
    raw = json.dumps({"goal": "g", "skills": ["列表"]}, ensure_ascii=False)

    with pytest.raises(PlannerError) as exc:
        parse_task(raw)
    assert "acceptance" in str(exc.value)


def test_parse_task_rejects_empty_goal():
    raw = json.dumps({"goal": "  ", "skills": ["列表"], "acceptance": "a"}, ensure_ascii=False)

    with pytest.raises(PlannerError):
        parse_task(raw)


def test_parse_task_wraps_single_object_with_task_key():
    raw = json.dumps({"task": {"goal": "g", "skills": ["列表"], "acceptance": "a"}}, ensure_ascii=False)

    assert parse_task(raw).goal == "g"


# --- 4. 越界校验 -------------------------------------------------------------


def test_generate_task_accepts_skills_inside_profile():
    profile = profile_with("列表", "字典", "循环")
    completer = FakeCompleter([task_json(skills=["列表", "字典"])])

    task = generate_task(profile, completer=completer)

    assert task.skills == ["列表", "字典"]
    assert task.new_skill is None


def test_generate_task_retries_once_on_out_of_scope_skill():
    profile = profile_with("列表", "字典", "循环")
    completer = FakeCompleter(
        [task_json(skills=["列表", "并发编程"]), task_json(skills=["列表", "字典"])]
    )

    task = generate_task(profile, completer=completer)

    assert len(completer.calls) == 2
    assert task.skills == ["列表", "字典"]
    # 重试的 prompt 要指出上次越界
    retry_text = "\n".join(m["content"] for m in completer.calls[1])
    assert "并发编程" in retry_text


def test_generate_task_gives_up_after_second_violation():
    profile = profile_with("列表", "字典", "循环")
    completer = FakeCompleter([task_json(skills=["并发编程"]), task_json(skills=["协程"])])

    with pytest.raises(PlannerError) as exc:
        generate_task(profile, completer=completer)

    assert len(completer.calls) == 2
    assert "画像" in str(exc.value)


def test_generate_task_allows_exactly_one_new_skill():
    profile = profile_with("列表", "字典", "循环")
    completer = FakeCompleter([task_json(skills=["列表", "字典"], new_skill="函数")])

    task = generate_task(profile, completer=completer)

    assert task.new_skill == "函数"


def test_generate_task_rejects_out_of_scope_skill_repeatedly():
    """两次都越界 → 报错且不再重试（避免死循环）。"""
    profile = profile_with("列表", "字典", "循环")
    completer = FakeCompleter(
        [task_json(skills=["列表", "并发编程"]), task_json(skills=["列表", "协程"])]
    )

    with pytest.raises(PlannerError) as exc:
        generate_task(profile, completer=completer)

    assert len(completer.calls) == 2
    assert "画像" in str(exc.value)


# --- 5. 地图约束（A-06） -----------------------------------------------------


def test_new_skill_must_come_from_map_next_unmet_point():
    """有地图时新点必须是地图里按书序的下一个未掌握点，否则带提示重试。"""
    profile = profile_with("列表", "字典", "循环")
    syllabus = {"book": "Python 入门", "chapters": [{"chapter": "第 4 章", "points": ["函数", "文件读写"]}]}
    completer = FakeCompleter(
        [task_json(skills=["列表"], new_skill="装饰器"), task_json(skills=["列表"], new_skill="函数")]
    )

    task = generate_task(profile, syllabus=syllabus, completer=completer)

    assert task.new_skill == "函数"
    retry_text = chr(10).join(m["content"] for m in completer.calls[1])
    assert "装饰器" in retry_text


def test_map_next_unmet_point_skips_already_known():
    profile = profile_with("列表", "函数", "循环")
    syllabus = {"book": "Python 入门", "chapters": [{"chapter": "第 4 章", "points": ["函数", "文件读写"]}]}

    assert next_unmet_point(syllabus, profile) == "文件读写"


def test_next_unmet_point_none_when_map_exhausted():
    profile = profile_with("列表", "函数", "文件读写")
    syllabus = {"book": "Python 入门", "chapters": [{"chapter": "第 4 章", "points": ["函数", "文件读写"]}]}

    assert next_unmet_point(syllabus, profile) is None


# --- 6. 渲染与落档 -----------------------------------------------------------


def test_render_task_contains_goal_skills_acceptance():
    task = GeneratedTask(goal="写通讯录", skills=["列表"], acceptance="能存盘", new_skill="函数", steps=["a"])

    text = render_task(task)

    assert "写通讯录" in text
    assert "列表" in text
    assert "能存盘" in text
    assert "函数" in text


def test_render_task_marks_new_skill_as_new():
    task = GeneratedTask(goal="g", skills=["列表"], acceptance="a", new_skill="函数")

    text = render_task(task)

    assert "新" in text


# --- 7. CLI ----------------------------------------------------------------


def test_cli_next_prints_task_and_appends_record(tmp_path, monkeypatch, capsys):
    from src import cli

    profile_path = tmp_path / "profile" / "knowledge.md"
    write_profile_atomic(profile_path, profile_with("列表", "字典", "循环"))
    tasks_path = tmp_path / "profile" / "tasks.md"
    completer = FakeCompleter([task_json()])
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: completer)

    code = cli.main(
        ["next"], env_path=tmp_path / ".env", profile_path=profile_path, tasks_path=tasks_path
    )
    out = capsys.readouterr()

    assert code == 0
    assert "写一个通讯录 CLI" in out.out
    assert tasks_path.is_file()
    assert "写一个通讯录 CLI" in tasks_path.read_text(encoding="utf-8")


def test_cli_next_reports_insufficient_profile(tmp_path, monkeypatch, capsys):
    from src import cli

    profile_path = tmp_path / "profile" / "knowledge.md"
    write_profile_atomic(profile_path, profile_with("列表"))
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: FakeCompleter([]))

    code = cli.main(["next"], env_path=tmp_path / ".env", profile_path=profile_path)
    out = capsys.readouterr()

    assert code == 0
    assert "笔记" in out.err


def test_cli_next_missing_profile_reports_clearly(tmp_path, monkeypatch, capsys):
    from src import cli

    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: FakeCompleter([]))

    code = cli.main(
        ["next"], env_path=tmp_path / ".env", profile_path=tmp_path / "profile" / "knowledge.md"
    )
    out = capsys.readouterr()

    # T-017 I-3 起：缺前置产物统一退 1（原先这里退 0），并指明下一步
    assert code == 1
    assert "画像" in out.err
    assert "sync" in out.err and "distill" in out.err


def test_two_mastered_plus_many_uncertain_still_refuses():
    profile = KnowledgeProfile(points=[
        KnowledgePoint("列表", "学过", "e"),
        KnowledgePoint("字典", "学过", "e"),
        KnowledgePoint("循环", "存疑", "e"),
        KnowledgePoint("函数", "存疑", "e"),
    ])

    with pytest.raises(PlannerError):
        generate_task(profile, completer=FakeCompleter([]))


def test_mixed_profile_uses_mastered_for_skills_check():
    """已掌握 ≥3 时正常出题；存疑点仍不能出现在 skills 里。"""
    profile = KnowledgeProfile(points=[
        KnowledgePoint("列表", "学过", "e"),
        KnowledgePoint("字典", "学过", "e"),
        KnowledgePoint("循环", "学过", "e"),
        KnowledgePoint("装饰器", "存疑", "e"),
    ])

    completer = FakeCompleter([task_json(skills=["列表", "字典"])])
    task = generate_task(profile, completer=completer)

    assert task.skills == ["列表", "字典"]

def test_cli_next_accepts_provider_flag(tmp_path, monkeypatch, capsys):
    """next 也要能指定 provider（与 distill 一致），否则客户没法强制走 Kimi。"""
    from src import cli

    profile_path = tmp_path / "profile" / "knowledge.md"
    write_profile_atomic(profile_path, profile_with("列表", "字典", "循环"))
    captured = {}

    def fake_completer(env_path=None, provider=None, home=None):
        captured["provider"] = provider
        return FakeCompleter([task_json()])

    monkeypatch.setattr(cli, "make_llm_completer", fake_completer)

    code = cli.main(
        ["next", "--provider", "kimi"],
        env_path=tmp_path / ".env",
        profile_path=profile_path,
        tasks_path=tmp_path / "profile" / "tasks.md",
    )
    out = capsys.readouterr()

    assert code == 0
    assert captured["provider"] == "kimi"
    assert "写一个通讯录 CLI" in out.out


def test_cli_next_unknown_provider_exits_2(tmp_path, monkeypatch, capsys):
    from src import cli

    profile_path = tmp_path / "profile" / "knowledge.md"
    write_profile_atomic(profile_path, profile_with("列表", "字典", "循环"))
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: FakeCompleter([]))

    code = cli.main(["next", "--provider", "openai"], env_path=tmp_path / ".env", profile_path=profile_path)
    out = capsys.readouterr()

    assert code == 2
    assert "openai" in out.err

def test_parse_task_recovers_json_with_trailing_prose():
    """实测：真实模型会在 JSON 后面继续写说明文字，
    以「整段必须是合法 JSON」的方式解析会直接失败。应能取出其中的 JSON 对象。"""
    raw = task_json() + chr(10) + chr(10) + "希望这个任务对你有帮助！如果需要更简单的版本可以告诉我。"

    task = parse_task(raw)

    assert task.goal == "写一个通讯录 CLI"


def test_parse_task_recovers_json_with_leading_prose_and_fence():
    raw = "好的，这是你的任务：" + chr(10) + chr(96) * 3 + "json" + chr(10) + task_json() + chr(10) + chr(96) * 3 + chr(10) + "加油！"

    assert parse_task(raw).goal == "写一个通讯录 CLI"


def test_parse_task_recovers_json_array_with_trailing_prose():
    raw = "[" + task_json() + "]" + chr(10) + "以上。"

    assert parse_task(raw).goal == "写一个通讯录 CLI"


def test_generate_task_retries_when_output_unparseable():
    profile = profile_with("列表", "字典", "循环")
    completer = FakeCompleter(["完全不是 JSON 的一段话", task_json()])

    task = generate_task(profile, completer=completer)

    assert len(completer.calls) == 2
    assert task.goal == "写一个通讯录 CLI"

def test_skills_with_topic_suffix_match_profile_names():
    """实测：模型会照抄 prompt 里的「列表（Python 基础）」当知识点名，
    它不是越界，应能匹配到画像里的「列表」。"""
    profile = profile_with("列表", "字典", "循环")
    completer = FakeCompleter([task_json(skills=["列表（Python 基础）", "字典（Python 基础）"])])

    task = generate_task(profile, completer=completer)

    assert task.skills == ["列表", "字典"]


def test_prompt_forbids_appending_topic_to_skill_names():
    text = chr(10).join(m["content"] for m in build_next_messages(profile_with("列表", "字典", "循环")))

    assert "只写知识点名称" in text or "不要带主题" in text


def test_out_of_scope_still_detected_after_normalization():
    profile = profile_with("列表", "字典", "循环")
    completer = FakeCompleter([
        task_json(skills=["列表（Python 基础）", "并发编程（Python 基础）"]),
        task_json(skills=["列表（Python 基础）", "并发编程（Python 基础）"]),
    ])

    with pytest.raises(PlannerError) as exc:
        generate_task(profile, completer=completer)
    assert "并发编程" in str(exc.value)