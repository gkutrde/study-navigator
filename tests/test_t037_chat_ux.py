"""T-037 失败测试（一）：markdown 渲染 + XSS 转义 + 只读文件端点。

客户反馈：回答是纯文本、文件点不开。但渲染 HTML 意味着**注入面**变大了，
所以这批测试一半是在锁"能渲染"，另一半是在锁"渲染不出来的东西必须出不来"。
"""
from __future__ import annotations

import pathlib
import urllib.parse

import pytest


def make_profile_dir(tmp_path):
    from src.profile import KnowledgeProfile, KnowledgePoint, write_profile_atomic

    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    write_profile_atomic(directory / "knowledge.md", KnowledgeProfile(points=[
        KnowledgePoint("列表（ul/ol/li）", "学过", "e", topic="网页基础"),
    ]))
    (directory / "tasks.md").write_text(
        "# 任务记录\n\n## 2026-09-27 10:00\n\n**目标**：做名片页\n\n**验收方式**：显示姓名\n",
        encoding="utf-8",
    )
    return directory


def render_turn(directory, when, role, text):
    """把一轮对话写进留档，再渲染成卡片 HTML（走真实面板）。"""
    from src.chat_session import append_turn
    from src.dashboard import TaskBoard

    append_turn(directory, when, role=role, text=text)
    return TaskBoard(directory).pages()["tasks"]


# ---------- ① markdown 渲染 ----------


def test_assistant_answer_renders_headings(tmp_path):
    directory = make_profile_dir(tmp_path)

    page = render_turn(directory, "2026-09-27 10:00", "assistant",
                       "## 结论\n\n先说重点。\n\n### 细项\n\n- 一\n- 二")

    assert "<h2>结论</h2>" in page
    assert "<h3>细项</h3>" in page
    assert "<li>一</li>" in page


def test_assistant_answer_renders_fenced_code(tmp_path):
    directory = make_profile_dir(tmp_path)

    page = render_turn(directory, "2026-09-27 10:00", "assistant",
                       "改一行：\n\n```python\nprint(f\"{i}. {name}\")\n```")

    assert "<pre><code>" in page
    assert "print(f" in page


def test_assistant_answer_renders_table(tmp_path):
    directory = make_profile_dir(tmp_path)

    page = render_turn(directory, "2026-09-27 10:00", "assistant",
                       "| 项 | 结果 |\n| --- | --- |\n| 缩进 | PASS |")

    assert "<table>" in page
    assert "<th>结果</th>" in page
    assert "<td>PASS</td>" in page


def test_assistant_answer_renders_bold(tmp_path):
    directory = make_profile_dir(tmp_path)

    page = render_turn(directory, "2026-09-27 10:00", "assistant", "这是 **重点** 内容")

    assert "<strong>重点</strong>" in page


def test_markdown_is_not_plain_text_anymore(tmp_path):
    """不能把整段 markdown 原样塞在 <pre> 或裸文本里。"""
    directory = make_profile_dir(tmp_path)

    page = render_turn(directory, "2026-09-27 10:00", "assistant", "## 标题")

    assert "## 标题" not in page, "星号/井号不该原样出现在页面上"


# ---------- ② 用户输入必须转义（XSS） ----------


def test_user_html_is_escaped(tmp_path):
    """用户输入一律转义——这是看板的注入面，绝不能渲染。"""
    directory = make_profile_dir(tmp_path)

    page = render_turn(directory, "2026-09-27 10:00", "user",
                       "<script>alert(1)</script>")

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_user_markdown_is_not_rendered(tmp_path):
    """用户输入即使长得像 markdown 也不渲染（只转义展示）。"""
    directory = make_profile_dir(tmp_path)

    page = render_turn(directory, "2026-09-27 10:00", "user", "## 我不是标题")

    assert "<h2>我不是标题</h2>" not in page
    assert "## 我不是标题" in page


def test_user_img_onerror_is_escaped(tmp_path):
    directory = make_profile_dir(tmp_path)

    page = render_turn(directory, "2026-09-27 10:00", "user",
                       '<img src=x onerror=alert(1)>')

    assert "<img src=x" not in page
    assert "&lt;img" in page


def test_assistant_script_tag_is_escaped_too(tmp_path):
    """回答里的 script 也不能执行（模型可能被带偏）。"""
    directory = make_profile_dir(tmp_path)

    page = render_turn(directory, "2026-09-27 10:00", "assistant",
                       "<script>alert(9)</script>")

    assert "<script>alert(9)</script>" not in page
    assert "&lt;script&gt;" in page


# ---------- ③ 只读文件端点 ----------


