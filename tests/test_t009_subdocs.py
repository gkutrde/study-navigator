"""T-009 失败测试：sync 子文档递归（父+全部子文档；无权子文档跳过并报出 ID）。

验收（[[04-任务与验收清单]] T-009 / A-01 完整版）：

- 给定文档 ID，递归拉取其全部子文档，落盘为本地 markdown；
- 无权/失败的子文档跳过并报出其 ID，已成功的部分保留；
- 父文档失败要保留已有文件。

实现前编写（fetch_wiki_children / sync_document_tree 尚不存在），必须全部失败。
"""

from __future__ import annotations

import pytest

from src.feishu import FeishuApiError, FeishuClient
from src.sync import sync_document_tree

ROOT_WIKI = "rootWikiToken001"
CHILD_A = "childWikiTokenA1"
CHILD_B = "childWikiTokenB2"
GRANDCHILD = "grandWikiTokenC3"
DOC_A = "docxChildA"
DOC_B = "docxChildB"
DOC_G = "docxGrandC"
DOC_ROOT = "docxRoot001"


# 请求顺序约定（实现按此顺序发起）：
#   1) 换 token  2) get_node(根)  3) blocks(根)  4) 列举子节点
#   5) blocks(子) …每个子文档一次；只有当子节点只剩 token（文档提及兜底）时才多一次 get_node
class StubTransport:
    def __init__(self, responses):
        self._factories = list(responses)
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
        if not self._factories:
            raise AssertionError("未预置的请求: {} {}".format(method, url))
        nxt = self._factories.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt() if callable(nxt) else nxt

    def urls(self):
        return [c["url"] for c in self.calls]


def ok(data):
    return {"code": 0, "msg": "success", "data": data}


def token_response():
    return ok({"tenant_access_token": "t-abc", "expire": 7200})


def node_response(wiki_token, obj_token, has_child=False, obj_type="docx"):
    def factory():
        return ok(
            {
                "node": {
                    "node_token": wiki_token,
                    "obj_token": obj_token,
                    "obj_type": obj_type,
                    "has_child": has_child,
                    "space_id": "sp1",
                }
            }
        )

    return factory


def children_response(items, has_more=False, page_token=None):
    def factory():
        data = {"items": items, "has_more": has_more}
        if page_token:
            data["page_token"] = page_token
        return ok(data)

    return factory


def child_item(wiki_token, obj_token, title, has_child=False, obj_type="docx"):
    return {
        "node_token": wiki_token,
        "obj_token": obj_token,
        "obj_type": obj_type,
        "has_child": has_child,
        "title": title,
        "space_id": "sp1",
    }


def blocks_page(items=None):
    def factory():
        return ok({"items": items or [], "has_more": False})

    return factory


def text_block(content, block_id="b"):
    """一个只含纯文本的段落块。"""
    return {
        "block_id": block_id,
        "block_type": 2,
        "text": {"elements": [{"text_run": {"content": content}}], "style": {}},
    }


def content_response(text):
    def factory():
        return ok({"content": text})

    return factory


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    path = tmp_path / ".env"
    path.write_text("FEISHU_APP_ID=a\nFEISHU_APP_SECRET=b\n", encoding="utf-8")
    return path


def make_client(env_file, transport):
    from src.credentials import load_credentials

    return FeishuClient(load_credentials(env_path=env_file), transport=transport)


# --- 1. 列举子节点 -----------------------------------------------------------


def test_fetch_wiki_children_paginates(env_file):
    transport = StubTransport(
        [
            token_response,
            children_response(
                [child_item(CHILD_A, DOC_A, "笔记A")], has_more=True, page_token="p2"
            ),
            children_response([child_item(CHILD_B, DOC_B, "笔记B")]),
        ]
    )
    client = make_client(env_file, transport)

    children = client.fetch_wiki_children("sp1", "rootNodeToken")

    assert [c.node_token for c in children] == [CHILD_A, CHILD_B]
    assert children[0].obj_token == DOC_A
    assert transport.calls[1]["params"]["parent_node_token"] == "rootNodeToken"
    assert transport.calls[1]["params"]["page_size"] >= 50
    assert transport.calls[2]["params"]["page_token"] == "p2"


