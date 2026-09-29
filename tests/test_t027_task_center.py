"""T-027 失败测试：任务中心（路由真分离 + 任务卡片 + 行内讲解 + 删除）。

现状（实测）：'' / index / knowledge / tasks **四个路由返回完全相同的 12714 字符页面**，
地图页压根不存在；任务区是纯 markdown 渲染，没有结构化卡片。

验收：四路由各自渲染、画像页无任务区块；卡片 chips 点击出行内讲解（二次命中缓存）；
删除只动目标块。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.dashboard import Dashboard, TaskBoard
from src.distill import KnowledgePoint
from src.profile import KnowledgeProfile, write_profile_atomic

TASKS_MD = """# 任务记录

## 2026-09-27 10:00

## 下一步任务

**目标**：做一个个人名片页

**题目出处**：哈佛 CS50（A-01 个人名片页）

**用到的知识点**：标题与文本格式化标签、列表（ul/ol/li）

**新知识点**：超链接 a 标签（href/target）（本次唯一的新点）

**验收方式**：能看到

## 2026-09-27 11:00

## 下一步任务

**目标**：做一张课程表

**用到的知识点**：表格（table/tr/th/td）

**验收方式**：能数出 4 行
"""

SYLLABUS_MD = """# 知识地图

## 某书

### 第 1 章 认识 HTML