def test_file_endpoint_serves_project_file(tmp_path):
    from src.dashboard import Dashboard, TaskBoard

    directory = make_profile_dir(tmp_path)
    board = Dashboard(directory, board=TaskBoard(directory, project_root=tmp_path))
    (tmp_path / "profile" / "notes.md").write_text("正文内容", encoding="utf-8")

    status, _ct, body = board.handle_request("GET", "/file?path=profile/notes.md")

    assert status == 200
    assert "正文内容" in body


def test_file_endpoint_rejects_parent_traversal(tmp_path):
    from src.dashboard import Dashboard, TaskBoard

    directory = make_profile_dir(tmp_path)
    board = Dashboard(directory, board=TaskBoard(directory, project_root=tmp_path))
    (tmp_path.parent / "outside.txt").write_text("外面的秘密", encoding="utf-8")

    for bad in ("../outside.txt", "profile/../../outside.txt", "..\\outside.txt"):
        status, _ct, body = board.handle_request(
            "GET", "/file?path=" + urllib.parse.quote(bad)
        )
        assert status == 400, f"{bad} 应被拒绝"
        assert "外面的秘密" not in body


def test_file_endpoint_rejects_absolute_path(tmp_path):
    from src.dashboard import Dashboard, TaskBoard

    directory = make_profile_dir(tmp_path)
    board = Dashboard(directory, board=TaskBoard(directory, project_root=tmp_path))

    status, _ct, _b = board.handle_request(
        "GET", "/file?path=" + urllib.parse.quote("C:/Windows/win.ini")
    )

    assert status == 400


def test_file_endpoint_404_for_missing(tmp_path):
    from src.dashboard import Dashboard, TaskBoard

    directory = make_profile_dir(tmp_path)
    board = Dashboard(directory, board=TaskBoard(directory, project_root=tmp_path))

    status, _ct, _b = board.handle_request("GET", "/file?path=profile/nope.md")

    assert status == 404


def test_file_endpoint_400_without_path(tmp_path):
    from src.dashboard import Dashboard, TaskBoard

    directory = make_profile_dir(tmp_path)
    board = Dashboard(directory, board=TaskBoard(directory, project_root=tmp_path))

    status, _ct, _b = board.handle_request("GET", "/file")

    assert status == 400


def test_file_endpoint_does_not_serve_outside_root(tmp_path):
    """符号链接/绝对路径都要挡在项目根之外。"""
    from src.dashboard import Dashboard, TaskBoard

    directory = make_profile_dir(tmp_path)
    board = Dashboard(directory, board=TaskBoard(directory, project_root=tmp_path))

    status, _ct, body = board.handle_request("GET", "/file?path=/etc/passwd")

    assert status == 400
    assert "root:" not in body


# ---------- ④ 路径变成可点链接 ----------


def test_project_paths_become_links(tmp_path):
    directory = make_profile_dir(tmp_path)

    page = render_turn(directory, "2026-09-27 10:00", "assistant",
                       "看 profile/knowledge.md 里的记录")

    assert "/file?path=profile/knowledge.md" in page
    assert "href=" in page


def test_non_project_paths_stay_plain(tmp_path):
    directory = make_profile_dir(tmp_path)

    page = render_turn(directory, "2026-09-27 10:00", "assistant",
                       "打开 C:/Windows/win.ini 看看")

    assert "/file?path=C" not in page

# ---------- T-037（二）：思考过程（stderr 推理流） ----------


def test_chat_once_returns_thinking_from_stderr(monkeypatch):
    """思考流在 stderr，**不能混进 stdout**（否则会被当成答案正文）。"""
    import subprocess

    import src.chat as chat

    monkeypatch.setattr(
        chat.subprocess, "run",
        lambda command, **kw: subprocess.CompletedProcess(
            command, 0, "最终答案\n", "先看验收单\n再对照代码\n"
        ),
    )

    result = chat.chat_once("dsh", "问题")

    assert result.answer == "最终答案\n"
    assert "先看验收单" in result.thinking
    assert "先看验收单" not in result.answer, "思考不能混进答案"


def test_chat_once_is_backward_compatible(monkeypatch):
    """老调用方拿到的是字符串（T-032/T-034 的既有行为不能破）。"""
    import subprocess

    import src.chat as chat

    monkeypatch.setattr(
        chat.subprocess, "run",
        lambda command, **kw: subprocess.CompletedProcess(command, 0, "答案", ""),
    )

    assert chat.chat_once("dsh", "问题") == "答案" or hasattr(
        chat.chat_once("dsh", "问题"), "answer"
    )


