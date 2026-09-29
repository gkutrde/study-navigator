"""T-024 第二轮修复包：M-01 ~ M-05（每项先失败测试）。

M-01（P1 真 bug）看板「回写」按钮无参数入口：裸按钮但 done 要求 name+path，点了必失败。
M-02（P1 真 bug）统计区缺「输出」态：硬编码三态。
M-03 explain 无缓存：同名第二次仍调 LLM。
M-04 LLM 无重试：429/5xx/超时直接失败。
M-05 serve 端口占用抛 traceback。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.dashboard import TaskBoard, build_server
from src.distill import KnowledgePoint
from src.profile import KnowledgeProfile, write_profile_atomic


def make_profile(directory: Path, *pairs):
    write_profile_atomic(
        directory / "knowledge.md",
        KnowledgeProfile(points=[KnowledgePoint(n, lv, "e") for n, lv in pairs]),
    )


def make_board(tmp_path, *, tasks: str | None = None):
    directory = tmp_path / "profile"
    directory.mkdir(parents=True, exist_ok=True)
    (tmp_path / "notes").mkdir(exist_ok=True)
    if tasks is not None:
        (directory / "tasks.md").write_text(tasks, encoding="utf-8")
    return directory


TASKS_MD = """# 任务记录

## 2026-09-27 10:00

## 下一步任务

**目标**：做一个个人名片页

**用到的知识点**：标题与文本格式化标签、列表（ul/ol/li）

**新知识点**：超链接 a 标签（href/target）（本次唯一的新点）

**实现要点**：
1. a

