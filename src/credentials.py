"""T-001：从本地 .env 读取飞书凭证。

凭证的取值只进入内存与请求体，绝不进入日志、异常消息或 stdout。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
import os

REQUIRED_FEISHU_KEYS = ("FEISHU_APP_ID", "FEISHU_APP_SECRET")
DEFAULT_ENV_PATH = Path(".env")


class CredentialError(RuntimeError):
    """凭证缺失或不可读。消息里只能出现「键名」，不能出现「值」。"""


def parse_env_file(path: Path | str) -> dict[str, str]:
    """极简 .env 解析：支持 KEY=VALUE、# 注释、可选的成对引号。"""
    p = Path(path)
    if not p.is_file():
        raise CredentialError(f"找不到 .env 文件：{p}（请复制 .env.example 并填入飞书凭证）")

    values: dict[str, str] = {}
    # errors="replace"：.env 被存成 GBK 等编码时，键名与 ASCII 值照样读得出来（以前直接抛 UnicodeDecodeError）
    for raw in p.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


@dataclass(frozen=True)
class Credentials:
    """飞书自建应用凭证。repr/str 永远是脱敏的。"""

    app_id: str
    app_secret: str

    def __repr__(self) -> str:
        return "Credentials(app_id=<set>, app_secret=<redacted>)"

    __str__ = __repr__


def _lookup(key: str, file_values: Mapping[str, str]) -> str:
    """优先读真实环境变量，其次读 .env 文件。"""
    from_env = os.environ.get(key, "").strip()
    if from_env:
        return from_env
    return str(file_values.get(key, "")).strip()


def load_credentials(env_path: Path | str = DEFAULT_ENV_PATH) -> Credentials:
    """读取 .env 并校验必需键；缺键时报出键名（不报值）。"""
    file_values = parse_env_file(env_path)
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for key in REQUIRED_FEISHU_KEYS:
        value = _lookup(key, file_values)
        if not value:
            missing.append(key)
        else:
            resolved[key] = value

    if missing:
        raise CredentialError(
            "飞书凭证缺失："
            + "、".join(missing)
            + f"（请在 {Path(env_path)} 中填写，参考 .env.example）"
        )

    return Credentials(app_id=resolved["FEISHU_APP_ID"], app_secret=resolved["FEISHU_APP_SECRET"])
