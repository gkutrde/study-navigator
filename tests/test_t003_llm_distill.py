"""T-003 失败测试：LLM 连通与提炼 prompt 雏形。

实现前编写（src/llm.py、src/distill.py 尚不存在），必须全部失败。
覆盖 T-003 的验收：给定一篇示例笔记文本，输出结构化知识点列表（名称+状态+证据）。

约定：
- 提示词只用「学过/做过/存疑」三态，与 [[模块-知识画像]] 一致，并声明不得臆断已掌握。
- 打桩 LLM 负责正常/异常路径；真实连通验证在任务卡的实测记录里，不进单元测试。
"""

from __future__ import annotations

import json

import pytest

from src import cli
from src.distill import (
    DISTILL_LEVELS,
    SAMPLE_NOTE,
    DistillError,
    build_distill_messages,
    distill_note,
    parse_knowledge_points,
)
from src.llm import LLMClient, LLMError, provider_config

DEEPSEEK_KEY = "deepseek_test_key_123456"
MOONSHOT_KEY = "moonshot_test_key_123456"
CODING_KEY = "coding_plan_test_key_123456"


class FakeCompleter:
    """打桩 LLM：按顺序返回预置回复，并记录收到的 messages。"""

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


def points_json(*points):
    return json.dumps(list(points), ensure_ascii=False)


@pytest.fixture(autouse=True)
def _no_real_kimi_login(monkeypatch):
    """把 provider 选择与本机真实的 Kimi Code CLI 登录态隔离：
    否则开发机上存在登录态时，T-003 的「缺 Key」用例会意外拿到登录态（T-011 之后才有这条路径）。"""
    monkeypatch.setattr("src.llm.load_cli_login", lambda *a, **k: None)


@pytest.fixture
def env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "LLM_PROVIDER=deepseek\n"
        "MOONSHOT_API_KEY=\n"
        "DEEPSEEK_API_KEY={}\n".format(DEEPSEEK_KEY),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def moonshot_env(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "LLM_PROVIDER=kimi\n"
        "MOONSHOT_API_KEY={}\n"
        "DEEPSEEK_API_KEY=\n".format(MOONSHOT_KEY),
        encoding="utf-8",
    )
    return path


# --- 1. provider 配置 --------------------------------------------------------


def test_provider_config_deepseek():
    cfg = provider_config("deepseek", {"DEEPSEEK_API_KEY": DEEPSEEK_KEY})

    assert "deepseek" in cfg.base_url
    assert cfg.model
    assert cfg.api_key == DEEPSEEK_KEY


def test_provider_config_kimi_uses_moonshot_key():
    cfg = provider_config("kimi", {"MOONSHOT_API_KEY": MOONSHOT_KEY})

    assert "moonshot" in cfg.base_url
    assert cfg.api_key == MOONSHOT_KEY


def test_provider_config_alias_accepts_moonshot_name():
    assert provider_config("moonshot", {"MOONSHOT_API_KEY": MOONSHOT_KEY}).api_key == MOONSHOT_KEY


def test_kimi_uses_live_coding_model_not_retired_moonshot_v1():
    """官方文档：moonshot-v1-* 已于 2026-08-31 下线，不能再作为默认模型。
    开放平台按量端点用 kimi-k2.7-code；coding 端点用 kimi-for-coding（T-011 实测）。"""
    cfg = provider_config("kimi", {"MOONSHOT_API_KEY": MOONSHOT_KEY})

    assert cfg.model == "kimi-k2.7-code"
    assert not cfg.model.startswith("moonshot-v1")


def test_kimi_coding_endpoint_model_is_kimi_for_coding():
    cfg = provider_config("kimi", {"KIMI_API_KEY": CODING_KEY})

    assert cfg.model == "kimi-for-coding"


def test_kimi_base_url_matches_official_openai_compatible_endpoint():
    cfg = provider_config("kimi", {"MOONSHOT_API_KEY": MOONSHOT_KEY})

    assert cfg.base_url == "https://api.moonshot.cn/v1"
    assert cfg.api_key_env == "MOONSHOT_API_KEY"


