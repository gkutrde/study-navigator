"""T-007 失败测试：CLI 入口串联五个命令 + .env 加载与缺失凭证报错。

验收（[[04-任务与验收清单]] T-007）：五个命令可执行；缺凭证时明确报错退出。

注意：import 的格式细则与错误文案属于 T-010，本任务只保证它「接上且可执行」。
"""

from __future__ import annotations

import json

import pytest

from src import cli
from src.profile import KnowledgeProfile, write_profile_atomic
from src.distill import KnowledgePoint


COMMANDS = ("sync", "import", "distill", "next", "done")


# --- 1. 用法与命令表 ---------------------------------------------------------


def test_usage_lists_all_five_commands(capsys):
    code = cli.main(["--help"])
    out = capsys.readouterr()

    assert code == 0
    for command in COMMANDS:
        assert command in out.err


def test_known_commands_exposed_for_dispatch():
    assert set(COMMANDS) <= set(cli.KNOWN_COMMANDS)


def test_unknown_command_exits_2(capsys):
    code = cli.main(["frobnicate"])
    out = capsys.readouterr()

    assert code == 2
    assert "frobnicate" in out.err
    assert "用法" in out.err


def test_no_args_prints_usage_exits_2(capsys):
    code = cli.main([])
    out = capsys.readouterr()

    assert code == 2
    assert "用法" in out.err


# --- 2. 每个命令的参数校验（缺参数一律退出码 2，不崩） -----------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["sync"],
        ["sync", "a", "b"],
        ["import"],
        ["distill"],
        ["done"],
        ["done", "只有知识点"],
        ["next", "多余参数"],
    ],
)
def test_missing_or_extra_args_exit_2(argv, tmp_path, capsys):
    code = cli.main(argv, env_path=tmp_path / ".env", profile_path=tmp_path / "p" / "knowledge.md")
    out = capsys.readouterr()

    assert code == 2, argv
    assert "用法" in out.err


# --- 3. 缺凭证时明确报错（不崩、不静默） ------------------------------------


def test_sync_missing_credentials_names_key(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("FEISHU_APP_ID=x\n", encoding="utf-8")

    code = cli.main(
        ["sync", "NMq0wmqEDiRkiAk2d8acp7mHnVd"],
        env_path=env,
        notes_dir=tmp_path / "notes",
    )
    out = capsys.readouterr()

    assert code == 1
    assert "FEISHU_APP_SECRET" in out.err


def test_distill_missing_llm_config_names_option(tmp_path, monkeypatch, capsys):
    env = tmp_path / ".env"
    env.write_text("LLM_PROVIDER=deepseek\nDEEPSEEK_API_KEY=\n", encoding="utf-8")
    note = tmp_path / "n.md"
    note.write_text("# 笔记", encoding="utf-8")
    for name in ("KIMI_API_KEY", "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("src.llm.load_cli_login", lambda *a, **k: None)

    code = cli.main(["distill", str(note)], env_path=env, profile_path=tmp_path / "p" / "k.md")
    out = capsys.readouterr()

    assert code == 1
    assert "LLM" in out.err


# --- 4. import：接上且可执行（细则属 T-010） --------------------------------


def test_import_missing_books_file_exits_2(tmp_path, capsys):
    code = cli.main(["import", "不存在的书.md"], env_path=tmp_path / ".env", books_dir=tmp_path / "books")
    out = capsys.readouterr()

    assert code == 2
    assert "不存在的书" in out.err


def test_import_writes_syllabus_with_stubbed_llm(tmp_path, monkeypatch, capsys):
    books = tmp_path / "books"
    books.mkdir()
    (books / "python.md").write_text(
        "---\ntitle: Python 入门\n---\n\n# 第 4 章 函数\n函数定义与调用\n", encoding="utf-8"
    )
    profile_dir = tmp_path / "profile"
    completer = _StubCompleter(
        [json.dumps([{"chapter": "第 4 章", "points": ["函数", "参数"]}], ensure_ascii=False)]
    )
    monkeypatch.setattr(cli, "make_llm_completer", lambda **kwargs: completer)

    code = cli.main(
        ["import", "python.md"],
        env_path=tmp_path / ".env",
        books_dir=books,
        syllabus_path=profile_dir / "syllabus.md",
    )
    out = capsys.readouterr()

    assert code == 0
    target = profile_dir / "syllabus.md"
    assert target.is_file()
    text = target.read_text(encoding="utf-8")
    assert "Python 入门" in text
    assert "函数" in text


class _StubCompleter:
    def __init__(self, replies):
        self._replies = list(replies)

    def complete(self, messages):
        return self._replies.pop(0)


# --- 5. 命令之间不互相干扰 ---------------------------------------------------


def test_next_and_done_do_not_need_llm_credentials_for_validation(tmp_path, capsys):
    """参数错误应在加载凭证之前就返回，避免因为没配 Key 而给出误导性报错。"""
    code = cli.main(["done", "列表"], env_path=tmp_path / "nonexistent.env")
    out = capsys.readouterr()

    assert code == 2
    assert "用法" in out.err