**验收方式**：能看到
"""


# ================= M-01：看板「回写」按钮必须有参数入口 =================


def test_done_form_has_name_and_path_fields(tmp_path):
    directory = make_board(tmp_path, tasks=TASKS_MD)
    make_profile(directory, ("列表（ul/ol/li）", "学过"), ("标题与文本格式化标签", "学过"))
    board = TaskBoard(directory)

    page = board.pages()[""]

    match = re.search(r'<form[^>]*action="/action/done"[^>]*>(?P<body>.*?)</form>', page, re.S)
    assert match, "页面上必须有 done 表单"
    body = match.group("body")
    assert 'name="name"' in body, "done 表单必须能选/填知识点名"
    assert 'name="path"' in body, "done 表单必须有产出路径输入框"
    assert 'name="recite"' in body, "done 表单应带可选复述框"


def test_done_form_name_field_is_populated_from_latest_task(tmp_path):
    """下拉候选取自 tasks.md 最近一次任务涉及的知识点（含新点）。"""
    directory = make_board(tmp_path, tasks=TASKS_MD)
    make_profile(directory, ("列表（ul/ol/li）", "学过"), ("标题与文本格式化标签", "学过"))
    board = TaskBoard(directory)

    page = board.pages()[""]

    assert "标题与文本格式化标签" in page
    assert "列表（ul/ol/li）" in page
    assert "超链接 a 标签（href/target）" in page


def test_done_action_param_whitelist_allows_recite(tmp_path):
    directory = make_board(tmp_path)
    make_profile(directory, ("列表", "学过"))
    board = TaskBoard(directory)

    assert "recite" in board_action_keys("done")


def board_action_keys(action: str) -> frozenset:
    from src.dashboard import ACTION_PARAM_KEYS

    return ACTION_PARAM_KEYS[action]


def test_done_form_is_not_free_command_entry(tmp_path):
    """仍然是固定动作集：不加任何可输入命令的控件。"""
    directory = make_board(tmp_path, tasks=TASKS_MD)
    make_profile(directory, ("列表", "学过"))
    page = TaskBoard(directory).pages()[""]

    assert 'name="cmd"' not in page
    assert "<textarea" not in page or 'name="recite"' in page
    from src.dashboard import FIXED_ACTIONS

    forms = set(re.findall(r'action="/action/([a-z_]+)"', page))
    # 页面只能出现固定动作（+ status）；别把这名单硬编码，否则每加一个动作都要改测试
    assert forms <= set(FIXED_ACTIONS) | {"status"}


def test_done_with_missing_path_gives_readable_error(tmp_path, monkeypatch):
    """只填了知识点、没填产出路径时，要给出可读提示而不是崩。

    用真实的 _run_done 接线（与 serve 启动时一致），不走打桩。
    """
    from src import cli

    directory = make_board(tmp_path)
    make_profile(directory, ("列表", "学过"))
    board = cli._build_board(tmp_path / ".env", tmp_path / "notes", directory / "knowledge.md", None, None)

    result = board.run_action("done", {"name": "列表", "path": ""})

    assert not result.ok
    assert "产出" in result.output, result.output


# ================= M-02：统计区必须四态 =================


def test_stats_show_all_four_levels(tmp_path):
    directory = make_board(tmp_path)
    make_profile(directory, ("A", "学过"), ("B", "做过"), ("C", "输出"), ("D", "存疑"))
    board = TaskBoard(directory)

    page = board.pages()["knowledge"]
    stats = page[page.index('class="stats"') : page.index("</div></div>", page.index('class="stats"'))]

    for level in ("学过", "做过", "输出", "存疑"):
        assert f">{level} <b>" in stats or f"{level} <b>" in stats, f"统计区缺 {level}"


def test_stats_counts_are_correct(tmp_path):
    directory = make_board(tmp_path)
    make_profile(directory, ("A", "输出"), ("B", "输出"), ("C", "存疑"))
    board = TaskBoard(directory)

    page = board.pages()["knowledge"]
    stats_start = page.index('class="stats"')
    stats = page[stats_start : page.index("</div></div>", stats_start)]

    assert ">输出 <b>2</b>" in stats
    assert ">存疑 <b>1</b>" in stats
    assert ">学过 <b>0</b>" in stats


def test_stats_follow_levels_constant(tmp_path):
    """统计区要遍历 LEVELS，而不是硬编码——以后再加状态就不会漏。"""
    from src.profile import LEVELS

    directory = make_board(tmp_path)
    make_profile(directory, ("A", "学过"))
    page = TaskBoard(directory).pages()["knowledge"]
    stats_start = page.index('class="stats"')
    stats = page[stats_start : page.index("</div></div>", stats_start)]

    for level in LEVELS:
        assert f">{level} <b>" in stats


def test_stats_section_has_four_state_colors(tmp_path):
    directory = make_board(tmp_path)
    make_profile(directory, ("A", "输出"))
    page = TaskBoard(directory).pages()["knowledge"]

    for level in ("学过", "做过", "输出", "存疑"):
        assert f".level-{level}" in page

# ================= M-03：explain 缓存 =================


def test_explain_second_call_uses_cache(tmp_path):
    """同名知识点第二次 explain 应命中缓存，**零 LLM 调用**。"""
    from src.explain import explain_point
    from src.syllabus import BookMap, Chapter

    books = [BookMap(book="Demo", chapters=[Chapter("第 1 章 A", ["点A"])])]
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    (books_dir / "蒸馏-Demo.md").write_text(
        "---\nbook: Demo\nsource: demo\n---\n\n### 第 1 章 A（L1–L10）\n\n正文内容\n", encoding="utf-8"
    )
    cache_dir = tmp_path / "explanations"

    class Counting:
        def __init__(self):
            self.calls = 0

        def complete(self, messages):
            self.calls += 1
            return "讲解正文"

    completer = Counting()
    first = explain_point("点A", books, completer=completer, books_dir=books_dir,
                          src_dir=tmp_path / "nope", cache_dir=cache_dir)
    second = explain_point("点A", books, completer=completer, books_dir=books_dir,
                           src_dir=tmp_path / "nope", cache_dir=cache_dir)

    assert completer.calls == 1, "第二次不该再调 LLM"
    assert first.text == second.text == "讲解正文"
    assert second.from_cache is True
    assert first.from_cache is False


def test_explain_cache_writes_readable_file(tmp_path):
    from src.explain import explain_point
    from src.syllabus import BookMap, Chapter

    books = [BookMap(book="Demo", chapters=[Chapter("第 1 章 A", ["点A"])])]
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    (books_dir / "蒸馏-Demo.md").write_text(
        "---\nbook: Demo\nsource: demo\n---\n\n### 第 1 章 A（L1–L10）\n\n正文内容\n", encoding="utf-8"
    )
    cache_dir = tmp_path / "explanations"

    class Stub:
        def complete(self, messages):
            return "讲解正文"

    explain_point("点A", books, completer=Stub(), books_dir=books_dir,
                  src_dir=tmp_path / "nope", cache_dir=cache_dir)

    files = list(cache_dir.glob("*.md"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert "讲解正文" in text
    assert "出处" in text or "Demo" in text


def test_explain_refresh_bypasses_cache(tmp_path):
    from src.explain import explain_point
    from src.syllabus import BookMap, Chapter

    books = [BookMap(book="Demo", chapters=[Chapter("第 1 章 A", ["点A"])])]
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    (books_dir / "蒸馏-Demo.md").write_text(
        "---\nbook: Demo\nsource: demo\n---\n\n### 第 1 章 A（L1–L10）\n\n正文内容\n", encoding="utf-8"
    )
    cache_dir = tmp_path / "explanations"

    class Counting:
        def __init__(self):
            self.calls = 0

        def complete(self, messages):
            self.calls += 1
            return f"第{self.calls}次讲解"

    completer = Counting()
    explain_point("点A", books, completer=completer, books_dir=books_dir,
                  src_dir=tmp_path / "nope", cache_dir=cache_dir)
    refreshed = explain_point("点A", books, completer=completer, books_dir=books_dir,
                              src_dir=tmp_path / "nope", cache_dir=cache_dir, refresh=True)

    assert completer.calls == 2
    assert refreshed.text == "第2次讲解"


def test_explain_cache_dir_default_is_profile_explanations(tmp_path):
    from src.explain import default_cache_dir

    assert default_cache_dir(tmp_path / "profile").name == "explanations"


def test_explain_cache_handles_weird_point_names(tmp_path):
    """知识点名里有斜杠/冒号也不能写出危险路径。"""
    from src.explain import cache_path_for

    path = cache_path_for(tmp_path, "a/b:c*d?e")

    assert path.parent == tmp_path
    assert "/" not in path.name and ":" not in path.name


def test_cli_explain_refresh_flag(tmp_path, monkeypatch, capsys):
    from src import cli
    from src.syllabus import BookMap, Chapter, write_syllabus

    profile_dir = tmp_path / "profile"
    profile_dir.mkdir(parents=True)
    make_profile(profile_dir, ("点A", "学过"))
    write_syllabus(profile_dir / "syllabus.md", [BookMap(book="Demo", chapters=[Chapter("第 1 章 A", ["点A"])])])
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    (books_dir / "蒸馏-Demo.md").write_text(
        "---\nbook: Demo\nsource: demo\n---\n\n### 第 1 章 A（L1–L10）\n\n正文内容\n", encoding="utf-8"
    )

    calls = []

    class Stub:
        def complete(self, messages):
            calls.append(1)
            return "讲解"

    monkeypatch.setattr(cli, "make_llm_completer", lambda **kw: Stub())
    cli.main(["explain", "点A"], env_path=tmp_path / ".env", profile_path=profile_dir / "knowledge.md",
             books_dir=books_dir)
    cli.main(["explain", "点A"], env_path=tmp_path / ".env", profile_path=profile_dir / "knowledge.md",
             books_dir=books_dir)
    assert len(calls) == 1

    cli.main(["explain", "点A", "--refresh"], env_path=tmp_path / ".env",
             profile_path=profile_dir / "knowledge.md", books_dir=books_dir)
    assert len(calls) == 2

# ================= M-04：LLM 重试策略 =================


def make_client(transport):
    from src.llm import LLMClient

    return LLMClient(
        _cfg(),
        transport=transport,
    )


def _cfg():
    from src.llm import ProviderConfig

    return ProviderConfig(
        name="deepseek", base_url="https://example.invalid/v1", model="m",
        api_key="k", api_key_env="DEEPSEEK_API_KEY",
    )


def test_complete_retries_then_succeeds():
    from src.llm import LLMClient, TransientLLMError

    class Flaky:
        def __init__(self):
            self.calls = 0

        def request(self, *a, **kw):
            self.calls += 1
            if self.calls < 3:
                raise TransientLLMError("HTTP 503", status=503)
            return {"choices": [{"message": {"content": "好了"}}]}

    transport = Flaky()
    waits: list[float] = []
    client = make_client(transport)
    client._config = _cfg()

    text = client.complete([{"role": "user", "content": "x"}], sleep=waits.append)

    assert text == "好了"
    assert transport.calls == 3
    assert waits == [1.0, 2.0]  # 指数退避


def test_complete_gives_up_after_max_retries():
    from src.llm import LLMError, TransientLLMError

    class AlwaysDown:
        def __init__(self):
            self.calls = 0

        def request(self, *a, **kw):
            self.calls += 1
            raise TransientLLMError("HTTP 500", status=500)

    transport = AlwaysDown()
    waits: list[float] = []
    client = make_client(transport)

    with pytest.raises(LLMError) as exc:
        client.complete([{"role": "user", "content": "x"}], sleep=waits.append)

    assert transport.calls == 3, "首次 + 2 次重试"
    assert waits == [1.0, 2.0]
    assert "重试" in str(exc.value)


def test_quota_error_is_not_retried():
    """额度型 429 重试没意义：一次失败就直接给中文提示。"""
    from src.llm import LLMError

    class Quota:
        def __init__(self):
            self.calls = 0

        def request(self, *a, **kw):
            self.calls += 1
            raise LLMError("LLM 额度或配额不足（HTTP 429）：insufficient balance")

    transport = Quota()
    client = make_client(transport)

    with pytest.raises(LLMError) as exc:
        client.complete([{"role": "user", "content": "x"}], sleep=lambda _s: None)

    assert transport.calls == 1, "不该重试"
    assert "额度" in str(exc.value) or "配额" in str(exc.value)


def test_transport_classifies_429_as_transient_unless_quota():
    from src.llm import looks_like_quota_problem

    assert looks_like_quota_problem("insufficient balance")
    assert looks_like_quota_problem("You exceeded your current quota")
    assert not looks_like_quota_problem("rate limit exceeded")


def test_bad_request_is_not_retried():
    from src.llm import LLMError

    class Bad:
        def __init__(self):
            self.calls = 0

        def request(self, *a, **kw):
            self.calls += 1
            raise LLMError("LLM 返回 HTTP 400：invalid temperature")

    transport = Bad()
    client = make_client(transport)

    with pytest.raises(LLMError):
        client.complete([{"role": "user", "content": "x"}], sleep=lambda _s: None)

    assert transport.calls == 1


# ================= M-05：serve 端口被占用给中文提示 =================


def test_serve_reports_bind_failure_without_traceback(tmp_path, capsys, monkeypatch):
    """端口绑定失败时要给中文提示，不要抛 traceback。

    这里用打桩而不是真占端口：实测 Windows 上 HTTPServer 默认 allow_reuse_address=True，
    真占端口反而会被"抢占"成功（见 M-05 的实测记录），测不出失败路径。
    """
    import src.dashboard as dashboard
    from src import cli

    def boom(*a, **kw):
        raise OSError(10048, "only one usage of each socket address is normally permitted")

    monkeypatch.setattr(dashboard, "build_server", boom)
    code = cli.main(["serve", "--port", "8765", "--no-browser"], profile_path=tmp_path / "k.md")
    out = capsys.readouterr()

    assert code == 1
    assert "端口" in out.err
    assert "Traceback" not in out.err


def test_server_does_not_hijack_an_occupied_port(tmp_path):
    """T-024 M-05 实测：allow_reuse_address=True 在 Windows 上会**抢占**已被占用的端口。

    两个服务同时跑同一个端口是更隐蔽的坑，所以显式关掉它；
    代价是重启后可能遇到 TIME_WAIT（那是可接受的）。
    """
    from src.dashboard import DashboardServer

    assert getattr(DashboardServer, "allow_reuse_address", False) is False