def test_fetch_wiki_children_requires_items(env_file):
    transport = StubTransport([token_response, lambda: ok({"has_more": False})])
    client = make_client(env_file, transport)

    with pytest.raises(FeishuApiError):
        client.fetch_wiki_children("sp1", "rootNodeToken")


def test_fetch_wiki_children_surfaces_permission_error_with_scope_hint(env_file):
    """实测：列举子节点要 wiki:node:retrieve（与单节点读取的 wiki:node:read 不同）。"""
    transport = StubTransport(
        [
            token_response,
            lambda: {
                "code": 99991672,
                "msg": "Access denied. One of the following scopes is required: [wiki:wiki, wiki:node:retrieve]",
                "data": {},
            },
        ]
    )
    client = make_client(env_file, transport)

    with pytest.raises(FeishuApiError) as exc:
        client.fetch_wiki_children("sp1", "rootNodeToken")
    assert "99991672" in str(exc.value)


# --- 2. 递归拉取 -------------------------------------------------------------


def test_sync_tree_writes_parent_and_children(tmp_path, env_file):
    transport = StubTransport(
        [
            token_response,
            node_response(ROOT_WIKI, DOC_ROOT, has_child=True),
            blocks_page(),
            children_response([child_item(CHILD_A, DOC_A, "笔记A"), child_item(CHILD_B, DOC_B, "笔记B")]),
            blocks_page(items=[text_block("子文档A正文", "bA")]),
            blocks_page(items=[text_block("子文档B正文", "bB")]),
        ]
    )
    client = make_client(env_file, transport)
    notes = tmp_path / "notes"

    result = sync_document_tree(client, ROOT_WIKI, notes)

    assert result.root.is_file()
    assert len(result.children) == 2
    names = sorted(p.name for p in result.children)
    assert names == sorted([CHILD_A + ".md", CHILD_B + ".md"])
    texts = [p.read_text(encoding="utf-8") for p in result.children]
    assert any("子文档A正文" in t for t in texts)
    assert any("子文档B正文" in t for t in texts)
    assert result.skipped == []


def test_sync_tree_recurses_into_grandchildren(tmp_path, env_file):
    transport = StubTransport(
        [
            token_response,
            node_response(ROOT_WIKI, DOC_ROOT, has_child=True),
            blocks_page(),
            children_response([child_item(CHILD_A, DOC_A, "A", has_child=True)]),
            blocks_page(),
            children_response([child_item(GRANDCHILD, DOC_G, "G")]),
            blocks_page(items=[text_block("G 正文", "bG")]),
            content_response("未使用"),
        ]
    )
    client = make_client(env_file, transport)

    result = sync_document_tree(client, ROOT_WIKI, tmp_path / "notes")

    assert len(result.children) == 2
    assert any(p.name == GRANDCHILD + ".md" for p in result.children)
    assert "G 正文" in (tmp_path / "notes" / (GRANDCHILD + ".md")).read_text(encoding="utf-8")


def test_sync_tree_skips_forbidden_child_and_reports_id(tmp_path, env_file):
    """无权子文档要跳过并报出 ID，已成功的部分保留。"""
    transport = StubTransport(
        [
            token_response,
            node_response(ROOT_WIKI, DOC_ROOT, has_child=True),
            blocks_page(),
            children_response([child_item(CHILD_A, DOC_A, "A"), child_item(CHILD_B, DOC_B, "B")]),
            blocks_page(items=[text_block("A 正文", "bA")]),
            lambda: {"code": 131006, "msg": "permission denied", "data": {}},
        ]
    )
    client = make_client(env_file, transport)

    result = sync_document_tree(client, ROOT_WIKI, tmp_path / "notes")

    assert len(result.children) == 1
    assert result.skipped and result.skipped[0][0] == CHILD_B
    # 跳过原因要能定位是哪篇：报出文档/节点 ID
    assert DOC_B in result.skipped[0][1] or CHILD_B in result.skipped[0][1]
    assert result.root.is_file()