# --- 1b. Kimi coding plan（会员套餐）与开放平台按量是两个不同平台 -----------

def test_kimi_coding_plan_uses_kimi_api_key_and_coding_endpoint():
    """官方文档：Kimi Code 会员（coding plan）走 api.kimi.com/coding，Key 由 Kimi Code 控制台创建，
    与开放平台按量 Key 不通用。"""
    cfg = provider_config("kimi", {"KIMI_API_KEY": CODING_KEY})

    assert cfg.name == "kimi"
    assert cfg.base_url == "https://api.kimi.com/coding/v1"
    assert cfg.api_key == CODING_KEY
    assert cfg.api_key_env == "KIMI_API_KEY"
    assert cfg.model == "kimi-for-coding"


def test_kimi_coding_plan_accepts_provider_aliases():
    for alias in ("kimi-coding", "kimi_code", "coding"):
        cfg = provider_config(alias, {"KIMI_API_KEY": CODING_KEY})
        assert cfg.base_url == "https://api.kimi.com/coding/v1", alias


def test_kimi_base_url_can_be_overridden_by_env():
    cfg = provider_config("kimi", {"KIMI_API_KEY": CODING_KEY, "KIMI_BASE_URL": "https://proxy.internal/v1"})
    assert cfg.base_url == "https://proxy.internal/v1"


def test_kimi_falls_back_to_moonshot_key_for_open_platform():
    """没有 KIMI_API_KEY 但配了 MOONSHOT_API_KEY 时，按开放平台按量端点处理。"""
    cfg = provider_config("kimi", {"MOONSHOT_API_KEY": MOONSHOT_KEY})

    assert cfg.base_url == "https://api.moonshot.cn/v1"
    assert cfg.api_key == MOONSHOT_KEY
    assert cfg.api_key_env == "MOONSHOT_API_KEY"


def test_kimi_missing_key_names_all_three_options():
    """没有 Key、也没有 CLI 登录态时，报错要点出三条可选路径。"""
    with pytest.raises(LLMError) as exc:
        provider_config("kimi", {})
    message = str(exc.value)
    assert "KIMI_API_KEY" in message
    assert "MOONSHOT_API_KEY" in message
    assert "登录" in message


def test_resolve_provider_prefers_configured_then_available_key(tmp_path):
    from src.llm import resolve_provider

    only_coding = tmp_path / "a.env"
    only_coding.write_text("KIMI_API_KEY={}\n".format(CODING_KEY), encoding="utf-8")
    assert resolve_provider(None, only_coding) == "kimi"

    only_deepseek = tmp_path / "b.env"
    only_deepseek.write_text("DEEPSEEK_API_KEY={}\n".format(DEEPSEEK_KEY), encoding="utf-8")
    assert resolve_provider(None, only_deepseek) == "deepseek"


def test_llm_client_posts_to_coding_endpoint_with_coding_key():
    transport = FakeTransport([{"choices": [{"message": {"content": "ok"}}]}])
    client = LLMClient(provider_config("kimi", {"KIMI_API_KEY": CODING_KEY}), transport=transport)

    client.complete([{"role": "user", "content": "hi"}])

    call = transport.calls[0]
    assert call["url"] == "https://api.kimi.com/coding/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer " + CODING_KEY


def test_provider_config_unknown_provider_raises():
    with pytest.raises(LLMError) as exc:
        provider_config("openai", {"DEEPSEEK_API_KEY": DEEPSEEK_KEY})
    assert "openai" in str(exc.value)


def test_provider_config_missing_key_names_key_not_value(tmp_path):
    with pytest.raises(LLMError) as exc:
        provider_config("deepseek", {"DEEPSEEK_API_KEY": ""})
    message = str(exc.value)
    assert "DEEPSEEK_API_KEY" in message
    assert DEEPSEEK_KEY not in message


# --- 2. LLMClient：请求形状与错误处理 ---------------------------------------


