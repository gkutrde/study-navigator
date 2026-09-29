"""T-011 失败测试：复用 Kimi Code CLI 登录态（不走 API Key）。

验收（见 [[04-任务与验收清单]] T-011）：

- .env 不配任何 Kimi Key 时，也能借 CLI 登录态成功调用一次；
- 模型名以实测为准（登录态端点返回 kimi-for-coding 系列，不是 k2.7-code）；
- token 过期时给出明确中文提示，提示去 Kimi Code CLI 重新登录；不实现自动刷新。

实现前编写（src/cli_login.py 尚不存在），必须全部失败。
"""

from __future__ import annotations

import json
import time

import pytest

from src.cli_login import CliLogin, load_cli_login
from src.llm import LLMClient, LLMError, provider_config

# 假的 token，只用于断言「不会泄漏到输出/异常里」
FAKE_TOKEN = "fake-access-token-1234567890"
CODING_BASE = "https://api.kimi.com/coding/v1"


def write_login(home, token=FAKE_TOKEN, expires_in=3600, **extra):
    path = home / ".kimi-code" / "credentials" / "kimi-code.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "access_token": token,
        "refresh_token": "fake-refresh-token",
        "expires_at": int(time.time()) + expires_in,
        "expires_in": expires_in,
        "scope": "kimi-code",
        "token_type": "Bearer",
    }
    payload.update(extra)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def without_env_keys(monkeypatch):
    for name in ("KIMI_API_KEY", "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY", "LLM_PROVIDER", "KIMI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


class FakeTransport:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def request(self, method, url, *, headers=None, json_body=None, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": dict(headers or {}), "json_body": json_body})
        if not self._responses:
            raise AssertionError("未预置的 LLM 请求")
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt() if callable(nxt) else nxt


# --- 1. 读取登录态 -----------------------------------------------------------


def test_load_cli_login_reads_token_and_expiry(tmp_path):
    write_login(tmp_path, expires_in=1800)

    login = load_cli_login(home=tmp_path)

    assert login is not None
    assert login.access_token == FAKE_TOKEN
    assert login.token_type == "Bearer"
    assert login.scope == "kimi-code"
    assert login.is_expired() is False


def test_load_cli_login_missing_file_returns_none(tmp_path):
    assert load_cli_login(home=tmp_path) is None


def test_load_cli_login_broken_json_returns_none(tmp_path):
    path = tmp_path / ".kimi-code" / "credentials" / "kimi-code.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not-json", encoding="utf-8")

    assert load_cli_login(home=tmp_path) is None


def test_load_cli_login_without_access_token_returns_none(tmp_path):
    write_login(tmp_path, token="")
    assert load_cli_login(home=tmp_path) is None


def test_load_cli_login_expired_is_flagged(tmp_path):
    write_login(tmp_path, expires_in=-60)

    login = load_cli_login(home=tmp_path)

    assert login is not None
    assert login.is_expired() is True


def test_cli_login_repr_never_shows_token(tmp_path):
    write_login(tmp_path)
    login = load_cli_login(home=tmp_path)

    assert FAKE_TOKEN not in repr(login)
    assert FAKE_TOKEN not in str(login)


# --- 2. provider 选择：登录态优先于 API Key ---------------------------------


def test_provider_uses_cli_login_when_no_api_key(tmp_path, monkeypatch):
    """.env 不配任何 Kimi Key 时，也要能用登录态调用（T-011 的核心验收）。"""
    without_env_keys(monkeypatch)
    write_login(tmp_path)

    cfg = provider_config("kimi", {}, home=tmp_path)

    assert cfg.base_url == CODING_BASE
    assert cfg.api_key == FAKE_TOKEN
    assert cfg.api_key_env == "<Kimi Code CLI 登录态>"
    assert cfg.model == "kimi-for-coding"


def test_provider_model_is_live_coding_model(tmp_path, monkeypatch):
    """实测：登录态端点可用模型为 kimi-for-coding 系列，不是 k2.7-code。"""
    without_env_keys(monkeypatch)
    write_login(tmp_path)

    cfg = provider_config("kimi", {}, home=tmp_path)

    assert cfg.model in ("kimi-for-coding", "kimi-for-coding-highspeed")


def test_api_key_still_wins_over_login_state(tmp_path, monkeypatch):
    """显式配了 Key 时仍按 Key 走，避免悄悄改用登录态。"""
    without_env_keys(monkeypatch)
    write_login(tmp_path)

    cfg = provider_config("kimi", {"KIMI_API_KEY": "sk-explicit-key-123456"}, home=tmp_path)

    assert cfg.api_key == "sk-explicit-key-123456"
    assert cfg.api_key_env == "KIMI_API_KEY"


def test_expired_login_without_key_raises_actionable_chinese_hint(tmp_path, monkeypatch):
    without_env_keys(monkeypatch)
    write_login(tmp_path, expires_in=-120)

    with pytest.raises(LLMError) as exc:
        provider_config("kimi", {}, home=tmp_path)

    message = str(exc.value)
    assert "过期" in message
    assert "Kimi Code CLI" in message
    assert "重新登录" in message
    assert FAKE_TOKEN not in message


def test_expired_login_explicit_key_still_works(tmp_path, monkeypatch):
    """登录态过期但配了 Key 时，不该被登录态拦住。"""
    without_env_keys(monkeypatch)
    write_login(tmp_path, expires_in=-120)

    cfg = provider_config("kimi", {"KIMI_API_KEY": "sk-explicit-key-123456"}, home=tmp_path)

    assert cfg.api_key == "sk-explicit-key-123456"


def test_no_login_and_no_key_names_all_three_options(tmp_path, monkeypatch):
    without_env_keys(monkeypatch)

    with pytest.raises(LLMError) as exc:
        provider_config("kimi", {}, home=tmp_path)

    message = str(exc.value)
    assert "KIMI_API_KEY" in message
    assert "MOONSHOT_API_KEY" in message
    assert "登录" in message


# --- 3. 真调用形状 -----------------------------------------------------------


def test_client_calls_coding_endpoint_with_bearer_login_token(tmp_path, monkeypatch):
    without_env_keys(monkeypatch)
    write_login(tmp_path)
    transport = FakeTransport([{"choices": [{"message": {"content": "ok"}}]}])
    client = LLMClient(provider_config("kimi", {}, home=tmp_path), transport=transport)

    assert client.complete([{"role": "user", "content": "hi"}]) == "ok"

    call = transport.calls[0]
    assert call["url"] == CODING_BASE + "/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer " + FAKE_TOKEN
    assert call["json_body"]["model"] == "kimi-for-coding"


def test_login_state_auth_failure_message_does_not_leak_token(tmp_path, monkeypatch):
    without_env_keys(monkeypatch)
    write_login(tmp_path)
    transport = FakeTransport([{"error": {"message": "token expired or invalid", "type": "invalid_auth"}}])
    client = LLMClient(provider_config("kimi", {}, home=tmp_path), transport=transport)

    with pytest.raises(LLMError) as exc:
        client.complete([{"role": "user", "content": "hi"}])

    assert FAKE_TOKEN not in str(exc.value)

# --- 4. CLI：--provider 强制走登录态 ----------------------------------------


def test_cli_distill_provider_flag_forces_login_state(tmp_path, monkeypatch, capsys):
    """卡片口径是「.env 不配任何 Kimi Key 也能成功」；.env 里 LLM_PROVIDER 可能是 deepseek，
    所以要有办法显式指定走 kimi。"""
    from src import cli

    without_env_keys(monkeypatch)
    home = tmp_path / "home"
    write_login(home)
    env = tmp_path / ".env"
    env.write_text("LLM_PROVIDER=deepseek\nDEEPSEEK_API_KEY=sk-deepseek-fake-123456\n", encoding="utf-8")
    note = tmp_path / "note.md"
    note.write_text("# 笔记\n\n## 列表\n列表用方括号。\n", encoding="utf-8")

    captured = {}

    class Completer:
        def complete(self, messages):
            captured["messages"] = messages
            return '[{"name": "列表", "level": "学过", "evidence": "列表用方括号"}]'

    monkeypatch.setattr(
        cli, "make_llm_completer", lambda env_path=None, provider=None, home=None: Completer()
    )

    code = cli.main(["distill", str(note), "--provider", "kimi"], env_path=env, home=home)
    out = capsys.readouterr()

    assert code == 0
    assert "列表" in out.out
    assert FAKE_TOKEN not in out.out + out.err


def test_cli_distill_unknown_provider_flag_exits_2(tmp_path, monkeypatch, capsys):
    from src import cli

    without_env_keys(monkeypatch)
    note = tmp_path / "note.md"
    note.write_text("# 笔记", encoding="utf-8")

    code = cli.main(["distill", str(note), "--provider", "openai"], env_path=tmp_path / ".env")
    out = capsys.readouterr()

    assert code == 2
    assert "openai" in out.err


def test_cli_distill_reports_expired_login_clearly(tmp_path, monkeypatch, capsys):
    """.env 没 Key、登录态过期 → 退出码 1 + 中文提示去重新登录（T-011 验收项）。"""
    from src import cli

    without_env_keys(monkeypatch)
    home = tmp_path / "home"
    write_login(home, expires_in=-300)
    env = tmp_path / ".env"
    env.write_text("LLM_PROVIDER=kimi\n", encoding="utf-8")
    note = tmp_path / "note.md"
    note.write_text("# 笔记", encoding="utf-8")

    code = cli.main(["distill", str(note)], env_path=env, home=home)
    out = capsys.readouterr()

    assert code == 1
    assert "过期" in out.err
    assert "重新登录" in out.err
    assert FAKE_TOKEN not in out.out + out.err

# --- 5. 请求参数：coding 模型不接受 temperature=0 ----------------------------


def test_coding_model_request_omits_temperature_by_default(tmp_path, monkeypatch):
    """实测：kimi-for-coding 只接受 temperature=1，传 0 会 HTTP 400
    invalid temperature。默认不传该字段，交给服务端默认值。"""
    without_env_keys(monkeypatch)
    write_login(tmp_path)
    transport = FakeTransport([{"choices": [{"message": {"content": "ok"}}]}])
    client = LLMClient(provider_config("kimi", {}, home=tmp_path), transport=transport)

    client.complete([{"role": "user", "content": "hi"}])

    assert "temperature" not in transport.calls[0]["json_body"]


def test_explicit_temperature_still_sent_when_asked(tmp_path, monkeypatch):
    without_env_keys(monkeypatch)
    write_login(tmp_path)
    transport = FakeTransport([{"choices": [{"message": {"content": "ok"}}]}])
    client = LLMClient(provider_config("kimi", {}, home=tmp_path), transport=transport)

    client.complete([{"role": "user", "content": "hi"}], temperature=1)

    assert transport.calls[0]["json_body"]["temperature"] == 1


def test_deepseek_still_sends_temperature_zero(tmp_path, monkeypatch):
    """DeepSeek 没这个限制，保持确定性输出。"""
    without_env_keys(monkeypatch)
    transport = FakeTransport([{"choices": [{"message": {"content": "ok"}}]}])
    client = LLMClient(provider_config("deepseek", {"DEEPSEEK_API_KEY": "sk-deepseek-1234567890"}), transport=transport)

    client.complete([{"role": "user", "content": "hi"}])

    assert transport.calls[0]["json_body"]["temperature"] == 0
