"""T-001 失败测试：飞书最小连通验证。

本文件在实现之前编写，必须全部失败（模块尚不存在）。
它把 T-001 的验收标准翻译成可执行断言：

- 命令行能打印出指定文档正文的纯文本
- 测试文档是 wiki 节点，须先解析出 obj_token 再走 docx 接口
- 凭证只从 .env 读取，且不得出现在任何面向人的输出里
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from src import cli
from src.feishu import FeishuClient
from src.feishu import FeishuApiError
from src.credentials import CredentialError
from src.credentials import load_credentials

APP_ID = "cli_test_app_id"
APP_SECRET = "cli_test_app_secret"
WIKI_TOKEN = "NMq0wmqEDiRkiAk2d8acp7mHnVd"
DOCX_ID = "docxResolvedToken123"
BODY_TEXT = "Python 列表与字典\n\n列表用方括号，字典用花括号。"


class StubTransport:
    """记录请求并返回预置响应的假传输层。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, *, params=None, headers=None, json_body=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": dict(params or {}),
                "headers": dict(headers or {}),
                "json_body": json_body,
            }
        )
        if not self.responses:
            raise AssertionError(f"未预置的请求: {method} {url}")
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        # 允许传入工厂函数：每次请求都拿到全新的响应对象，避免用例间互相污染
        return nxt() if callable(nxt) else nxt


def ok(data):
    return {"code": 0, "msg": "success", "data": data}


# 每次调用都返回全新的响应对象：避免同一条 fixture 被多个用例共享而互相污染
def token_response():
    return ok({"tenant_access_token": "t-abc", "expire": 7200})


def wiki_ok_response():
    return ok({"node": {"obj_type": "docx", "obj_token": DOCX_ID}})


def content_response(text=BODY_TEXT):
    return ok({"content": text})


def blocks_response():
    """T-002 起 sync 会先拉块再取正文，CLI 用例需要预置这一页。"""
    return ok({"items": [], "has_more": False})


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    """写一份最小 .env，并把进程环境变量清干净。"""

    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    path = tmp_path / ".env"
    path.write_text(
        "# 凭证只放这里\n"
        f"FEISHU_APP_ID={APP_ID}\n"
        f"FEISHU_APP_SECRET={APP_SECRET}\n"
        "LLM_PROVIDER=kimi\n",
        encoding="utf-8",
    )
    return path


def happy_transport():
    return StubTransport([token_response(), wiki_ok_response(), content_response()])


# --- 输入解析：wiki 链接与 wiki token 的区分 ---------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        (f"https://zcn4eq1fppkv.feishu.cn/wiki/{WIKI_TOKEN}", WIKI_TOKEN),
        (f"https://zcn4eq1fppkv.feishu.cn/wiki/{WIKI_TOKEN}?from=from_copylink", WIKI_TOKEN),
        (f"https://zcn4eq1fppkv.feishu.cn/docx/{DOCX_ID}", DOCX_ID),
        (WIKI_TOKEN, WIKI_TOKEN),
    ],
)
def test_parse_document_ref_returns_token(raw, expected):
    assert cli.parse_document_ref(raw) == (expected, "/wiki/" in raw)


def test_parse_document_ref_flags_wiki_link(tmp_path):
    token, maybe_wiki = cli.parse_document_ref(f"https://x.feishu.cn/wiki/{WIKI_TOKEN}")
    assert (token, maybe_wiki) == (WIKI_TOKEN, True)


def test_parse_document_ref_empty_raises():
    with pytest.raises(ValueError):
        cli.parse_document_ref("   ")


# --- 凭证：只从 .env 读、缺失即报错、不泄露值 ---------------------------------


def test_load_credentials_reads_env_file(env_file):
    creds = load_credentials(env_path=env_file)
    assert creds.app_id == APP_ID
    assert creds.app_secret == APP_SECRET


def test_load_credentials_missing_file_raises(tmp_path):
    with pytest.raises(CredentialError) as exc:
        load_credentials(env_path=tmp_path / "nope.env")
    assert ".env" in str(exc.value)


def test_load_credentials_missing_key_names_key_not_value(tmp_path):
    path = tmp_path / ".env"
    path.write_text(f"FEISHU_APP_SECRET={APP_SECRET}\n", encoding="utf-8")
    with pytest.raises(CredentialError) as exc:
        load_credentials(env_path=path)
    message = str(exc.value)
    assert "FEISHU_APP_ID" in message
    assert APP_SECRET not in message


def test_load_credentials_blank_value_counts_as_missing(tmp_path):
    path = tmp_path / ".env"
    path.write_text("FEISHU_APP_ID=\nFEISHU_APP_SECRET=\n", encoding="utf-8")
    with pytest.raises(CredentialError):
        load_credentials(env_path=path)


def test_credentials_repr_never_shows_secret(env_file):
    creds = load_credentials(env_path=env_file)
    assert APP_SECRET not in repr(creds)


