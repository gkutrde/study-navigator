"""T-002：把飞书文档块转成 markdown 并落盘 notes/。

边界（见 [[模块-笔记同步]]）：

- 只做单文档；子文档递归是 T-009。
- 不理解内容，只做块级结构还原。
- 未知块类型降级为占位文本，不静默丢弃、不猜内容。
- 落盘走「临时文件 + 替换」；任何一步失败都不改动已有文件。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .feishu import FeishuApiError, FeishuClient, scope_hint

# 飞书代码块 language 枚举 → 代码围栏语言标记（只列常见的，其余留空）
CODE_LANGUAGES = {
    1: "plaintext",
    2: "abap",
    3: "ada",
    4: "apache",
    5: "apex",
    6: "assembly",
    7: "bash",
    8: "csharp",
    9: "cpp",
    10: "c",
    11: "cobol",
    12: "css",
    13: "coffeescript",
    14: "d",
    15: "dart",
    16: "delphi",
    17: "django",
    18: "dockerfile",
    19: "erlang",
    20: "fortran",
    21: "foxpro",
    22: "go",
    23: "groovy",
    24: "html",
    25: "htmlbars",
    26: "http",
    27: "haskell",
    28: "json",
    29: "java",
    30: "javascript",
    31: "julia",
    32: "kotlin",
    33: "latex",
    34: "lisp",
    35: "logo",
    36: "lua",
    37: "matlab",
    38: "makefile",
    39: "markdown",
    40: "nginx",
    41: "objectivec",
    42: "openedge",
    43: "php",
    44: "perl",
    45: "powershell",
    46: "prolog",
    47: "protobuf",
    48: "python",
    49: "r",
    50: "rst",
    51: "ruby",
    52: "rust",
    53: "sas",
    54: "scss",
    55: "sql",
    56: "scala",
    57: "scheme",
    58: "scratch",
    59: "shell",
    60: "swift",
    61: "thrift",
    62: "typescript",
    63: "vbscript",
    64: "visualbasic",
    65: "xml",
    66: "yaml",
    67: "cmake",
    68: "diff",
    69: "gherkin",
    70: "graphql",
    71: "sml",
    72: "toml",
}

_FENCE = "```"


def _elements_of(block: dict[str, Any], payload_key: str, document_id: str) -> list[dict[str, Any]]:
    payload = block.get(payload_key)
    if payload is None:
        return []
    if not isinstance(payload, dict):
        raise FeishuApiError(
            f"文档 {document_id} 的块 {block.get('block_id')} 结构异常（{payload_key} 不是对象）"
        )
    elements = payload.get("elements", [])
    if not isinstance(elements, list):
        # 结构损坏必须显式失败：绝不能把坏数据渲染成半成品文件
        raise FeishuApiError(
            f"文档 {document_id} 的块 {block.get('block_id')} 结构异常（elements 不是列表）"
        )
    return elements


def _render_elements(elements: Iterable[dict[str, Any]]) -> str:
    parts: list[str] = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        # 注意：真实文档里 mention 等元素会同时带一个空的 text_run，
        # 所以必须先判非文本元素，否则提及会被吞成空串。
        if element.get("mention_doc"):
            mention = element["mention_doc"]
            title = mention.get("title") if isinstance(mention, dict) else None
            # 提及本身就是笔记内容的一部分（真实文档里它替代了段落文字），
            # 飞书也把 title 计入 raw_content，所以这里带上标题而不是丢成空串。
            parts.append(f"[文档提及: {title}]" if title else "[文档提及]")
            continue
        if element.get("mention_user"):
            parts.append("[用户提及]")
            continue
        if element.get("file"):
            parts.append("[附件]")
            continue
        if element.get("equation"):
            parts.append("[公式]")
            continue
        if element.get("reminder"):
            parts.append("[提醒]")
            continue
        run = element.get("text_run")
        if isinstance(run, dict):
            content = str(run.get("content", ""))
            if content:
                parts.append(_apply_inline_style(content, run.get("text_element_style") or {}))
            continue
        if run is None:
            parts.append("[未支持的元素]")
    return "".join(parts)


def _apply_inline_style(content: str, style: dict[str, Any]) -> str:
    if not isinstance(style, dict):
        return content
    if style.get("inline_code"):
        return "`" + content + "`"
    text = content
    if style.get("bold"):
        text = f"**{text}**"
    if style.get("italic"):
        text = f"*{text}*"
    if style.get("strikethrough"):
        text = f"~~{text}~~"
    link = style.get("link")
    if isinstance(link, dict) and link.get("url"):
        text = f"[{text}]({link['url']})"
    return text


def _code_language(style: dict[str, Any]) -> str:
    if not isinstance(style, dict):
        return ""
    raw = style.get("language")
    if isinstance(raw, bool) or raw is None:
        return ""
    if isinstance(raw, int):
        return CODE_LANGUAGES.get(raw, "")
    return ""


class _Renderer:
    """按块渲染。父子关系通过 children + by_id 解析，visited 保证不重复渲染。"""

    def __init__(self, blocks: list[dict[str, Any]], document_id: str) -> None:
        self._blocks = blocks
        self._by_id = {b.get("block_id"): b for b in blocks if isinstance(b, dict)}
        self._document_id = document_id
        self._visited: set[str] = set()
        self._ordered_index = 0

    def render(self) -> str:
        lines: list[str] = []
        for block in self._blocks:
            if isinstance(block, dict):
                self._render_block(block, 0, lines)
        text = "\n".join(lines)
        while "\n\n\n" in text:
            text = text.replace("\n\n\n", "\n\n")
        return text.strip("\n")

    def _render_block(self, block: dict[str, Any], depth: int, lines: list[str]) -> None:
        block_id = block.get("block_id")
        if block_id in self._visited:
            return
        if block_id:
            self._visited.add(block_id)

        lines.extend(self._block_lines(block, depth))

        # 飞书把整篇文档的块都挂在 page 块下，page 是容器不是层级：
        # 若把它算作一层，整篇笔记会统一多出两个空格缩进。
        is_container = block.get("block_type") == 1
        child_depth = depth if is_container else depth + 1
        for child_id in block.get("children") or []:
            child = self._by_id.get(child_id)
            if isinstance(child, dict):
                self._render_block(child, child_depth, lines)

    def _block_lines(self, block: dict[str, Any], depth: int) -> list[str]:
        block_type = block.get("block_type")
        indent = "  " * depth

        if block_type == 1:
            return self._paragraph_lines(block, "page", indent)
        if isinstance(block_type, int) and 3 <= block_type <= 11:
            key = f"heading{block_type - 2}"
            text = _render_elements(_elements_of(block, key, self._document_id)).strip()
            return [f"{indent}{'#' * (block_type - 1)} {text}"] if text else []
        if block_type == 2:
            return self._paragraph_lines(block, "text", indent)
        if block_type == 12:
            return self._list_lines(block, "bullet", "- ", indent)
        if block_type == 13:
            return self._list_lines(block, "ordered", None, indent)
        if block_type == 14:
            elements = _elements_of(block, "code", self._document_id)
            payload = block.get("code") or {}
            language = _code_language(payload.get("style") or {})
            return [_FENCE + language, _render_elements(elements), _FENCE]
        if block_type == 15:
            return self._paragraph_lines(block, "quote_container", indent)
        if block_type == 31:
            # 表格（实测客户笔记里 68 个单元格都在这）：渲染成 markdown 表格，内容不能丢
            table_lines = self._table_lines(block)
            if table_lines:
                return table_lines
            return [f"{indent}[表格]"]
        if block_type == 32:
            # 表格单元格本身不单独输出（由 table 汇总），单独出现时也不产生噪声
            return []
        if block_type == 27:
            # 图片不下载，但保留位置标记；token 属于内部标识，不写进笔记正文
            return [f"{indent}[图片]"]
        if block_type in (30,):
            return [f"{indent}[内嵌表格]"]
        if block_type == 43:
            return [f"{indent}[内嵌看板]"]
        if block_type in (24, 25):
            # 分栏只是排版容器，内容在子块里，这里不产生标记
            return []
        # 未知块：按模块笔记红线降级为占位文本，不丢弃也不猜内容
        return [f"{indent}[未支持的块: {block_type}]"]

    def _cell_text(self, block_id: str) -> str:
        """取某个单元格块下所有子块的文本（表格用）。"""
        pieces: list[str] = []
        cell = self._by_id.get(block_id)
        if not isinstance(cell, dict):
            return ""
        for child_id in cell.get("children") or []:
            child = self._by_id.get(child_id)
            if not isinstance(child, dict):
                continue
            payload_key = child.get("payload_key")
            if payload_key is None:
                payload_key = next(
                    (
                        key
                        for key in child
                        if key not in {"block_id", "parent_id", "children", "block_type", "comments"}
                    ),
                    None,
                )
            if payload_key is None:
                continue
            text = _render_elements(_elements_of(child, payload_key, self._document_id)).strip()
            if text:
                pieces.append(text)
        return " ".join(pieces).replace("|", chr(92) + "|")

    def _table_lines(self, block: dict[str, Any]) -> list[str]:
        """把飞书表格渲染成 markdown 表格（行列数来自 table.property）。"""
        payload = block.get("table") or {}
        prop = payload.get("property") if isinstance(payload.get("property"), dict) else {}
        cells = block.get("children") or []
        columns = int(prop.get("column_size") or 0)
        if not cells:
            return []
        if columns <= 0:
            columns = len(cells)

        rows: list[list[str]] = []
        for start in range(0, len(cells), columns):
            rows.append([self._cell_text(cid) for cid in cells[start:start + columns]])
        if not rows:
            return []

        width = max(len(row) for row in rows)
        lines = []
        for index, row in enumerate(rows):
            padded = row + [""] * (width - len(row))
            lines.append("| " + " | ".join(padded) + " |")
            if index == 0:
                lines.append("| " + " | ".join(["---"] * width) + " |")
        return lines

    def _paragraph_lines(self, block: dict[str, Any], key: str, indent: str) -> list[str]:
        text = _render_elements(_elements_of(block, key, self._document_id)).strip()
        if not text:
            return []
        payload = block.get(key) or {}
        if isinstance(payload.get("style"), dict) and payload["style"].get("quote"):
            return [f"{indent}> {text}"]
        return [f"{indent}{text}"]

    def _list_lines(self, block: dict[str, Any], key: str, marker: str | None, indent: str) -> list[str]:
        text = _render_elements(_elements_of(block, key, self._document_id)).strip()
        if marker is None:
            self._ordered_index += 1
            marker = f"{self._ordered_index}. "
        return [f"{indent}{marker}{text}"]


def render_markdown(blocks: list[dict[str, Any]], document_id: str = "") -> str:
    """把飞书文档块列表转成 markdown。"""
    if not blocks:
        return ""
    return _Renderer(list(blocks), document_id).render()


def write_note_atomic(path: Path | str, content: str) -> Path:
    """先写 <path>.tmp，成功后再替换目标文件；失败不留下半成品。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_name(target.name + ".tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(target)
    except OSError as exc:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise FeishuApiError(f"写入 {target} 失败：{type(exc).__name__}") from None
    return target


def sync_document(client: FeishuClient, document_id: str, notes_dir: Path | str) -> Path:
    """拉取一篇文档 → 转 markdown → 落盘 notes/<id>.md，返回文件路径。"""
    blocks = client.fetch_blocks(document_id)
    markdown = render_markdown(blocks, document_id=document_id)
    return write_note_atomic(Path(notes_dir) / f"{document_id}.md", markdown)


@dataclass
class SyncTreeResult:
    """一次递归同步的结果（T-009）。"""

    root: Path
    document_id: str = ""
    children: list[Path] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _mention_child_tokens(blocks: list[dict[str, Any]]) -> list[str]:
    """从父文档的块里找「文档提及」的 token —— 缺 wiki:node:retrieve 权限时的兜底发现方式。"""
    tokens: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        payload_key = next(
            (
                key
                for key in block
                if key not in {"block_id", "parent_id", "children", "block_type", "comments"}
            ),
            None,
        )
        if payload_key is None:
            continue
        payload = block.get(payload_key)
        if not isinstance(payload, dict):
            continue
        for element in payload.get("elements") or []:
            if not isinstance(element, dict):
                continue
            mention = element.get("mention_doc")
            if isinstance(mention, dict):
                token = str(mention.get("token") or "").strip()
                if token and token not in tokens:
                    tokens.append(token)
    return tokens


def sync_document_tree(
    client: FeishuClient,
    wiki_token: str,
    notes_dir: Path | str,
    *,
    max_depth: int = 5,
) -> SyncTreeResult:
    """递归拉取一个 wiki 节点及其全部子节点，各自落盘 notes/<wiki token>.md。

    - 父文档失败 → 抛错，不写任何文件（已成功的子文档也不会被删）。
    - 子文档失败/无权 → 跳过并记录 (节点标识, 原因)，其余继续。
    - 列举子节点需要 wiki:node:retrieve；缺该权限时退化为「从父文档的文档提及发现子文档」。
    """
    if max_depth < 0:
        raise FeishuApiError("max_depth 不能为负数")

    notes_root = Path(notes_dir)
    root_doc_id, space_id = client.resolve_wiki_node(wiki_token)

    # 父文档：先取块与正文（失败即抛，不产生半成品）
    root_blocks = client.fetch_blocks(root_doc_id)
    root_markdown = render_markdown(root_blocks, document_id=root_doc_id)
    root_path = write_note_atomic(notes_root / f"{wiki_token}.md", root_markdown)

    result = SyncTreeResult(root=root_path, document_id=root_doc_id)
    visited: set[str] = {wiki_token}

    # 队列元素：(node_token, obj_token, space_id, depth, has_child)
    queue: list[tuple[str, str, str, int, bool]] = (
        _discover_children(client, wiki_token, space_id, root_blocks, result, depth=1)
        if max_depth >= 1
        else []
    )

    while queue:
        node_token, obj_token, child_space, depth, has_child = queue.pop(0)
        if node_token in visited:
            continue
        visited.add(node_token)

        try:
            if obj_token:
                doc_id = obj_token
            else:
                # 兜底发现的子节点只有 token，需要先解析成文档 ID。
                # 注意：解析失败必须直接跳过这个子文档，绝不能拿 wiki token 当文档 ID 去取块
                # （否则错误信息会误导成「块响应异常」）。
                doc_id, child_space_id = client.resolve_wiki_node(node_token)
                if child_space_id and not child_space:
                    child_space = child_space_id
            blocks = client.fetch_blocks(doc_id)
            markdown = render_markdown(blocks, document_id=doc_id)
            path = write_note_atomic(notes_root / f"{node_token}.md", markdown)
        except FeishuApiError as exc:
            result.skipped.append((node_token, f"拉取失败：{exc}"))
            continue
        except Exception as exc:  # 兜底：单个子文档异常不应中断整棵树
            result.skipped.append((node_token, f"未预期错误：{type(exc).__name__}"))
            continue

        result.children.append(path)

        if depth < max_depth:
            queue.extend(
                _discover_children(
                    client,
                    node_token,
                    child_space or space_id,
                    blocks,
                    result,
                    depth=depth + 1,
                    has_child=has_child,
                )
            )

    return result


def _discover_children(
    client: FeishuClient,
    node_token: str,
    space_id: str,
    blocks: list[dict[str, Any]],
    result: SyncTreeResult,
    *,
    depth: int,
    has_child: bool = True,
) -> list[tuple[str, str, str, int, bool]]:
    """发现子节点：优先用 wiki 列举接口；该接口权限不足时退化为文档提及。

    has_child=False 时跳过列举接口（API 已明确没有子节点），既省请求也避免无意义的权限报错。
    返回 (node_token, obj_token, space_id, depth, has_child)。
    """
    if space_id and has_child:
        try:
            children = client.fetch_wiki_children(space_id, node_token)
            return [
                (c.node_token, c.obj_token, c.space_id or space_id, depth, bool(c.has_child))
                for c in children
            ]
        except FeishuApiError as exc:
            hint = scope_hint(exc)
            if not hint:
                # 非权限类错误：记下来但继续用兜底方式，避免整棵树失败
                result.notes.append(f"列举 {node_token} 的子节点失败（改用文档提及兜底）：{exc}")
            else:
                if hint not in result.notes:
                    result.notes.append(hint)

    tokens = _mention_child_tokens(blocks)
    # 兜底发现的节点未知是否有子节点，按 True 处理以便继续递归
    return [(token, "", space_id, depth, True) for token in tokens]