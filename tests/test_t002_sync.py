"""T-002 失败测试：sync 命令完整实现（blocks → markdown → 落盘 notes/）。

在实现之前编写：src/sync.py 尚不存在，必须全部失败。
覆盖 T-002 的验收（A-01 单文档部分）：

- 分页取回文档全部块（不是只取第一页）
- 页面/标题/段落/引用/列表/代码块转成正确 markdown，未知块降级为占位文本
- 写 notes/<id>.md 走「临时文件 + 替换」
- 任何一步失败都不得改动已有文件
- 命令行 sync 落盘并提示路径
"""

from __future__ import annotations

import pytest

from src import cli
from src.sync import render_markdown

APP_ID = "sync_test_app_id"
APP_SECRET = "sync_test_app_secret"
WIKI_TOKEN = "NMq0wmqEDiRkiAk2d8acp7mHnVd"
DOCX_ID = "docxTestToken456"

FENCE = chr(96) * 3


class StubTransport:
    """按调用顺序返回预置响应；每次请求都重建响应对象，避免用例间互相污染。"""

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

    def block_calls(self):
        return [c for c in self.calls if "/blocks" in c["url"]]


def ok(data):
    return {"code": 0, "msg": "success", "data": data}


def token_response():
    return ok({"tenant_access_token": "t-sync", "expire": 7200})


def wiki_response():
    return ok({"node": {"obj_type": "docx", "obj_token": DOCX_ID}})


def content_response(text="正文纯文本"):
    """T-002 起 CLI 在落盘后仍会打印正文，需要预置 raw_content 响应。"""

    def factory():
        return ok({"content": text})

    return factory


def blocks_page(items, has_more=False, page_token=None):
    def factory():
        data = {"items": items, "has_more": has_more}
        if page_token:
            data["page_token"] = page_token
        return ok(data)

    return factory


def el(text, **style):
    run = {"content": text}
    if style:
        run["text_element_style"] = style
    return {"text_run": run}


_BLOCK_SEQ = [0]


def block(block_type, payload_key, elements=None, style=None, **extra):
    """构造块。block_id 必须唯一：渲染器用 visited 集合去重，重复 id 会被当成同一块。"""
    _BLOCK_SEQ[0] += 1
    b = {
        "block_id": "blk-{}-{}-{}".format(block_type, payload_key, _BLOCK_SEQ[0]),
        "block_type": block_type,
        payload_key: {"elements": elements or [], "style": style or {}},
    }
    b.update(extra)
    return b


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    path = tmp_path / ".env"
    path.write_text("FEISHU_APP_ID={}\nFEISHU_APP_SECRET={}\n".format(APP_ID, APP_SECRET), encoding="utf-8")
    return path


def make_client(env_file, transport):
    from src.credentials import load_credentials
    from src.feishu import FeishuClient

    return FeishuClient(load_credentials(env_path=env_file), transport=transport)


# --- 1. 分页取块 -------------------------------------------------------------


def test_fetch_blocks_follows_pagination(env_file):
    transport = StubTransport(
        [
            token_response,
            blocks_page([{"block_id": "b1", "block_type": 2}], has_more=True, page_token="p2"),
            blocks_page([{"block_id": "b2", "block_type": 2}], has_more=False),
        ]
    )
    client = make_client(env_file, transport)

    blocks = client.fetch_blocks(DOCX_ID)

    assert [b["block_id"] for b in blocks] == ["b1", "b2"]
    assert transport.block_calls()[0]["params"]["page_size"] == 500
    assert transport.block_calls()[1]["params"]["page_token"] == "p2"


def test_fetch_blocks_single_page_makes_one_call(env_file):
    transport = StubTransport([token_response, blocks_page([{"block_id": "b1", "block_type": 2}])])
    client = make_client(env_file, transport)

    client.fetch_blocks(DOCX_ID)

    assert len(transport.block_calls()) == 1


def test_fetch_blocks_requires_items_field(env_file):
    from src.feishu import FeishuApiError

    transport = StubTransport([token_response, lambda: ok({"has_more": False})])
    client = make_client(env_file, transport)

    with pytest.raises(FeishuApiError):
        client.fetch_blocks(DOCX_ID)


# --- 2. 块 → markdown --------------------------------------------------------