def test_llm_client_uses_openai_compatible_chat_payload():
    transport = FakeTransport([{"choices": [{"message": {"content": "你好"}}]}])
    client = LLMClient(provider_config("deepseek", {"DEEPSEEK_API_KEY": DEEPSEEK_KEY}), transport=transport)

    reply = client.complete([{"role": "user", "content": "hi"}])

    assert reply == "你好"
    call = transport.calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/chat/completions")
    assert call["headers"]["Authorization"] == "Bearer " + DEEPSEEK_KEY
    assert call["json_body"]["model"]
    assert call["json_body"]["messages"] == [{"role": "user", "content": "hi"}]


def test_llm_client_network_error_raises_without_key():
    transport = FakeTransport([URLError("boom")])
    client = LLMClient(provider_config("deepseek", {"DEEPSEEK_API_KEY": DEEPSEEK_KEY}), transport=transport)

    with pytest.raises(LLMError) as exc:
        client.complete([{"role": "user", "content": "hi"}])

    assert DEEPSEEK_KEY not in str(exc.value)


def test_llm_client_http_error_message_has_no_key():
    transport = FakeTransport([{"error": {"message": "invalid api key", "code": "401"}}])
    client = LLMClient(provider_config("deepseek", {"DEEPSEEK_API_KEY": DEEPSEEK_KEY}), transport=transport)

    with pytest.raises(LLMError) as exc:
        client.complete([{"role": "user", "content": "hi"}])

    message = str(exc.value)
    assert "invalid api key" in message
    assert DEEPSEEK_KEY not in message


def test_llm_client_missing_choices_raises():
    transport = FakeTransport([{"choices": []}])
    client = LLMClient(provider_config("deepseek", {"DEEPSEEK_API_KEY": DEEPSEEK_KEY}), transport=transport)

    with pytest.raises(LLMError):
        client.complete([{"role": "user", "content": "hi"}])


def test_llm_client_repr_never_shows_key():
    client = LLMClient(provider_config("deepseek", {"DEEPSEEK_API_KEY": DEEPSEEK_KEY}))
    assert DEEPSEEK_KEY not in repr(client)


# --- 3. prompt 雏形 ----------------------------------------------------------


def test_build_distill_messages_includes_note_and_three_levels():
    messages = build_distill_messages("这是一篇笔记：Python 列表")

    assert messages[0]["role"] == "system"
    joined = "\n".join(m["content"] for m in messages)
    assert "Python 列表" in joined
    for level in DISTILL_LEVELS:
        assert level in joined
    assert "JSON" in joined.upper()


def test_build_distill_messages_carries_existing_profile_names():
    messages = build_distill_messages("笔记", existing_names=["列表", "字典"])

    joined = "\n".join(m["content"] for m in messages)
    assert "列表" in joined and "字典" in joined


def test_prompt_forbids_claiming_mastery():
    """模块笔记红线：不得把 LLM 的猜测当成已掌握事实。"""
    joined = "\n".join(m["content"] for m in build_distill_messages("笔记"))

    assert "存疑" in joined
    assert ("不要" in joined) or ("不得" in joined)


# --- 4. 解析 LLM 输出 -------------------------------------------------------


def test_parse_plain_json_array():
    raw = points_json(
        {"name": "列表", "level": "学过", "evidence": "列表用方括号", "topic": "Python 基础"}
    )

    points = parse_knowledge_points(raw)

    assert len(points) == 1
    assert points[0].name == "列表"
    assert points[0].level == "学过"
    assert points[0].evidence == "列表用方括号"
    assert points[0].topic == "Python 基础"


def test_parse_json_inside_code_fence():
    raw = "好的，这是结果：\n" + chr(96) * 3 + "json\n" + points_json(
        {"name": "字典", "level": "学过", "evidence": "用花括号"}
    ) + "\n" + chr(96) * 3

    points = parse_knowledge_points(raw)

    assert [p.name for p in points] == ["字典"]


