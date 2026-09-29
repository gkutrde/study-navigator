"""飞书开放平台最小只读客户端。

做四件事：换 tenant_access_token、把 wiki 节点解析成 docx 文档 ID、
取正文纯文本（T-001 连通验证）、分页取文档块（T-002）。
不涉及 markdown 转换与落盘（在 src/sync.py）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import requests

from .credentials import Credentials

FEISHU_BASE = "https://open.feishu.cn/open-apis"
TENANT_TOKEN_URL = f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal"
WIKI_GET_NODE_URL = f"{FEISHU_BASE}/wiki/v2/spaces/get_node"
# 按 space_id 列举空间下的节点；带 parent_node_token 即列举某节点的子节点（T-009）
WIKI_LIST_NODES_URL = FEISHU_BASE + "/wiki/v2/spaces/{space_id}/nodes"
WIKI_CHILDREN_PAGE_SIZE = 50
# 飞书权限类错误码：列出子节点需要 wiki:node:retrieve（与单节点读取的 wiki:node:read 不同）
FEISHU_PERMISSION_CODE = "99991672"
RETRIEVE_SCOPE_HINT = "wiki:node:retrieve"
RAW_CONTENT_URL = FEISHU_BASE + "/docx/v1/documents/{document_id}/raw_content"
BLOCKS_URL = FEISHU_BASE + "/docx/v1/documents/{document_id}/blocks"
BLOCKS_PAGE_SIZE = 500


class FeishuApiError(RuntimeError):
    """飞书接口失败。消息里只能出现错误码、文档标识和原因，不能出现凭证。"""


@dataclass(frozen=True)
class WikiChild:
    """wiki 节点的子节点（T-009）。"""

    node_token: str
    obj_token: str
    obj_type: str
    title: str = ""
    has_child: bool = False
    space_id: str = ""


def scope_hint(error: BaseException) -> str:
    """从飞书权限报错里提炼出可执行的提示（缺哪个 scope）。"""
    text = str(error)
    if FEISHU_PERMISSION_CODE not in text:
        return ""
    if RETRIEVE_SCOPE_HINT in text:
        return (
            "列举子节点需要应用身份权限 wiki:node:retrieve（当前只有 wiki:node:read）；"
            "本次已退化为「从父文档的文档提及里发现子文档」"
        )
    return f"飞书权限不足（错误码 {FEISHU_PERMISSION_CODE}）：{text[:200]}"


class Transport(Protocol):
    """HTTP 传输层协议：测试用打桩实现替换，生产用 RequestsTransport。"""

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any: ...


def _short_reason(text: str, limit: int = 400) -> str:
    """截断飞书返回的原文，但保留足够长度让权限申请链接完整可见。"""
    collapsed = " ".join(str(text).split())
    return collapsed if len(collapsed) <= limit else collapsed[:limit] + "..."


class RequestsTransport:
    """真实网络传输。异常只暴露异常类名，避免响应体把凭证带出去。"""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def request(self, method, url, *, params=None, headers=None, json_body=None):
        try:
            response = requests.request(
                method,
                url,
                params=params,
                headers=headers,
                json=json_body,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise FeishuApiError(f"网络请求失败：{type(exc).__name__}") from None
        try:
            return response.json()
        except ValueError:
            raise FeishuApiError(
                f"飞书返回了非 JSON 响应（HTTP {response.status_code}）"
            ) from None


class FeishuClient:
    """飞书只读客户端。"""

    def __init__(self, credentials: Credentials, transport: Transport | None = None) -> None:
        self._credentials = credentials
        self._transport = transport if transport is not None else RequestsTransport()
        self._tenant_token: str | None = None

    # --- 内部 ---

    def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        is_token_call = url == TENANT_TOKEN_URL
        try:
            response = self._transport.request(
                "POST" if is_token_call else "GET",
                url,
                params=params,
                headers=None if is_token_call else self._auth_header(),
                json_body=(
                    {
                        "app_id": self._credentials.app_id,
                        "app_secret": self._credentials.app_secret,
                    }
                    if is_token_call
                    else None
                ),
            )
        except FeishuApiError:
            raise
        except Exception as exc:
            # 传输层异常可能携带请求体（含 app_secret），只保留异常类型名
            raise FeishuApiError(f"网络请求失败：{type(exc).__name__}") from None
        return _check(response)

    def _tenant_access_token(self) -> str:
        if self._tenant_token:
            return self._tenant_token
        payload = self._get(TENANT_TOKEN_URL)
        token = payload.get("tenant_access_token")
        if not token:
            raise FeishuApiError(
                "飞书未返回 tenant_access_token：请检查 .env 中 FEISHU_APP_ID / FEISHU_APP_SECRET 是否有效"
            )
        self._tenant_token = str(token)
        return self._tenant_token

    def _auth_header(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._tenant_access_token()}"}

    # --- 对外 ---

    def resolve_wiki_node(self, token: str) -> tuple[str, str]:
        """解析 wiki 节点，返回 (docx 文档 ID, space_id)。只发一次请求。"""
        try:
            payload = self._get(WIKI_GET_NODE_URL, params={"token": token})
        except FeishuApiError as exc:
            raise FeishuApiError(f"wiki 节点 {token} 解析失败：{exc}") from None
        node = payload.get("node") or {}
        obj_token = node.get("obj_token")
        if not obj_token:
            obj_type = node.get("obj_type") or "未知"
            raise FeishuApiError(
                f"wiki 节点 {token} 未解析出文档 ID（obj_type={obj_type}）；"
                "请确认该文档已授权给应用（把文档分享给应用/机器人）"
            )
        return str(obj_token), str(node.get("space_id") or "")

    def resolve_docx_token(self, token: str, maybe_wiki: bool) -> str:
        """wiki 节点要先解析出 obj_token（docx 文档 ID）；非 wiki 输入原样返回。"""
        if not maybe_wiki:
            return token
        obj_token, _ = self.resolve_wiki_node(token)
        return obj_token

    def fetch_wiki_children(self, space_id: str, parent_node_token: str) -> list[WikiChild]:
        """列举某 wiki 节点下的全部直接子节点（分页聚合，T-009）。

        注意：该接口需要应用身份权限 wiki:node:retrieve；只有 wiki:node:read 时会报 99991672。
        """
        children: list[WikiChild] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {
                "parent_node_token": parent_node_token,
                "page_size": WIKI_CHILDREN_PAGE_SIZE,
            }
            if page_token:
                params["page_token"] = page_token
            try:
                payload = self._get(WIKI_LIST_NODES_URL.format(space_id=space_id), params=params)
            except FeishuApiError as exc:
                raise FeishuApiError(
                    f"列举 wiki 节点 {parent_node_token} 的子节点失败：{exc}"
                ) from None
            items = payload.get("items")
            if not isinstance(items, list):
                raise FeishuApiError(f"wiki 节点 {parent_node_token} 的子节点响应缺少 items 列表")
            for item in items:
                if not isinstance(item, dict):
                    continue
                node_token = str(item.get("node_token") or "").strip()
                if not node_token:
                    continue
                children.append(
                    WikiChild(
                        node_token=node_token,
                        obj_token=str(item.get("obj_token") or ""),
                        obj_type=str(item.get("obj_type") or ""),
                        title=str(item.get("title") or ""),
                        has_child=bool(item.get("has_child")),
                        space_id=str(item.get("space_id") or space_id),
                    )
                )
            if not payload.get("has_more"):
                return children
            page_token = payload.get("page_token")
            if not page_token:
                raise FeishuApiError(
                    f"wiki 节点 {parent_node_token} 分页异常：has_more 为真但没有 page_token"
                )

    def fetch_blocks(self, document_id: str) -> list[dict[str, Any]]:
        """分页取回文档全部块（T-002）。"""
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": BLOCKS_PAGE_SIZE, "document_revision_id": -1}
            if page_token:
                params["page_token"] = page_token
            try:
                payload = self._get(BLOCKS_URL.format(document_id=document_id), params=params)
            except FeishuApiError as exc:
                raise FeishuApiError(f"文档 {document_id} 块内容拉取失败：{exc}") from None
            page_items = payload.get("items")
            if not isinstance(page_items, list):
                raise FeishuApiError(f"文档 {document_id} 的块响应缺少 items 列表")
            items.extend(page_items)
            if not payload.get("has_more"):
                return items
            page_token = payload.get("page_token")
            if not page_token:
                raise FeishuApiError(f"文档 {document_id} 分页异常：has_more 为真但没有 page_token")

    def fetch_plain_text(self, document_id: str) -> str:
        """取文档正文纯文本。"""
        try:
            payload = self._get(RAW_CONTENT_URL.format(document_id=document_id))
        except FeishuApiError as exc:
            raise FeishuApiError(f"文档 {document_id} 正文拉取失败：{exc}") from None
        if "content" not in payload:
            raise FeishuApiError(f"文档 {document_id} 的响应缺少正文字段 content")
        return str(payload.get("content") or "").rstrip()


def _check(response: Any) -> dict[str, Any]:
    """把飞书响应统一校验成 data 段，失败抛 FeishuApiError。"""
    if not isinstance(response, dict):
        raise FeishuApiError(f"飞书返回了非对象响应（{type(response).__name__}）")

    code = response.get("code")
    if code in (0, None):
        data = response.get("data")
        if data is None:
            nested: dict[str, Any] = {"tenant_access_token": response.get("tenant_access_token")}
            if "expire" in response:
                nested["expire"] = response.get("expire")
            return nested
        if not isinstance(data, dict):
            raise FeishuApiError("飞书返回的 data 段格式异常")
        return data

    message = _short_reason(response.get("msg") or "")
    raise FeishuApiError(f"飞书接口返回错误码 {code}：{message}")
