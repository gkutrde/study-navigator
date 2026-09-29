"""T-028 失败测试：作业点评（固定动作集加 review）。

要求：
- 任务卡片「提交作业」：粘贴代码或填本地路径；
- 白名单 {task, code}；
- 代码 ≤8000 字符，超额截断并注明；
- LLM 按**验收方式**给评价 + 建议，留档含提交时间，可多次；
- CLI 加 review <时间戳> <文件>。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.dashboard import ACTION_PARAM_KEYS, FIXED_ACTIONS, Dashboard, TaskBoard
from src.distill import KnowledgePoint
from src.profile import KnowledgeProfile, write_profile_atomic

TASKS_MD = """# 任务记录

## 2026-09-27 10:00

## 下一步任务

**目标**：做一个个人名片页

**用到的知识点**：列表（ul/ol/li）

**验收方式**：页面能显示姓名、一句话简介、头像占位

## 2026-09-27 11:00

## 下一步任务

**目标**：做一张课程表

**验收方式**：表格有 4 行
"""


def make_directory(tmp_path, tasks=TASKS_MD):
    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    write_profile_atomic(
        directory / "knowledge.md",
        KnowledgeProfile(points=[KnowledgePoint("列表（ul/ol/li）", "学过", "e")]),
    )
    (directory / "tasks.md").write_text(tasks, encoding="utf-8")
    return directory


class StubCompleter:
    def __init__(self, reply="【评价】结构清晰。【建议】加上头像占位。"):
        self.reply = reply
        self.calls = 0
        self.seen: list = []

    def complete(self, messages):
        self.calls += 1
        self.seen.append(messages)
        return self.reply


# ---------- 1. 白名单：review 进固定动作集 ----------


def test_review_is_a_fixed_action(tmp_path):
    assert "review" in FIXED_ACTIONS


def test_review_param_whitelist_is_task_and_code(tmp_path):
    assert ACTION_PARAM_KEYS["review"] == frozenset({"task", "code"})


def test_review_rejects_extra_params(tmp_path):
    directory = make_directory(tmp_path)
    board = TaskBoard(directory, operations={"review": lambda **kw: "ok"})

    result = board.run_action("review", {"task": "2026-09-27 10:00", "code": "x", "cmd": "whoami"})

    assert not result.ok
    assert result.status == 400


# ---------- 2. 留档：写入 tasks.md 对应块 ----------


def test_review_appends_evaluation_to_task_block(tmp_path):
    from src.planner import append_review

    directory = make_directory(tmp_path)
    path = directory / "tasks.md"

    append_review(path, "2026-09-27 10:00", code="<h1>张三</h1>", feedback="结构清晰", suggestion="加头像")

    text = path.read_text(encoding="utf-8")
    block = text.split("## 2026-09-27 11:00")[0]
    assert "提交时间" in block
    assert "结构清晰" in block
    assert "加头像" in block
    # 别的块不该被污染
    assert "提交时间" not in text.split("## 2026-09-27 11:00")[1]


def test_review_records_submit_time(tmp_path):
    from src.planner import append_review, read_task_records

    directory = make_directory(tmp_path)
    path = directory / "tasks.md"

    append_review(path, "2026-09-27 10:00", code="x", feedback="f", suggestion="s")

    record = next(r for r in read_task_records(path) if r.when == "2026-09-27 10:00")
    assert record.reviews, "留档里要有点评记录"
    assert record.reviews[0].submitted_at, "要有提交时间"


def test_review_can_be_submitted_multiple_times(tmp_path):
    from src.planner import append_review, read_task_records

    directory = make_directory(tmp_path)
    path = directory / "tasks.md"

    append_review(path, "2026-09-27 10:00", code="v1", feedback="第一次评价", suggestion="s1")
    append_review(path, "2026-09-27 10:00", code="v2", feedback="第二次评价", suggestion="s2")

    record = next(r for r in read_task_records(path) if r.when == "2026-09-27 10:00")
    assert len(record.reviews) == 2, "可多次提交，历史都留着"
    text = path.read_text(encoding="utf-8")
    assert "第一次评价" in text and "第二次评价" in text


def test_review_unknown_task_raises(tmp_path):
    from src.planner import PlannerError, append_review

    directory = make_directory(tmp_path)

    with pytest.raises(PlannerError):
        append_review(directory / "tasks.md", "1999-01-01 00:00", code="x", feedback="f", suggestion="s")


def test_review_is_atomic_and_leaves_no_tmp(tmp_path):
    from src.planner import append_review

    directory = make_directory(tmp_path)

    append_review(directory / "tasks.md", "2026-09-27 10:00", code="x", feedback="f", suggestion="s")

    assert not list(directory.glob("*.tmp"))


# ---------- 3. 代码截断 ----------


def test_code_is_truncated_at_limit(tmp_path):
    from src.review import MAX_CODE_CHARS, prepare_code

    long_code = "a" * (MAX_CODE_CHARS + 500)
    text, truncated = prepare_code(long_code)

    assert truncated is True
    assert len(text) <= MAX_CODE_CHARS
    assert "截断" in text, "超额要在代码里注明"


def test_short_code_is_not_truncated(tmp_path):
    from src.review import prepare_code

    text, truncated = prepare_code("<h1>hi</h1>")

    assert truncated is False
    assert text == "<h1>hi</h1>"


def test_review_notes_truncation_in_archive(tmp_path):
    from src.planner import append_review, read_task_records

    directory = make_directory(tmp_path)
    path = directory / "tasks.md"
    long_code = "x" * 9000

    append_review(path, "2026-09-27 10:00", code=long_code, feedback="f", suggestion="s")

    record = next(r for r in read_task_records(path) if r.when == "2026-09-27 10:00")
    assert record.reviews[0].truncated is True


# ---------- 4. LLM 按验收方式点评 ----------


def test_review_prompt_includes_acceptance_and_code(tmp_path):
    from src.review import build_review_messages

    messages = build_review_messages(
        goal="做一个个人名片页", acceptance="页面能显示姓名", code="<h1>张三</h1>"
    )
    blob = json.dumps(messages, ensure_ascii=False)

    assert "页面能显示姓名" in blob, "要按验收方式点评"
    assert "<h1>张三</h1>" in blob
    assert "建议" in blob


def test_review_task_gives_feedback_and_suggestion(tmp_path):
    from src.review import review_code

    completer = StubCompleter("【评价】OK\n\n【建议】加头像")
    result = review_code(
        goal="做名片页", acceptance="显示姓名", code="<h1>张三</h1>", completer=completer
    )

    assert result.feedback
    assert result.suggestion
    assert completer.calls == 1


def test_review_parses_evaluation_and_suggestion(tmp_path):
    from src.review import review_code

    completer = StubCompleter("【评价】结构清晰，语义正确。\n【建议】补一个头像占位 div。")
    result = review_code(goal="g", acceptance="a", code="c", completer=completer)

    assert "结构清晰" in result.feedback
    assert "头像占位" in result.suggestion


def test_review_without_suggestion_section_still_works(tmp_path):
    from src.review import review_code

    completer = StubCompleter("这段代码整体可用，但列表标签没闭合。")
    result = review_code(goal="g", acceptance="a", code="c", completer=completer)

    assert result.feedback, "没有分区时整段当评价"
    assert result.suggestion == ""


# ---------- 5. HTTP / 看板接线 ----------


def test_review_accepts_json_request(tmp_path):
    from src import cli

    directory = make_directory(tmp_path)
    completer = StubCompleter()

    board = cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )
    board._operations["review"] = _make_review_op(directory, completer)
    dash = Dashboard(directory, board=board)

    status, content_type, body = dash.handle_request(
        "POST", "/action/review",
        body=json.dumps({"task": "2026-09-27 10:00", "code": "<h1>张三</h1>"}).encode("utf-8"),
        content_type="application/json",
    )

    assert status == 200, body[:300]
    payload = json.loads(body)
    assert payload["ok"] is True
    assert "评价" in payload["output"] or "结构" in payload["output"]
    assert "提交时间" in (directory / "tasks.md").read_text(encoding="utf-8")


def _make_review_op(directory, completer):
    from src.planner import append_review, read_task_records
    from src.review import review_code

    def op(task: str, code: str):
        record = next((r for r in read_task_records(directory / "tasks.md") if r.when == task), None)
        if record is None:
            raise RuntimeError(f"没有时间戳为「{task}」的任务")
        result = review_code(
            goal=record.goal, acceptance=record.acceptance, code=code, completer=completer
        )
        append_review(
            directory / "tasks.md", task, code=result.code,
            feedback=result.feedback, suggestion=result.suggestion, truncated=result.truncated,
        )
        return f"【评价】{result.feedback}\n【建议】{result.suggestion}"

    return op


def test_review_json_requires_task_and_code(tmp_path):
    from src import cli

    directory = make_directory(tmp_path)
    board = cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )
    dash = Dashboard(directory, board=board)

    status, _ct, body = dash.handle_request(
        "POST", "/action/review",
        body=json.dumps({"task": "2026-09-27 10:00"}).encode("utf-8"),
        content_type="application/json",
    )

    assert status == 400
    assert "code" in json.loads(body)["message"] or "代码" in json.loads(body)["message"]


def test_task_card_has_submit_form(tmp_path):
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    assert 'action="/action/review"' in page
    assert 'name="task"' in page
    assert 'name="code"' in page


def test_task_card_shows_existing_review(tmp_path):
    from src.planner import append_review

    directory = make_directory(tmp_path)
    append_review(
        directory / "tasks.md", "2026-09-27 10:00",
        code="x", feedback="结构清晰", suggestion="加头像",
    )

    page = TaskBoard(directory).pages()["tasks"]

    assert "结构清晰" in page
    assert "提交时间" in page


# ---------- 6. CLI ----------


def test_cli_review_writes_archive(tmp_path, monkeypatch, capsys):
    from src import cli

    directory = make_directory(tmp_path)
    code_file = tmp_path / "card.html"
    code_file.write_text("<h1>张三</h1>", encoding="utf-8")

    monkeypatch.setattr(cli, "make_llm_completer", lambda **kw: StubCompleter("【评价】好\n【建议】加头像"))
    code = cli.main(
        ["review", "2026-09-27 10:00", str(code_file), "--provider", "deepseek"],
        env_path=tmp_path / ".env",
        profile_path=directory / "knowledge.md",
    )
    capsys.readouterr()

    assert code == 0
    text = (directory / "tasks.md").read_text(encoding="utf-8")
    assert "提交时间" in text
    assert "加头像" in text


def test_cli_review_rejects_missing_file(tmp_path, capsys):
    from src import cli

    directory = make_directory(tmp_path)
    code = cli.main(
        ["review", "2026-09-27 10:00", str(tmp_path / "nope.html")],
        env_path=tmp_path / ".env",
        profile_path=directory / "knowledge.md",
    )
    err = capsys.readouterr().err

    assert code == 1
    assert "找不到" in err or "不存在" in err


def test_cli_review_needs_two_args(tmp_path, capsys):
    from src import cli

    directory = make_directory(tmp_path)
    code = cli.main(["review", "2026-09-27 10:00"], env_path=tmp_path / ".env",
                    profile_path=directory / "knowledge.md")
    capsys.readouterr()

    assert code == 2
