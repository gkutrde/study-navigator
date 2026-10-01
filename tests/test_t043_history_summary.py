"""T-043 失败测试：chat 历史摘要压缩（超长不再硬裁）。

现在超 30000 字符是**硬裁**：最旧轮次直接丢掉，
于是第 11 轮问起第 1 轮的结论时模型已经看不见了。

改成：最旧轮次先交 LLM 压成 ≤500 字摘要块，再拼进 prompt；
摘要缓存进 chat.md，避免每轮重压。
"""
from __future__ import annotations

import pathlib

import pytest

from src.chat_session import (
    MAX_PROMPT_CHARS,
    SUMMARY_BUDGET,
    ChatTurn,
    append_turn,
    build_prompt,
    load_summary,
    load_turns,
    save_summary,
)


@pytest.fixture(autouse=True)
def _clear_summary_cache():
    """摘要有进程内缓存，用例之间必须隔离（否则上一条的缓存会把下一条"假绿"）。"""
    from src import chat_session

    chat_session._SUMMARY_MEMO.clear()
    yield
    chat_session._SUMMARY_MEMO.clear()


def filler(n_chars: int, tag: str) -> str:
    return (tag + "：") + ("内容" * (n_chars // 2))[:n_chars]


def long_history(rounds: int = 12, chars: int = 4000):
    turns = []
    for index in range(1, rounds + 1):
        turns.append(ChatTurn(role="user", text=filler(chars, f"第{index}轮问题")))
        turns.append(ChatTurn(role="assistant", text=filler(chars, f"第{index}轮回答")))
    return turns


# ---------- 摘要常量与存储 ----------


def test_summary_budget_is_500():
    assert SUMMARY_BUDGET == 500


def test_save_and_load_summary_roundtrip(tmp_path):
    directory = tmp_path / "profile"
    directory.mkdir(parents=True)

    save_summary(directory, "2026-09-27 10:00", "第一轮聊了列表缩进", upto=4)
    got = load_summary(directory, "2026-09-27 10:00")

    assert got is not None
    assert "列表缩进" in got.text
    assert got.upto == 4, "要记住摘要覆盖到第几轮，避免重复压缩"


def test_summary_survives_reload(tmp_path):
    directory = tmp_path / "profile"
    directory.mkdir(parents=True)
    save_summary(directory, "2026-09-27 10:00", "摘要内容", upto=6)

    # 再写一轮对话（会重写留档文件）
    append_turn(directory, "2026-09-27 10:00", role="user", text="新问题")

    got = load_summary(directory, "2026-09-27 10:00")
    assert got is not None and "摘要内容" in got.text, "摘要不能被后续写档冲掉"


def test_load_summary_returns_none_when_absent(tmp_path):
    directory = tmp_path / "profile"
    directory.mkdir(parents=True)

    assert load_summary(directory, "2026-09-27 10:00") is None


def test_summary_is_human_readable_in_archive(tmp_path):
    directory = tmp_path / "profile"
    directory.mkdir(parents=True)
    save_summary(directory, "2026-09-27 10:00", "聊了缩进", upto=2)

    from src.chat_session import archive_path

    text = archive_path(directory, "2026-09-27 10:00").read_text(encoding="utf-8")
    assert "聊了缩进" in text, "摘要要落进留档（人可读）"
    assert "摘要" in text


def test_summary_does_not_break_turn_parsing(tmp_path):
    """摘要块不能被当成一轮对话读回来（T-035 标题分隔符那个坑的同类）。"""
    directory = tmp_path / "profile"
    directory.mkdir(parents=True)
    append_turn(directory, "2026-09-27 10:00", role="user", text="问一")
    append_turn(directory, "2026-09-27 10:00", role="assistant", text="答一")
    save_summary(directory, "2026-09-27 10:00", "摘要：聊了列表", upto=2)

    turns = load_turns(directory, "2026-09-27 10:00")

    assert len(turns) == 2, "摘要是独立块，不该多切出轮次"
    assert turns[0].text == "问一"


# ---------- prompt 组装 ----------


def test_short_history_unchanged():
    """没超限时行为完全不变（不能把正常路径搞乱）。"""
    turns = [ChatTurn(role="user", text="问"), ChatTurn(role="assistant", text="答")]
    prompt = build_prompt("上下文", turns, "新问题")

    assert "之前的对话" in prompt
    assert "摘要" not in prompt
    assert "已裁剪" not in prompt


def test_long_history_uses_summary_not_hard_trim():
    """超长时要给摘要块，而不是只写"已裁剪 N 轮"。"""
    turns = long_history(rounds=12)

    def summarizer(old_turns):
        return "前 10 轮：学生一直在练列表缩进，最后确认了「点号后要加空格」。", len(old_turns)

    prompt = build_prompt("上下文", turns, "第 12 轮问题", summarizer=summarizer)

    assert "点号后要加空格" in prompt, "摘要内容必须进 prompt"
    assert "【较早对话摘要】" in prompt or "摘要" in prompt
    assert len(prompt) <= MAX_PROMPT_CHARS + 2000, "不能因为摘要把 prompt 撑爆"


def test_oldest_turns_replaced_by_summary():
    """最旧的轮次被摘要替代，但最新几轮原文保留。

    注意轮数要真的超限：12 轮 × 4000 字约 24000，在 30000 以内**根本不会压**，
    这个测试第一版就是这么假绿的。
    """
    turns = long_history(rounds=20)
    calls = []

    def summarizer(old_turns):
        calls.append(old_turns)
        return "早期摘要", len(old_turns)

    prompt = build_prompt("上下文", turns, "第 12 轮问题", summarizer=summarizer)

    assert calls, "应当调用过摘要器"
    assert "早期摘要" in prompt
    assert "第20轮回答" in prompt, "最近的轮次必须原文保留"
    assert "第1轮回答" not in prompt, "最旧的轮次应当已被摘要替代"


def test_summarizer_only_called_for_overflow():
    """摘要要缓存：同一批旧轮次不该被反复压缩。"""
    turns = long_history(rounds=20)
    seen = []

    def summarizer(old_turns):
        seen.append(tuple(id(t) for t in old_turns))
        return "摘要", len(old_turns)

    build_prompt("上下文", turns, "问题一", summarizer=summarizer)
    first = len(seen)
    build_prompt("上下文", turns, "问题二", summarizer=summarizer)

    assert first >= 1, "第一次要压"
    assert len(seen) == first, "第二次不该再压（缓存命中）"


def test_cached_summary_is_reused(tmp_path):
    """带 profile_dir 时，摘要落盘后再拼 prompt 不再调摘要器。"""
    directory = tmp_path / "profile"
    directory.mkdir(parents=True)
    when = "2026-09-27 10:00"
    turns = long_history(rounds=12)
    calls = []

    def summarizer(old_turns):
        calls.append(1)
        return "落盘摘要", len(old_turns)

    build_prompt("上下文", turns, "问题一", summarizer=summarizer, profile_dir=directory, when=when)
    assert len(calls) == 1
    assert load_summary(directory, when) is not None, "摘要要落盘"

    build_prompt("上下文", turns, "问题二", summarizer=summarizer, profile_dir=directory, when=when)
    assert len(calls) == 1, "第二次应当命中落盘缓存"


def test_no_summarizer_falls_back_to_trimming():
    """没有摘要器时退回硬裁（保证老调用方不崩）。"""
    turns = long_history(rounds=12)

    prompt = build_prompt("上下文", turns, "问题")

    assert "已裁剪" in prompt


def test_handoff_never_trimmed_even_with_summary():
    """接力上下文永远全文保留（T-034 的硬约束）。"""
    turns = long_history(rounds=12)
    context = "接力上下文全文" * 100

    prompt = build_prompt(
        context, turns, "问题", summarizer=lambda old: ("摘要", len(old))
    )

    assert context in prompt


# ---------- 验收：10 轮长对话后仍能引用第 1 轮结论 ----------


def test_acceptance_11th_round_can_reference_round_1():
    """验收：10 轮长对话后第 11 轮仍能"引用"第 1 轮结论。

    做法：第 1 轮给一个具体结论；摘要器（模拟 LLM）保留它；
    第 11 轮的 prompt 里必须能看到那个结论。
    """
    conclusion = "结论：index.html 里 ul 的缩进要用两个空格"
    turns = [ChatTurn(role="user", text="第一轮问题"), ChatTurn(role="assistant", text=conclusion)]
    for index in range(2, 11):
        turns.append(ChatTurn(role="user", text=filler(4000, f"第{index}轮问题")))
        turns.append(ChatTurn(role="assistant", text=filler(4000, f"第{index}轮回答")))

    def summarizer(old_turns):
        joined = " ".join(t.text for t in old_turns)
        keep = conclusion if conclusion in joined else "（早期内容已概括）"
        return keep, len(old_turns)

    prompt = build_prompt("上下文", turns, "第 11 轮：我第一轮的结论是什么？", summarizer=summarizer)

    assert conclusion in prompt, "第 11 轮必须还能看到第 1 轮的结论"
    assert "第11轮" in prompt or "第 11 轮" in prompt

# ---------- 摘要器本体（LLM 包装） ----------


class StubCompleter:
    def __init__(self, reply="摘要内容", raises=None):
        self.reply = reply
        self.raises = raises
        self.calls = []

    def complete(self, messages):
        self.calls.append(str(messages))
        if self.raises:
            raise self.raises
        return self.reply


def test_summarizer_returns_text_and_upto():
    from src.chat_session import build_summarizer

    completer = StubCompleter("  早期结论：缩进用两空格  ")
    summarizer = build_summarizer(completer)
    turns = [ChatTurn(role="user", text="问"), ChatTurn(role="assistant", text="答")]

    text, upto = summarizer(turns)

    assert "缩进用两空格" in text
    assert upto == 2, "要报告覆盖了几轮"
    assert completer.calls, "要真的调用 LLM"


def test_summarizer_enforces_budget():
    from src.chat_session import build_summarizer

    completer = StubCompleter("很长的内容" * 500)
    summary, _ = build_summarizer(completer)(
        [ChatTurn(role="user", text="问")]
    )

    assert len(summary) <= SUMMARY_BUDGET


def test_summarizer_prompt_asks_to_keep_conclusions():
    from src.chat_session import build_summarizer

    completer = StubCompleter("摘要")
    build_summarizer(completer)([ChatTurn(role="user", text="问")])

    sent = completer.calls[0]
    assert "结论" in sent, "要让模型保留结论（不然第 11 轮引用不到第 1 轮）"
    assert str(SUMMARY_BUDGET) in sent, "要告诉它字数上限"


def test_summarizer_failure_falls_back_instead_of_raising():
    from src.chat_session import build_summarizer

    completer = StubCompleter(raises=RuntimeError("API 挂了"))
    text, upto = build_summarizer(completer)(
        [ChatTurn(role="user", text="第一轮的关键结论")]
    )

    assert "第一轮的关键结论" in text, "压不动时至少保住原文开头"
    assert upto == 1


def test_summarizer_empty_reply_falls_back():
    from src.chat_session import build_summarizer

    text, _ = build_summarizer(StubCompleter("   "))(
        [ChatTurn(role="user", text="原始内容")]
    )

    assert "原始内容" in text


# ---------- 接线：CLI 两条路径都要带摘要器 ----------


def test_op_chat_passes_summarizer_and_cache():
    """面板那一轮必须传 summarizer + profile_dir/when（否则摘要不落盘）。"""
    body = pathlib.Path("src/cli.py").read_text(encoding="utf-8")

    assert "build_summarizer" in body
    assert "profile_dir=target.parent" in body
    assert "summarizer=summarizer" in body


def test_repl_chat_passes_summarizer():
    body = pathlib.Path("src/cli.py").read_text(encoding="utf-8")

    assert "repl_summarizer" in body, "REPL 也要带摘要器"
    assert "summarizer=repl_summarizer" in body


def test_cli_falls_back_when_llm_unavailable():
    """拿不到 LLM 时不该让整轮问答挂掉（退回硬裁）。"""
    body = pathlib.Path("src/cli.py").read_text(encoding="utf-8")

    assert body.count("summarizer = None") + body.count("repl_summarizer = None") >= 2