- 点A
"""


def make_directory(tmp_path, *, tasks=TASKS_MD, syllabus=SYLLABUS_MD):
    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    write_profile_atomic(
        directory / "knowledge.md",
        KnowledgeProfile(points=[
            KnowledgePoint("列表（ul/ol/li）", "学过", "e"),
            KnowledgePoint("表格（table/tr/th/td）", "存疑", "e"),
        ]),
    )
    if tasks is not None:
        (directory / "tasks.md").write_text(tasks, encoding="utf-8")
    if syllabus is not None:
        (directory / "syllabus.md").write_text(syllabus, encoding="utf-8")
    return directory


def sections(html: str) -> dict:
    """从页面里抽出各区块出现与否，避免断言整页文本。"""
    return {
        "knowledge": "知识画像" in html,
        "tasks": "任务中心" in html or "任务记录" in html,
        "syllabus": "知识地图" in html,
    }


# ---------- 1. 路由真分离 ----------


def test_routes_are_distinct_pages(tmp_path):
    directory = make_directory(tmp_path)
    pages = TaskBoard(directory).pages()

    assert set(pages) >= {"", "knowledge", "tasks", "syllabus"}
    bodies = {route: pages[route] for route in ("", "knowledge", "tasks", "syllabus")}
    assert len(set(bodies.values())) == 4, "四个路由必须是不同页面"


def test_knowledge_page_has_no_task_section(tmp_path):
    """画像页不该有任务区块内容。

    注意：顶栏导航里有「任务中心」这个链接文字，所以不能直接断言页面不含该词——
    要断言的是**任务内容**不在画像页里。
    """
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["knowledge"]

    assert "<h2>知识画像</h2>" in page
    assert "<h2>任务中心</h2>" not in page
    assert "做一个个人名片页" not in page
    assert "data-task=" not in page


def test_tasks_page_has_no_knowledge_section(tmp_path):
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    assert "任务中心" in page
    assert "做一个个人名片页" in page
    assert "表格（table/tr/th/td）" not in page.split("任务中心", 1)[0]


def test_syllabus_page_renders_map(tmp_path):
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["syllabus"]

    assert "知识地图" in page
    assert "第 1 章 认识 HTML" in page


def test_home_page_is_overview_not_full_dump(tmp_path):
    directory = make_directory(tmp_path)
    pages = TaskBoard(directory).pages()

    home = pages[""]
    # 首页只做概览：不该把整份任务记录塞进来
    assert len(home) < len(pages["tasks"])
    assert "做一个个人名片页" not in home


def test_index_alias_equals_home(tmp_path):
    directory = make_directory(tmp_path)
    pages = TaskBoard(directory).pages()

    assert pages.get("index", pages[""]) == pages[""]


def test_nav_links_point_to_all_four(tmp_path):
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()[""]

    for href in ('href="/"', 'href="/knowledge"', 'href="/tasks"', 'href="/syllabus"'):
        assert href in page, f"导航缺 {href}"


# ---------- 2. 任务卡片 ----------


def test_task_cards_are_structured(tmp_path):
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    assert page.count('class="task-card"') == 2
    assert "2026-09-27 10:00" in page
    assert "2026-09-27 11:00" in page


def test_task_card_shows_source_when_present(tmp_path):
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    assert "哈佛 CS50" in page
    assert "题目出处" in page


def test_task_card_lists_points_as_chips(tmp_path):
    """卡片上的知识点 chip 要能点（行内讲解）。"""
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    for name in ("标题与文本格式化标签", "列表（ul/ol/li）", "超链接 a 标签（href/target）"):
        assert f'data-explain="{name}"' in page, f"缺 {name} 的讲解 chip"


def test_points_chips_do_not_appear_in_free_text(tmp_path):
    """验收方式里的文字不该被当成知识点 chip。"""
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    assert 'data-explain="能看到"' not in page
    assert 'data-explain="能数出 4 行"' not in page


def test_each_task_card_has_delete_button(tmp_path):
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    assert page.count('data-delete-task="2026-09-27 10:00"') == 1
    assert page.count('data-delete-task="2026-09-27 11:00"') == 1


# ---------- 3. 删除：只动目标块 ----------


def test_delete_task_removes_only_that_block(tmp_path):
    from src.planner import delete_task_record

    directory = make_directory(tmp_path)
    path = directory / "tasks.md"

    delete_task_record(path, "2026-09-27 10:00")
    text = path.read_text(encoding="utf-8")

    assert "做一个个人名片页" not in text
    assert "做一张课程表" in text
    assert "2026-09-27 11:00" in text
    assert "# 任务记录" in text, "标题不能被删掉"


def test_delete_task_is_atomic_and_leaves_no_tmp(tmp_path):
    from src.planner import delete_task_record

    directory = make_directory(tmp_path)
    path = directory / "tasks.md"

    delete_task_record(path, "2026-09-27 10:00")

    assert not list(directory.glob("*.tmp"))


def test_delete_unknown_timestamp_raises(tmp_path):
    from src.planner import PlannerError, delete_task_record

    directory = make_directory(tmp_path)

    with pytest.raises(PlannerError):
        delete_task_record(directory / "tasks.md", "1999-01-01 00:00")


def test_delete_last_block_keeps_header(tmp_path):
    from src.planner import delete_task_record

    directory = make_directory(tmp_path)
    path = directory / "tasks.md"

    delete_task_record(path, "2026-09-27 10:00")
    delete_task_record(path, "2026-09-27 11:00")

    assert path.read_text(encoding="utf-8").strip() == "# 任务记录"


# ---------- 4. 删除动作进白名单，且不破坏固定动作集 ----------


def test_delete_action_is_whitelisted(tmp_path):
    from src.dashboard import ACTION_PARAM_KEYS, FIXED_ACTIONS

    assert "delete_task" in FIXED_ACTIONS
    assert ACTION_PARAM_KEYS["delete_task"] == frozenset({"when"})


def test_delete_task_action_removes_block(tmp_path):
    from src import cli

    directory = make_directory(tmp_path)
    board = cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )

    result = board.run_action("delete_task", {"when": "2026-09-27 10:00"})

    assert result.ok
    assert "做一个个人名片页" not in (directory / "tasks.md").read_text(encoding="utf-8")


def test_delete_task_action_rejects_extra_params(tmp_path):
    directory = make_directory(tmp_path)
    board = TaskBoard(directory)

    result = board.run_action("delete_task", {"when": "2026-09-27 10:00", "cmd": "rm -rf /"})

    assert not result.ok
    assert result.status == 400


def test_delete_action_requires_when(tmp_path):
    from src import cli

    directory = make_directory(tmp_path)
    board = cli._build_board(
        tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None
    )

    result = board.run_action("delete_task", {})

    assert not result.ok
    assert "时间" in result.output or "when" in result.output

# ---------- 5. JS 路径：explain / delete_task 也要 JSON 响应 ----------


def test_explain_accepts_json_request(tmp_path, monkeypatch):
    """JS 点 chip 要拿 JSON；explain 在 JSON 路径下不能回 303。"""
    from src import cli
    from src.syllabus import BookMap, Chapter, write_syllabus
    from src.explain import default_cache_dir

    directory = make_directory(tmp_path)
    # 书名要与真实约定一致：地图里的 book 必须能对上蒸馏稿 frontmatter 的 book
    write_syllabus(directory / "syllabus.md", [BookMap(book="某书", chapters=[Chapter("第 1 章 A", ["点A"])])])
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    (books_dir / "蒸馏-某书.md").write_text(
        "---\nbook: 某书\nsource: demo\n---\n\n### 第 1 章 A（L1–L10）\n\n正文\n", encoding="utf-8"
    )
    src_dir = tmp_path / "books" / "_src"
    src_dir.mkdir()
    (src_dir / "README.md").write_text("| 前缀 | 书 |\n|---|---|\n| demo | 某书 |\n", encoding="utf-8")
    (src_dir / "demo.txt").write_text("\n".join(f"第 {i} 行" for i in range(1, 21)), encoding="utf-8")

    class Stub:
        def complete(self, messages):
            return "讲解正文"

    monkeypatch.setattr(cli, "make_llm_completer", lambda **kw: Stub())
    board = cli._build_board(tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None)
    dash = Dashboard(directory, board=board)

    status, content_type, body = dash.handle_request(
        "POST", "/action/explain",
        body=json.dumps({"name": "点A"}).encode("utf-8"),
        content_type="application/json",
    )

    assert status == 200, body[:200]
    assert "json" in content_type
    payload = json.loads(body)
    assert payload["ok"] is True
    assert "讲解正文" in payload["output"]


def test_delete_task_accepts_json_request(tmp_path):
    from src import cli

    directory = make_directory(tmp_path)
    board = cli._build_board(tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None)
    dash = Dashboard(directory, board=board)

    status, content_type, body = dash.handle_request(
        "POST", "/action/delete_task",
        body=json.dumps({"when": "2026-09-27 10:00"}).encode("utf-8"),
        content_type="application/json",
    )

    assert status == 200
    assert "json" in content_type
    assert json.loads(body)["ok"] is True
    assert "做一个个人名片页" not in (directory / "tasks.md").read_text(encoding="utf-8")


def test_delete_task_json_failure_is_400(tmp_path):
    from src import cli

    directory = make_directory(tmp_path)
    board = cli._build_board(tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None)
    dash = Dashboard(directory, board=board)

    status, _ct, body = dash.handle_request(
        "POST", "/action/delete_task",
        body=json.dumps({"when": "1999-01-01 00:00"}).encode("utf-8"),
        content_type="application/json",
    )

    assert status == 400
    assert json.loads(body)["ok"] is False


def test_form_post_for_explain_still_303(tmp_path, monkeypatch):
    """无 JS 时 explain 仍然走表单路径（303），渐进增强不破。"""
    from src import cli

    directory = make_directory(tmp_path)
    board = cli._build_board(tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", directory / "tasks.md", None)
    dash = Dashboard(directory, board=board)

    status, _ct, _body = dash.handle_request(
        "POST", "/action/delete_task",
        body=b"when=2026-09-27+10%3A00",
        content_type="application/x-www-form-urlencoded",
    )

    assert status == 303


def test_panel_js_targets_explain_and_delete(tmp_path):
    directory = make_directory(tmp_path)
    page = TaskBoard(directory).pages()["tasks"]

    assert "/action/explain" in page
    assert "/action/delete_task" in page
    assert "explain-slot" in page