def test_render_page_title_and_headings():
    blocks = [
        block(1, "page", [el("我的笔记")]),
        block(3, "heading1", [el("第一章")]),
        block(4, "heading2", [el("第一节")]),
        block(5, "heading3", [el("细节")]),
    ]

    md = render_markdown(blocks)

    assert "我的笔记" in md
    assert "## 第一章" in md
    assert "### 第一节" in md
    assert "#### 细节" in md
    assert not any(line.startswith("# ") for line in md.splitlines())


def test_render_paragraph_and_quote():
    blocks = [
        block(2, "text", [el("第一段")]),
        block(2, "text", [el("引用一")], style={"quote": True}),
    ]

    md = render_markdown(blocks)

    assert "第一段" in md
    assert "> 引用一" in md


def test_render_bullet_and_ordered_lists():
    blocks = [
        block(12, "bullet", [el("要点一")]),
        block(12, "bullet", [el("要点二")]),
        block(13, "ordered", [el("第一步")]),
        block(13, "ordered", [el("第二步")]),
    ]

    md = render_markdown(blocks)

    assert "- 要点一" in md
    assert "- 要点二" in md
    assert "1. 第一步" in md
    assert "2. 第二步" in md


def test_render_code_block_with_language():
    # 48 = python（1 = plaintext，22 = go，与飞书 language 枚举一致）
    blocks = [block(14, "code", [el("print(1)")], style={"language": 48})]

    md = render_markdown(blocks)

    assert FENCE + "python" in md
    assert "print(1)" in md
    assert md.count(FENCE) == 2


def test_render_unknown_block_becomes_placeholder():
    """模块笔记红线：未知块不得静默丢弃、也不得猜测内容。"""
    # 29 = 第三方小组件（本库未出现、也未支持）
    blocks = [block(29, "widget", [el("组件里的内容")])]

    md = render_markdown(blocks)

    assert "组件里的内容" not in md
    assert "[未支持的块: 29]" in md


def test_render_inline_styles():
    blocks = [
        block(
            2,
            "text",
            [
                el("粗", bold=True),
                el("斜", italic=True),
                el("码", inline_code=True),
                el("链", link={"url": "https://example.com"}),
            ],
        )
    ]

    md = render_markdown(blocks)

    assert "**粗**" in md
    assert "*斜*" in md
    assert chr(96) + "码" + chr(96) in md
    assert "[链](https://example.com)" in md


def test_render_empty_document():
    assert render_markdown([]) == ""


def test_render_skips_empty_paragraphs_without_blank_bursts():
    blocks = [
        block(2, "text", [el("前")]),
        block(2, "text", []),
        block(2, "text", []),
        block(2, "text", [el("后")]),
    ]

    md = render_markdown(blocks)

    assert "前" in md and "后" in md
    assert "\n\n\n" not in md


def test_render_nested_children_are_indented():
    child = block(12, "bullet", [el("子要点")])
    parent = block(12, "bullet", [el("父要点")])
    parent["children"] = [child["block_id"]]
    other = block(2, "text", [el("段落")])
    other["children"] = [child["block_id"]]

    md = render_markdown([parent, other, child])

    lines = [ln for ln in md.splitlines() if "子要点" in ln]
    assert lines and lines[0].startswith("  - ")


# --- 3. 落盘：临时文件 + 替换，失败不动旧文件 -------------------------------


def test_write_note_atomic_creates_dir_and_cleans_tmp(tmp_path):
    from src.sync import write_note_atomic

    target = tmp_path / "notes" / (DOCX_ID + ".md")

    write_note_atomic(target, "# 标题\n\n正文")

    assert target.read_text(encoding="utf-8") == "# 标题\n\n正文"
    assert list(target.parent.glob("*.tmp")) == []


def test_write_note_atomic_replaces_existing(tmp_path):
    from src.sync import write_note_atomic

    target = tmp_path / "notes" / (DOCX_ID + ".md")
    target.parent.mkdir(parents=True)
    target.write_text("旧内容", encoding="utf-8")

    write_note_atomic(target, "新内容")

    assert target.read_text(encoding="utf-8") == "新内容"


def test_fetch_failure_does_not_touch_existing_file(tmp_path, env_file):
    from src.feishu import FeishuApiError
    from src.sync import sync_document

    notes = tmp_path / "notes"
    notes.mkdir()
    target = notes / (DOCX_ID + ".md")
    target.write_text("原有笔记", encoding="utf-8")

    transport = StubTransport(
        [token_response, lambda: {"code": 131006, "msg": "permission denied", "data": {}}]
    )
    client = make_client(env_file, transport)

    with pytest.raises(FeishuApiError):
        sync_document(client, DOCX_ID, notes)

    assert target.read_text(encoding="utf-8") == "原有笔记"
    assert list(notes.glob("*.tmp")) == []