def test_parse_wrapped_in_object_with_points_key():
    raw = json.dumps(
        {"points": [{"name": "循环", "level": "存疑", "evidence": "只提了一句"}]}, ensure_ascii=False
    )

    assert parse_knowledge_points(raw)[0].name == "循环"


def test_parse_empty_list_means_no_programming_points():
    assert parse_knowledge_points("[]") == []


def test_parse_invalid_level_raises():
    raw = points_json({"name": "列表", "level": "精通", "evidence": "x"})

    with pytest.raises(DistillError) as exc:
        parse_knowledge_points(raw)

    assert "精通" in str(exc.value)


def test_parse_missing_name_raises():
    raw = points_json({"level": "学过", "evidence": "x"})

    with pytest.raises(DistillError) as exc:
        parse_knowledge_points(raw)
    assert "name" in str(exc.value).lower()


def test_parse_missing_evidence_raises():
    raw = points_json({"name": "列表", "level": "学过"})

    with pytest.raises(DistillError) as exc:
        parse_knowledge_points(raw)
    assert "evidence" in str(exc.value).lower()


def test_parse_non_json_raises_actionable_error():
    with pytest.raises(DistillError) as exc:
        parse_knowledge_points("我觉得这篇笔记讲了列表和字典")
    assert "JSON" in str(exc.value)


# --- 5. distill_note：编排 --------------------------------------------------


def test_distill_note_fills_evidence_from_note_when_llm_gives_only_heading():
    """LLM 只回小节标题时，证据要落到该小节正文，而不是把标题本身当证据。"""
    completer = FakeCompleter(
        [points_json({"name": "列表", "level": "学过", "evidence": "## 列表"})]
    )

    points = distill_note(SAMPLE_NOTE, source="notes/demo.md", completer=completer)

    assert points[0].name == "列表"
    assert "方括号" in points[0].evidence


def test_distill_note_without_evidence_and_without_source_raises():
    completer = FakeCompleter([points_json({"name": "列表", "level": "学过", "evidence": ""})])

    with pytest.raises(DistillError) as exc:
        distill_note(SAMPLE_NOTE, completer=completer)
    assert "evidence" in str(exc.value).lower()


def test_distill_note_sends_note_text_and_no_key(monkeypatch):
    completer = FakeCompleter([points_json({"name": "列表", "level": "学过", "evidence": "e"})])

    distill_note(SAMPLE_NOTE, completer=completer)

    assert "列表" in completer.prompt_text()
    assert DEEPSEEK_KEY not in completer.prompt_text()


def test_distill_note_propagates_llm_error():
    completer = FakeCompleter([LLMError("额度不足")])

    with pytest.raises(DistillError) as exc:
        distill_note(SAMPLE_NOTE, completer=completer)
    assert "额度不足" in str(exc.value)


# --- 6. CLI：distill --------------------------------------------------------


