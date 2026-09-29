"""T-012 失败测试：本地只读看板（serve 命令）。

验收（[[04-任务与验收清单]] T-012）：

- 启动后浏览器访问 localhost 能看到画像与任务列表；
- **无任何写接口**（只读）；
- 停服后文件无改动；
- 只用标准库 http.server，绑定 localhost；
- 样式从简，留白给客户自己美化。

实现前编写（src/dashboard.py 尚不存在），必须全部失败。
"""

from __future__ import annotations

import http.client
import socket
import threading
import time
from pathlib import Path

import pytest

from src.dashboard import (
    Dashboard,
    build_pages,
    build_server,
    markdown_to_html,
    render_page,
)
from src.distill import KnowledgePoint
from src.profile import KnowledgeProfile, write_profile_atomic


def make_files(tmp_path):
    profile = tmp_path / "profile"
    write_profile_atomic(
        profile / "knowledge.md",
        KnowledgeProfile(
            points=[
                KnowledgePoint("列表", "学过", "笔记：列表用方括号", "Python 基础"),
                KnowledgePoint("字典", "做过", "产出：out.py", "Python 基础"),
            ]
        ),
    )
    (profile / "tasks.md").write_text(
        "# 任务记录\n\n## 2026-09-26 10:00\n\n## 下一步任务\n\n**目标**：写通讯录\n\n**验收方式**：能存盘\n",
        encoding="utf-8",
    )
    return profile


@pytest.fixture
def files(tmp_path):
    return make_files(tmp_path)


# --- 1. markdown → HTML（保守转换 + 转义） ---------------------------------


def test_markdown_to_html_headings_and_paragraphs():
    html = markdown_to_html("# 标题\n\n正文一段")

    assert "<h1>标题</h1>" in html
    assert "<p>正文一段</p>" in html


def test_markdown_to_html_lists_and_code_and_table():
    md = "## 主题\n\n- 甲\n- 乙\n\n" + chr(96) * 3 + "python\nx = 1\n" + chr(96) * 3 + "\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n"

    html = markdown_to_html(md)

    assert "<li>甲</li>" in html
    assert "x = 1" in html
    assert "<table>" in html and "<td>1</td>" in html


def test_markdown_to_html_escapes_script_tags():
    """本地文件内容也要转义，绝不能把 <script> 直接塞进页面。"""
    html = markdown_to_html("正文 <script>alert(1)</script>")

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_markdown_to_html_escapes_html_in_table_cells():
    html = markdown_to_html("| a |\n| --- |\n| <img src=x onerror=1> |\n")

    assert "<img" not in html


# --- 2. 页面渲染 -----------------------------------------------------------


def test_render_page_has_expected_structure():
    page = render_page("标题", "<p>内容</p>")

    assert "<!DOCTYPE html>" in page
    assert "<title>标题</title>" in page
    assert "<p>内容</p>" in page
    assert "charset" in page.lower()


def test_build_pages_lists_profile_and_tasks(files):
    pages = build_pages(files)

    assert "" in pages or "index" in pages
    index = pages.get("") or pages.get("index")
    assert "知识画像" in index
    assert "任务" in index


def test_build_pages_profile_page_shows_points(files):
    pages = build_pages(files)
    html = pages.get("knowledge") or pages.get("profile") or pages.get("")

    assert "列表" in html
    assert "学过" in html
    assert "字典" in html


def test_build_pages_tasks_page_shows_task(files):
    pages = build_pages(files)
    html = pages.get("tasks") or ""

    assert "写通讯录" in html


def test_build_pages_missing_files_are_reported_not_crashed(tmp_path):
    pages = build_pages(tmp_path / "profile")

    html = pages.get("") or pages.get("index")
    assert "还没有" in html or "不存在" in html