def test_render_failure_does_not_touch_existing_file(tmp_path, env_file):
    from src.feishu import FeishuApiError
    from src.sync import sync_document

    notes = tmp_path / "notes"
    notes.mkdir()
    target = notes / (DOCX_ID + ".md")
    target.write_text("原有笔记", encoding="utf-8")

    broken = [{"block_id": "b1", "block_type": 2, "text": {"elements": "not-a-list", "style": {}}}]
    transport = StubTransport([token_response, blocks_page(broken)])
    client = make_client(env_file, transport)

    with pytest.raises(FeishuApiError):
        sync_document(client, DOCX_ID, notes)

    assert target.read_text(encoding="utf-8") == "原有笔记"
    assert list(notes.glob("*.tmp")) == []


# --- 4. 端到端：sync_document 与 CLI ----------------------------------------


def test_sync_document_writes_markdown(tmp_path, env_file):
    from src.sync import sync_document

    blocks = [
        block(1, "page", [el("测试笔记")]),
        block(3, "heading1", [el("标题一")]),
        block(2, "text", [el("正文一段")]),
        block(14, "code", [el("x = 1")], style={"language": 48}),
    ]
    transport = StubTransport([token_response, blocks_page(blocks)])
    client = make_client(env_file, transport)
    notes = tmp_path / "notes"

    path = sync_document(client, DOCX_ID, notes)

    text = path.read_text(encoding="utf-8")
    assert path.name == DOCX_ID + ".md"
    assert "## 标题一" in text
    assert "正文一段" in text
    assert FENCE + "python" in text


def test_cli_sync_writes_note_and_reports_path(monkeypatch, tmp_path, env_file, capsys):
    notes = tmp_path / "notes"
    blocks = [block(3, "heading1", [el("标题一")]), block(2, "text", [el("正文")])]
    transport = StubTransport(
        [token_response, wiki_response, blocks_page(blocks), content_response()]
    )
    monkeypatch.setattr(cli, "make_transport", lambda: transport)

    code = cli.main(
        ["sync", "https://zcn4eq1fppkv.feishu.cn/wiki/" + WIKI_TOKEN],
        env_path=env_file,
        notes_dir=notes,
    )
    out = capsys.readouterr()

    assert code == 0
    # T-009 起落盘文件名用 wiki 节点 token（父+子文档统一命名，便于溯源）
    written = notes / (WIKI_TOKEN + ".md")
    assert written.is_file()
    assert "正文" in written.read_text(encoding="utf-8")
    assert str(written) in out.out + out.err


def test_cli_sync_failure_keeps_old_file(monkeypatch, tmp_path, env_file, capsys):
    notes = tmp_path / "notes"
    notes.mkdir()
    target = notes / (DOCX_ID + ".md")
    target.write_text("原有笔记", encoding="utf-8")
    transport = StubTransport(
        [token_response, wiki_response, lambda: {"code": 131006, "msg": "denied", "data": {}}]
    )
    monkeypatch.setattr(cli, "make_transport", lambda: transport)

    code = cli.main(
        ["sync", "https://x.feishu.cn/wiki/" + WIKI_TOKEN], env_path=env_file, notes_dir=notes
    )
    out = capsys.readouterr()

    assert code == 1
    assert target.read_text(encoding="utf-8") == "原有笔记"
    assert WIKI_TOKEN in out.err


def test_cli_sync_never_prints_secret(monkeypatch, tmp_path, env_file, capsys):
    notes = tmp_path / "notes"
    transport = StubTransport(
        [
            token_response,
            wiki_response,
            blocks_page([block(2, "text", [el("正文")])]),
            content_response(),
        ]
    )
    monkeypatch.setattr(cli, "make_transport", lambda: transport)

    cli.main(["sync", "https://x.feishu.cn/wiki/" + WIKI_TOKEN], env_path=env_file, notes_dir=notes)
    out = capsys.readouterr()

    assert APP_SECRET not in out.out + out.err
    assert "t-sync" not in out.out + out.err


# --- 5. 真实文档形状（实测后补的回归） --------------------------------------


