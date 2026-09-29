"""T-011：复用 Kimi Code CLI 的登录态（OAuth access_token）。

Kimi Code CLI 登录后会把凭证写到 ~/.kimi-code/credentials/kimi-code.json，
里面有 access_token / refresh_token / expires_at。本模块只做三件事：

1. 读取该文件（不存在、损坏、没有 token 都返回 None）；
2. 判断是否过期；
3. 提供进内存的令牌给 LLMClient 用。

边界：
- 不实现自动刷新（T-011 明确不做），过期就提示去 CLI 重新登录；
- 令牌只进内存与请求头，绝不写日志、不进异常消息、不落档。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import time

DEFAULT_LOGIN_PATH = Path(".kimi-code") / "credentials" / "kimi-code.json"


@dataclass(frozen=True)
class CliLogin:
    """Kimi Code CLI 登录态。repr 固定脱敏。"""

    access_token: str
    refresh_token: str = ""
    expires_at: float | None = None
    scope: str = ""
    token_type: str = "Bearer"
    source: str = ""
    _extra: dict = field(default_factory=dict, repr=False)

    def __repr__(self) -> str:
        state = "已过期" if self.is_expired() else "有效"
        return f"CliLogin(source={self.source or '<unknown>'}, state={state}, token=<redacted>)"

    __str__ = __repr__

    def is_expired(self, now: float | None = None) -> bool:
        """没有 expires_at 时按「不判过期」处理（交给服务端拒绝）。"""
        if self.expires_at is None:
            return False
        return self.expires_at <= (time.time() if now is None else now)

    def seconds_left(self, now: float | None = None) -> float | None:
        if self.expires_at is None:
            return None
        return self.expires_at - (time.time() if now is None else now)


def default_login_path(home: Path | str | None = None) -> Path:
    base = Path(home) if home is not None else Path(os.path.expanduser("~"))
    return base / DEFAULT_LOGIN_PATH


def load_cli_login(home: Path | str | None = None, path: Path | str | None = None) -> CliLogin | None:
    """读取登录态；文件不存在 / 不是 JSON / 没有 access_token 都返回 None。"""
    target = Path(path) if path is not None else default_login_path(home)
    if not target.is_file():
        return None
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None

    token = str(raw.get("access_token") or "").strip()
    if not token:
        return None

    expires_at = raw.get("expires_at")
    try:
        expires_at = float(expires_at) if expires_at is not None else None
    except (TypeError, ValueError):
        expires_at = None

    return CliLogin(
        access_token=token,
        refresh_token=str(raw.get("refresh_token") or ""),
        expires_at=expires_at,
        scope=str(raw.get("scope") or ""),
        token_type=str(raw.get("token_type") or "Bearer"),
        source=target.as_posix(),
    )


LOGIN_STATE_ENV_LABEL = "<Kimi Code CLI 登录态>"
RELOGIN_HINT = "请重新登录：在 Kimi Code CLI 里执行 /login（登录态由 CLI 维护，工具不自动刷新）"