def test_build_pages_includes_syllabus_when_present(files):
    (files / "syllabus.md").write_text("# 知识地图\n\n## Python 入门\n\n### 第 4 章\n\n- 函数\n", encoding="utf-8")

    pages = build_pages(files)

    assert "syllabus" in pages
    assert "函数" in pages["syllabus"]


# --- 3. 只读保证 -----------------------------------------------------------


def test_dashboard_rejects_write_methods(files):
    dash = Dashboard(files)

    for method in ("POST", "PUT", "DELETE", "PATCH"):
        status = dash.handle_request(method, "/")
        assert status[0] == 405, method


def test_dashboard_only_serves_get(files):
    dash = Dashboard(files)

    status, content_type, body = dash.handle_request("GET", "/")

    assert status == 200
    assert "text/html" in content_type
    assert body


def test_dashboard_unknown_path_returns_404(files):
    dash = Dashboard(files)

    status = dash.handle_request("GET", "/nope")[0]

    assert status == 404


def test_dashboard_does_not_write_any_file(files):
    """停服后（以及服务期间）文件必须原样不动。"""
    before = {p.name: p.read_text(encoding="utf-8") for p in files.glob("*.md")}
    dash = Dashboard(files)

    for path in ("/", "/knowledge", "/tasks", "/syllabus", "/nope"):
        dash.handle_request("GET", path)
        dash.handle_request("POST", path)

    after = {p.name: p.read_text(encoding="utf-8") for p in files.glob("*.md")}
    assert after == before
    assert list(files.glob("*.tmp")) == []


def test_dashboard_reports_profile_mtime(files):
    dash = Dashboard(files)
    page = dash.handle_request("GET", "/")[2]

    assert "刷新" in page or "更新时间" in page or "生成于" in page


# --- 4. 服务器绑定与端到端 -------------------------------------------------


def test_build_server_binds_localhost_only(files):
    server = build_server(files, port=0)
    try:
        host, port = server.server_address[:2]
        assert host in ("127.0.0.1", "localhost")
        assert port > 0
    finally:
        server.server_close()


def test_server_serves_real_http_request(files):
    server = build_server(files, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        conn.close()

        assert response.status == 200
        assert "知识画像" in body
    finally:
        server.shutdown()
        server.server_close()


def test_server_rejects_post_over_http(files):
    server = build_server(files, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("POST", "/", body=b"x=1")
        response = conn.getresponse()
        response.read()
        conn.close()

        assert response.status == 405
    finally:
        server.shutdown()
        server.server_close()


# --- 5. CLI ---------------------------------------------------------------


def test_cli_serve_help_and_usage(capsys):
    from src import cli

    code = cli.main(["--help"])
    out = capsys.readouterr()

    assert code == 0
    assert "serve" in out.err
    assert "serve" in cli.KNOWN_COMMANDS


def test_cli_serve_rejects_bad_port(tmp_path, capsys):
    from src import cli

    code = cli.main(["serve", "--port", "abc"], profile_path=tmp_path / "profile" / "knowledge.md")
    out = capsys.readouterr()

    assert code == 2
    assert "端口" in out.err


def test_cli_serve_starts_and_stops(files, monkeypatch, capsys):
    """用真端口起服，验证能访问且退出后文件未变（T-012 验收）。"""
    from src import cli
    import src.dashboard as dash_mod

    before = {p.name: p.read_text(encoding="utf-8") for p in files.glob("*.md")}
    started = {}

    def fake_serve_forever(self):
        started["port"] = self.server_address[1]
        raise KeyboardInterrupt  # 模拟 Ctrl+C 停服

    monkeypatch.setattr(dash_mod.DashboardServer, "serve_forever", fake_serve_forever)

    code = cli.main(["serve", "--port", "0", "--no-browser"], profile_path=files / "knowledge.md")
    out = capsys.readouterr()

    assert code == 0
    assert started["port"] > 0
    assert "http://127.0.0.1:" in out.err
    after = {p.name: p.read_text(encoding="utf-8") for p in files.glob("*.md")}
    assert after == before