# --- 连通：wiki 节点先解析 obj_token，再取正文 --------------------------------


def test_resolve_node_token_for_wiki_returns_obj_token(env_file):
    transport = happy_transport()
    client = FeishuClient(load_credentials(env_path=env_file), transport=transport)

    docx_id = client.resolve_docx_token(WIKI_TOKEN, maybe_wiki=True)

    assert docx_id == DOCX_ID
    token_call, wiki_call = transport.calls[0], transport.calls[1]
    assert token_call["url"].endswith("/auth/v3/tenant_access_token/internal")
    assert token_call["json_body"]["app_id"] == APP_ID
    assert "/wiki/v2/spaces/get_node" in wiki_call["url"]
    assert wiki_call["params"]["token"] == WIKI_TOKEN
    assert wiki_call["headers"]["Authorization"] == "Bearer t-abc"


def test_resolve_node_token_non_wiki_skips_wiki_api(env_file):
    transport = happy_transport()
    client = FeishuClient(load_credentials(env_path=env_file), transport=transport)

    assert client.resolve_docx_token(DOCX_ID, maybe_wiki=False) == DOCX_ID
    # 非 wiki 输入是纯本地判定，不应发起任何请求
    assert transport.calls == []


def test_fetch_plain_text_returns_raw_content(env_file):
    transport = StubTransport([token_response(), content_response()])
    client = FeishuClient(load_credentials(env_path=env_file), transport=transport)

    text = client.fetch_plain_text(DOCX_ID)

    assert text == BODY_TEXT
    call = transport.calls[-1]
    assert f"/docx/v1/documents/{DOCX_ID}/raw_content" in call["url"]
    assert call["headers"]["Authorization"] == "Bearer t-abc"


def test_fetch_plain_text_strips_trailing_whitespace(env_file):
    transport = StubTransport([token_response(), content_response(f"{BODY_TEXT}\n\n  \n")])
    client = FeishuClient(load_credentials(env_path=env_file), transport=transport)

    assert client.fetch_plain_text(DOCX_ID) == BODY_TEXT


def test_token_is_cached_across_calls(env_file):
    transport = happy_transport()
    client = FeishuClient(load_credentials(env_path=env_file), transport=transport)

    client.resolve_docx_token(WIKI_TOKEN, maybe_wiki=True)
    client.fetch_plain_text(DOCX_ID)

    token_calls = [c for c in transport.calls if "tenant_access_token" in c["url"]]
    assert len(token_calls) == 1


# --- 失败路径：报错要指出文档 ID，且不覆盖半成品、不泄露凭证 -------------------


def test_wiki_node_without_obj_token_raises_with_token(env_file):
    transport = StubTransport([token_response(), ok({"node": {}})])
    client = FeishuClient(load_credentials(env_path=env_file), transport=transport)

    with pytest.raises(FeishuApiError) as exc:
        client.resolve_docx_token(WIKI_TOKEN, maybe_wiki=True)
    assert WIKI_TOKEN in str(exc.value)


def test_api_error_surfaces_code_and_document_id(env_file):
    transport = StubTransport(
        [token_response(), {"code": 131006, "msg": "permission denied", "data": {}}]
    )
    client = FeishuClient(load_credentials(env_path=env_file), transport=transport)

    with pytest.raises(FeishuApiError) as exc:
        client.resolve_docx_token(WIKI_TOKEN, maybe_wiki=True)
    message = str(exc.value)
    assert "131006" in message
    assert WIKI_TOKEN in message
    assert APP_SECRET not in message


def test_credentials_never_leak_into_request_headers_or_errors(env_file):
    transport = StubTransport([token_response(), {"code": 99991663, "msg": "invalid token", "data": {}}])
    client = FeishuClient(load_credentials(env_path=env_file), transport=transport)

    with pytest.raises(FeishuApiError) as exc:
        client.resolve_docx_token(WIKI_TOKEN, maybe_wiki=True)

    # 请求体里只允许出现在鉴权请求（POST body）中，且不得出现在错误消息与请求头里
    assert APP_SECRET not in str(exc.value)
    for call in transport.calls:
        assert APP_SECRET not in json.dumps(call["headers"], default=str)
        assert APP_SECRET not in str(call["params"])
        assert APP_SECRET not in str(call["url"])
    auth_calls = [c for c in transport.calls if "tenant_access_token" in c["url"]]
    assert len(auth_calls) == 1
    assert auth_calls[0]["json_body"]["app_secret"] == APP_SECRET


def test_network_failure_raises_api_error_without_credentials(env_file):
    transport = StubTransport([urllib.error.URLError("boom")])
    client = FeishuClient(load_credentials(env_path=env_file), transport=transport)

    with pytest.raises(FeishuApiError) as exc:
        client.fetch_plain_text(DOCX_ID)
    assert APP_SECRET not in str(exc.value)
    assert "t-abc" not in str(exc.value)