def test_chat_once_strips_ansi_from_thinking(monkeypatch):
    """stderr 里常带 ANSI 颜色码，要清掉再展示。"""
    import subprocess

    import src.chat as chat

    monkeypatch.setattr(
        chat.subprocess, "run",
        lambda command, **kw: subprocess.CompletedProcess(command, 0, "答案", "\x1b[32m思考中\x1b[0m\n"),
    )

    result = chat.chat_once("dsh", "问题")

    assert "\x1b[" not in result.thinking
    assert "思考中" in result.thinking


def test_chat_once_empty_stderr_gives_empty_thinking(monkeypatch):
    import subprocess

    import src.chat as chat

    monkeypatch.setattr(
        chat.subprocess, "run",
        lambda command, **kw: subprocess.CompletedProcess(command, 0, "答案", ""),
    )

    assert chat.chat_once("dsh", "问题").thinking == ""


def test_thinking_is_archived_and_shown_folded(tmp_path):
    """思考要进留档（可回看），面板里是默认折叠的块。"""
    from src.chat_session import append_turn, load_turns
    from src.dashboard import TaskBoard
    from src.profile import KnowledgeProfile, write_profile_atomic

    directory = tmp_path / "profile"
    directory.mkdir(parents=True)
    write_profile_atomic(directory / "knowledge.md", KnowledgeProfile())
    (directory / "tasks.md").write_text(
        "# 任务记录\n\n## 2026-09-27 10:00\n\n**目标**：x\n\n**验收方式**：y\n",
        encoding="utf-8",
    )

    append_turn(directory, "2026-09-27 10:00", role="assistant", text="答案", thinking="我在想\n第二行")

    turns = load_turns(directory, "2026-09-27 10:00")
    assert turns[0].thinking.startswith("我在想"), "思考要留在留档里"

    page = TaskBoard(directory).pages()["tasks"]
    assert "<details" in page, "思考块要可折叠"
    assert "思考过程" in page
    assert "我在想" in page
    assert "<details" in page and "open" not in page.split("chat-thinking")[1][:80], "默认折叠"


def test_turn_without_thinking_has_no_details(tmp_path):
    from src.chat_session import append_turn
    from src.dashboard import TaskBoard
    from src.profile import KnowledgeProfile, write_profile_atomic

    directory = tmp_path / "profile"
    directory.mkdir(parents=True)
    write_profile_atomic(directory / "knowledge.md", KnowledgeProfile())
    (directory / "tasks.md").write_text(
        "# 任务记录\n\n## 2026-09-27 10:00\n\n**目标**：x\n\n**验收方式**：y\n",
        encoding="utf-8",
    )
    append_turn(directory, "2026-09-27 10:00", role="assistant", text="只有答案")

    page = TaskBoard(directory).pages()["tasks"]

    assert "思考过程" not in page


def test_thinking_roundtrip_survives_headings_in_content(tmp_path):
    """思考里带 # 也不能把留档切乱（T-035 的老坑）。"""
    from src.chat_session import append_turn, load_turns

    directory = tmp_path / "profile"
    directory.mkdir(parents=True)
    append_turn(directory, "2026-09-27 10:00", role="assistant", text="答案",
                thinking="## 我在想\n### 再想")

    turns = load_turns(directory, "2026-09-27 10:00")

    assert len(turns) == 1
    assert "## 我在想" in turns[0].thinking
    assert turns[0].text.strip() == "答案"

def test_file_endpoint_works_when_profile_is_in_subdir(tmp_path):
    """画像放在子目录时也要能解析 profile/xxx（浏览器验收踩过的 404）。"""
    from src.dashboard import Dashboard, TaskBoard
    from src.profile import KnowledgeProfile, write_profile_atomic

    (tmp_path / "README.md").write_text("# 项目", encoding="utf-8")
    nested = tmp_path / "profile" / "_scratch"
    nested.mkdir(parents=True)
    write_profile_atomic(nested / "knowledge.md", KnowledgeProfile())

    board = TaskBoard(nested)
    assert board.project_root == tmp_path.resolve(), "要往上找到真正的项目根"

    dashboard = Dashboard(nested, board=board)
    status, _ct, body = dashboard.handle_request("GET", "/file?path=profile/_scratch/knowledge.md")

    assert status == 200, "子目录里的画像也要能读到"
    assert "知识画像" in body


def test_project_root_prefers_readme_marker(tmp_path):
    from src.dashboard import TaskBoard

    (tmp_path / "README.md").write_text("# 根", encoding="utf-8")
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)

    assert TaskBoard(deep).project_root == tmp_path.resolve()