def test_page_block_does_not_indent_whole_document():
    """真实文档把全部块挂在 page 块下；page 是容器，不能让整篇笔记统一缩进。"""
    page = block(1, "page", [el("笔记本")])
    h1 = block(3, "heading1", [el("第一章")])
    para = block(2, "text", [el("正文")])
    page["children"] = [h1["block_id"], para["block_id"]]

    md = render_markdown([page, h1, para])

    lines = md.splitlines()
    assert "## 第一章" in lines
    assert "正文" in lines


def test_mention_with_empty_text_run_is_not_swallowed():
    """真实文档里 mention 元素旁边会带一个空 text_run，不能被吞成空串。"""
    blocks = [block(2, "text", [{"text_run": {"content": ""}, "mention_doc": {"token": "x"}}])]

    md = render_markdown(blocks)

    assert "[文档提及]" in md


def test_mention_document_title_is_preserved():
    """实测：提及本身替代了段落文字，飞书也把 title 计入 raw_content，
    所以必须带上标题，否则就是静默丢内容。"""
    blocks = [
        block(2, "text", [{"text_run": {"content": ""}, "mention_doc": {"token": "x", "title": "python"}}])
    ]

    md = render_markdown(blocks)

    assert "[文档提及: python]" in md

# --- 6. 真实笔记里常见的块类型（T-009 实测补齐） ---------------------------


def test_render_image_block_as_placeholder_without_downloading():
    blocks = [block(27, "image", [], **{"token": "imgToken123"})]

    md = render_markdown(blocks)

    assert "[图片" in md            # 不下载图片，但必须留下位置标记
    assert "imgToken123" not in md  # 不把内部 token 當成内容写进笔记


def test_render_embedded_sheet_and_board_placeholders():
    md = render_markdown([
        block(30, "sheet", [], **{"token": "sheetTok"}),
        block(43, "board", [], **{"token": "boardTok"}),
    ])

    assert "[内嵌表格]" in md
    assert "[内嵌看板]" in md


def test_render_table_with_cell_contents():
    """飞书表格：table 块 + table_cell 子块；单元格内容要能读出来（实测 68 处）。"""
    cell_a = block(32, "table_cell", [])
    cell_a["children"] = ["text-a"]
    text_a = block(2, "text", [el("姓名")])
    text_a["block_id"] = "text-a"

    cell_b = block(32, "table_cell", [])
    cell_b["children"] = ["text-b"]
    text_b = block(2, "text", [el("年龄")])
    text_b["block_id"] = "text-b"

    table = block(31, "table", [])
    table["children"] = [cell_a["block_id"], cell_b["block_id"]]

    md = render_markdown([table, cell_a, cell_b, text_a, text_b])

    assert "姓名" in md and "年龄" in md
    assert "未支持的块: 32" not in md


def test_render_grid_preserves_child_content():
    """分栏（grid/grid_column）只是排版容器，里面的正文不能丢。"""
    inner = block(2, "text", [el("分栏里的正文")])
    inner["block_id"] = "inner-text"
    column = block(25, "grid_column", [])
    column["children"] = ["inner-text"]
    grid = block(24, "grid", [])
    grid["children"] = [column["block_id"]]

    md = render_markdown([grid, column, inner])

    assert "分栏里的正文" in md
    assert "未支持的块" not in md


def test_render_table_renders_rows_as_markdown_table():
    """两列两行的表格渲染成 markdown 表格，便于阅读。"""
    def cell(cid, text_id, content):
        c = {"block_id": cid, "block_type": 32, "table_cell": {}, "children": [text_id]}
        return c

    def txt(tid, content):
        return {"block_id": tid, "block_type": 2, "text": {"elements": [{"text_run": {"content": content}}], "style": {}}}

    cells = [cell("c1", "t1", "姓名"), cell("c2", "t2", "年龄"), cell("c3", "t3", "小明"), cell("c4", "t4", "18")]
    table = {"block_id": "tb", "block_type": 31, "table": {"property": {"row_size": 2, "column_size": 2}}, "children": ["c1", "c2", "c3", "c4"]}
    blocks = [table, *cells, txt("t1", "姓名"), txt("t2", "年龄"), txt("t3", "小明"), txt("t4", "18")]

    md = render_markdown(blocks)

    assert "| 姓名 | 年龄 |" in md
    assert "| 小明 | 18 |" in md
    assert "| --- | --- |" in md