def write_note(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text(SAMPLE_NOTE, encoding="utf-8")
    return path


def test_cli_distill_prints_structured_points(monkeypatch, tmp_path, env_file, capsys):
    note = write_note(tmp_path)
    completer = FakeCompleter(
        [
            points_json(
                {"name": "列表", "level": "学过", "evidence": "列表用方括号"},
                {"name": "字典", "level": "存疑", "evidence": "只提了一句"},
            )
        ]
    )
    monkeypatch.setattr(
        cli, "make_llm_completer", lambda env_path=None, **kwargs: completer
    )

    code = cli.main(["distill", str(note)], env_path=env_file)
    out = capsys.readouterr()

    assert code == 0
    assert "列表" in out.out and "学过" in out.out
    assert "字典" in out.out and "存疑" in out.out
    assert DEEPSEEK_KEY not in out.out + out.err


def test_cli_distill_json_flag_outputs_machine_readable(monkeypatch, tmp_path, env_file, capsys):
    note = write_note(tmp_path)
    completer = FakeCompleter(
        [points_json({"name": "列表", "level": "学过", "evidence": "e", "topic": "Python 基础"})]
    )
    monkeypatch.setattr(
        cli, "make_llm_completer", lambda env_path=None, **kwargs: completer
    )

    code = cli.main(["distill", str(note), "--json"], env_path=env_file)
    out = capsys.readouterr()

    assert code == 0
    payload = json.loads(out.out)
    assert payload[0]["name"] == "列表"
    assert payload[0]["level"] == "学过"
    assert payload[0]["topic"] == "Python 基础"


def test_cli_distill_missing_file_exits_2(monkeypatch, tmp_path, env_file, capsys):
    monkeypatch.setattr(cli, "make_llm_completer", lambda env_path=None: FakeCompleter([]))

    code = cli.main(["distill", str(tmp_path / "nope.md")], env_path=env_file)
    out = capsys.readouterr()

    assert code == 2
    assert "nope.md" in out.err


def test_cli_distill_no_points_reports_no_change(monkeypatch, tmp_path, env_file, capsys):
    note = write_note(tmp_path)
    completer = FakeCompleter(["[]"])
    monkeypatch.setattr(
        cli, "make_llm_completer", lambda env_path=None, **kwargs: completer
    )

    code = cli.main(["distill", str(note)], env_path=env_file)
    out = capsys.readouterr()

    assert code == 0
    assert "无可提炼" in out.err


def test_cli_distill_llm_failure_exits_1_without_key(monkeypatch, tmp_path, env_file, capsys):
    note = write_note(tmp_path)
    completer = FakeCompleter([LLMError("接口失败")])
    monkeypatch.setattr(
        cli, "make_llm_completer", lambda env_path=None, **kwargs: completer
    )

    code = cli.main(["distill", str(note)], env_path=env_file)
    out = capsys.readouterr()

    assert code == 1
    assert DEEPSEEK_KEY not in out.out + out.err


def test_usage_mentions_distill(monkeypatch, env_file, capsys):
    monkeypatch.setattr(cli, "make_llm_completer", lambda env_path=None: FakeCompleter([]))

    code = cli.main(["--help"], env_path=env_file)
    out = capsys.readouterr()

    assert code == 0
    assert "distill" in out.err


# --- 6b. provider 选择的集成行为（跨文件，容易只在真实运行时才暴露） ----------


def test_make_llm_completer_falls_back_when_preferred_key_missing(tmp_path, monkeypatch, capsys):
    """首选 provider 缺 Key 但另一个配了，必须降级而不是直接失败。"""
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "LLM_PROVIDER=kimi\nKIMI_API_KEY=\nDEEPSEEK_API_KEY={}\n".format(DEEPSEEK_KEY),
        encoding="utf-8",
    )

    completer = cli.make_llm_completer(env_path=env)
    err = capsys.readouterr().err

    assert completer.model == "deepseek-chat"
    assert "降级" in err


def test_make_llm_completer_uses_coding_plan_when_present(tmp_path, monkeypatch):
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "LLM_PROVIDER=kimi\nKIMI_API_KEY={}\n".format(CODING_KEY), encoding="utf-8"
    )

    completer = cli.make_llm_completer(env_path=env)

    # T-011 实测：coding 端点的可用模型是 kimi-for-coding
    assert completer.model == "kimi-for-coding"


def test_make_llm_completer_no_key_at_all_raises(tmp_path, monkeypatch):
    for name in ("KIMI_API_KEY", "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text("LLM_PROVIDER=deepseek\nDEEPSEEK_API_KEY=\n", encoding="utf-8")

    with pytest.raises(LLMError):
        cli.make_llm_completer(env_path=env)


class FakeTransport:
    """LLM 传输层打桩：记录请求并返回预置响应。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def request(self, method, url, *, headers=None, json_body=None, timeout=None):
        self.calls.append(
            {"method": method, "url": url, "headers": dict(headers or {}), "json_body": json_body}
        )
        if not self._responses:
            raise AssertionError("未预置的 LLM 请求")
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt() if callable(nxt) else nxt


from urllib.error import URLError  # noqa: E402  (放在末尾避免与 pytest 导入顺序混淆)