def test_permission_error_keeps_actionable_url(env_file):
    """飞书权限报错里带申请链接，截断不能把链接和后续排查信息吃掉。"""
    long_msg = (
        "Access denied. One of the following scopes is required: [wiki:wiki, wiki:node:read]. "
        "应用尚未开通所需的应用身份权限，点击链接申请并开通任一权限即可："
        "https://open.feishu.cn/app/cli_xxxxxxxxxxxxxxxx/store?tab=permission&source=apply_app_permission"
    )
    transport = StubTransport([token_response(), {"code": 99991672, "msg": long_msg, "data": {}}])
    client = FeishuClient(load_credentials(env_path=env_file), transport=transport)

    with pytest.raises(FeishuApiError) as exc:
        client.resolve_docx_token(WIKI_TOKEN, maybe_wiki=True)

    message = str(exc.value)
    assert "wiki:node:read" in message
    assert "https://open.feishu.cn/app/" in message


def test_auth_failure_message_names_key_hint(env_file):
    transport = StubTransport([{"code": 10003, "msg": "invalid app_secret", "data": {}}])
    client = FeishuClient(load_credentials(env_path=env_file), transport=transport)

    with pytest.raises(FeishuApiError) as exc:
        client.fetch_plain_text(DOCX_ID)
    assert APP_SECRET not in str(exc.value)


# --- CLI 端到端（打桩传输层） -------------------------------------------------


def run_cli(monkeypatch, env_file, transport, argv, capsys, notes_dir=None):
    monkeypatch.setattr(cli, "make_transport", lambda: transport)
    kwargs = {"env_path": env_file}
    if notes_dir is not None:
        kwargs["notes_dir"] = notes_dir
    code = cli.main(argv, **kwargs)
    return code, capsys.readouterr()


def test_cli_prints_plain_text_to_stdout(monkeypatch, env_file, tmp_path, capsys):
    transport = StubTransport(
        [token_response, wiki_ok_response, blocks_response, content_response]
    )
    code, out = run_cli(
        monkeypatch,
        env_file,
        transport,
        ["sync", f"https://zcn4eq1fppkv.feishu.cn/wiki/{WIKI_TOKEN}"],
        capsys,
        notes_dir=tmp_path / "notes",
    )
    assert code == 0
    assert BODY_TEXT in out.out
    assert "列表用方括号" in out.out


def test_cli_missing_credentials_prints_key_name_and_exits_1(monkeypatch, tmp_path, capsys):
    empty = tmp_path / ".env"
    empty.write_text("FEISHU_APP_ID=x\n", encoding="utf-8")
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    monkeypatch.setattr(cli, "make_transport", lambda: StubTransport([]))

    code = cli.main(["sync", WIKI_TOKEN], env_path=empty)
    out = capsys.readouterr()

    assert code == 1
    assert "FEISHU_APP_SECRET" in out.err
    assert "x" not in out.out


def test_cli_api_error_exits_nonzero_and_names_document_id(monkeypatch, env_file, capsys):
    transport = StubTransport(
        [token_response(), {"code": 131006, "msg": "permission denied", "data": {}}]
    )
    code, out = run_cli(monkeypatch, env_file, transport, ["sync", WIKI_TOKEN], capsys)

    assert code != 0
    assert WIKI_TOKEN in out.err
    assert APP_SECRET not in out.out + out.err


def test_cli_usage_error_exits_2(monkeypatch, env_file, capsys):
    monkeypatch.setattr(cli, "make_transport", lambda: StubTransport([]))
    code = cli.main(["sync"], env_path=env_file)
    out = capsys.readouterr()

    assert code == 2
    assert "用法" in out.err


def test_cli_never_prints_secret_on_success(monkeypatch, env_file, tmp_path, capsys):
    url = f"https://zcn4eq1fppkv.feishu.cn/wiki/{WIKI_TOKEN}"
    transport = StubTransport(
        [token_response, wiki_ok_response, blocks_response, content_response]
    )
    code, out = run_cli(monkeypatch, env_file, transport, ["sync", url], capsys, notes_dir=tmp_path / "notes")
    assert code == 0
    assert APP_SECRET not in out.out + out.err
    assert "t-abc" not in out.out + out.err


def test_cli_bare_token_is_treated_as_docx_id(monkeypatch, env_file, capsys):
    """裸 token 按文档 ID 处理（wiki 链接才是 wiki 节点），因此会走 docx 正文接口，
    这里用不匹配的桩响应证明该分支并给出可读错误。"""
    code, out = run_cli(monkeypatch, env_file, happy_transport(), ["sync", WIKI_TOKEN], capsys)

    assert code == 1
    assert WIKI_TOKEN in out.err
    assert APP_SECRET not in out.out + out.err