def test_sync_tree_child_failure_keeps_existing_child_file(tmp_path, env_file):
    notes = tmp_path / "notes"
    notes.mkdir()
    existing = notes / (CHILD_A + ".md")
    existing.write_text("旧的子文档内容", encoding="utf-8")

    transport = StubTransport(
        [
            token_response,
            node_response(ROOT_WIKI, DOC_ROOT, has_child=True),
            blocks_page(),
            children_response([child_item(CHILD_A, DOC_A, "A")]),
            lambda: {"code": 131006, "msg": "denied", "data": {}},
        ]
    )
    client = make_client(env_file, transport)

    result = sync_document_tree(client, ROOT_WIKI, notes)

    assert existing.read_text(encoding="utf-8") == "旧的子文档内容"
    assert result.skipped[0][0] == CHILD_A
    assert DOC_A in result.skipped[0][1] or CHILD_A in result.skipped[0][1]


def test_sync_tree_root_failure_does_not_write(tmp_path, env_file):
    transport = StubTransport(
        [token_response, lambda: {"code": 131006, "msg": "denied", "data": {}}]
    )
    client = make_client(env_file, transport)
    notes = tmp_path / "notes"

    with pytest.raises(FeishuApiError):
        sync_document_tree(client, ROOT_WIKI, notes)

    assert not notes.exists() or list(notes.glob("*.md")) == []


def test_sync_tree_respects_max_depth(tmp_path, env_file):
    transport = StubTransport(
        [
            token_response,
            node_response(ROOT_WIKI, DOC_ROOT, has_child=True),
            blocks_page(),
            children_response([child_item(CHILD_A, DOC_A, "A", has_child=True)]),
            blocks_page(),
        ]
    )
    client = make_client(env_file, transport)

    result = sync_document_tree(client, ROOT_WIKI, tmp_path / "notes", max_depth=1)

    assert len(result.children) == 1
    # 达到深度上限后不应再列举子节点的子节点
    assert not any("/nodes" in url and i > 3 for i, url in enumerate(transport.urls()))


# --- 3. 兜底：从父文档的文档提及发现子文档（实测路径） ----------------------


def test_sync_tree_falls_back_to_mentions_when_children_api_forbidden(tmp_path, env_file):
    """实测：应用缺 wiki:node:retrieve 时列举子节点会 99991672。
    此时退化为「读父文档块里的文档提及 token」，逐个解析后继续递归。"""
    parent_blocks = [
        {
            "block_id": "b1",
            "block_type": 2,
            "text": {
                "elements": [
                    {"text_run": {"content": ""}, "mention_doc": {"token": CHILD_A, "obj_type": 16, "title": "A"}},
                ],
                "style": {},
            },
        }
    ]
    transport = StubTransport(
        [
            token_response,
            node_response(ROOT_WIKI, DOC_ROOT, has_child=True),
            blocks_page(parent_blocks),
            lambda: {
                "code": 99991672,
                "msg": "Access denied. required: [wiki:node:retrieve]",
                "data": {},
            },
            node_response(CHILD_A, DOC_A),
            blocks_page(items=[text_block("A 正文（来自提及发现）", "bA")]),
            content_response("未使用"),
        ]
    )
    client = make_client(env_file, transport)

    result = sync_document_tree(client, ROOT_WIKI, tmp_path / "notes")

    assert len(result.children) == 1
    assert "A 正文（来自提及发现）" in result.children[0].read_text(encoding="utf-8")
    assert result.notes and any("wiki:node:retrieve" in n for n in result.notes)


def test_sync_tree_dedupes_repeated_mentions(tmp_path, env_file):
    parent_blocks = [
        {
            "block_id": "b1",
            "block_type": 2,
            "text": {
                "elements": [
                    {"mention_doc": {"token": CHILD_A, "obj_type": 16}},
                    {"mention_doc": {"token": CHILD_A, "obj_type": 16}},
                ],
                "style": {},
            },
        }
    ]
    transport = StubTransport(
        [
            token_response,
            node_response(ROOT_WIKI, DOC_ROOT, has_child=True),
            blocks_page(parent_blocks),
            lambda: {"code": 99991672, "msg": "required: [wiki:node:retrieve]", "data": {}},
            node_response(CHILD_A, DOC_A),
            blocks_page(items=[text_block("A 正文", "bA")]),
            content_response("未使用"),
        ]
    )
    client = make_client(env_file, transport)

    result = sync_document_tree(client, ROOT_WIKI, tmp_path / "notes")

    assert len(result.children) == 1