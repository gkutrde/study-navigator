"""T-003：LLM 客户端封装（Kimi 为主、DeepSeek 备用）。

只做一件事：发一次 OpenAI 兼容的 chat/completions 请求并取回文本。
凭证只从 .env / 环境变量读取，绝不进入日志、异常消息或调用方 payload。

Kimi 有两个互不通用的平台（官方文档 www.kimi.com/code/docs/kimi-code/faq.html）：

| 平台 | base_url | 计费 | Key 入口 | 环境变量 |
| --- | --- | --- | --- | --- |
| Kimi Code 会员（coding plan） | https://api.kimi.com/coding/v1 | 会员订阅含额度 | Kimi Code 控制台 | KIMI_API_KEY |
| Kimi 开放平台（按量） | https://api.moonshot.cn/v1 | 按量付费 | platform.kimi.com | MOONSHOT_API_KEY |

两者 Key 不通用；provider=kimi 时优先用 coding plan 的 KIMI_API_KEY。
coding 端点支持 OpenAI 兼容的 /chat/completions（端点探测：无效 Key 返回 401 invalid_authentication_error，
而不是 404）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
import os
from pathlib import Path
import re
import time
from typing import Any
import urllib.error
import urllib.request

from .cli_login import LOGIN_STATE_ENV_LABEL, RELOGIN_HINT, default_login_path, load_cli_login
from .credentials import DEFAULT_ENV_PATH, parse_env_file


class LLMError(RuntimeError):
    """LLM 调用失败或配置不合法。消息里只能出现键名、HTTP 状态和服务端提示，不能出现 Key。"""


PROVIDER_ALIASES = {
    "kimi": "kimi",
    "kimi-coding": "kimi",
    "kimi_code": "kimi",
    "kimicode": "kimi",
    "coding": "kimi",
    "moonshot": "kimi",
    "deepseek": "deepseek",
}

# Kimi 两个平台的端点与 Key（互不通用）
KIMI_CODING_BASE = "https://api.kimi.com/coding/v1"
KIMI_OPEN_PLATFORM_BASE = "https://api.moonshot.cn/v1"
KIMI_CODING_KEY_ENV = "KIMI_API_KEY"
KIMI_OPEN_KEY_ENV = "MOONSHOT_API_KEY"
KIMI_MODEL_ENV = "KIMI_MODEL"
# 实测（T-011）：登录态端点 /coding/v1/models 返回的是 kimi-for-coding 系列
KIMI_CODING_MODEL = "kimi-for-coding"
KIMI_CODING_MODELS = ("kimi-for-coding", "kimi-for-coding-highspeed", "k3", "k3-256k")
# 开放平台按量端点在售模型
KIMI_OPEN_PLATFORM_MODEL = "kimi-k2.7-code"
KIMI_BASE_URL_ENV = "KIMI_BASE_URL"


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    model: str
    api_key: str
    api_key_env: str
    base_url_env: str = ""

    def __repr__(self) -> str:
        return (
            f"ProviderConfig(name={self.name!r}, model={self.model!r}, "
            f"api_key=<redacted from {self.api_key_env}>)"
        )

    __str__ = __repr__


def provider_config(
    provider: str,
    values: dict[str, str] | None = None,
    home: Path | str | None = None,
) -> ProviderConfig:
    """把 provider 名与凭证表解析成可用的配置；缺 Key 时报出键名。"""
    values = dict(values or {})
    key = (provider or "").strip().lower()
    canonical = PROVIDER_ALIASES.get(key)
    if canonical is None:
        raise LLMError(f"未知的 LLM provider：{provider}（可选：kimi/moonshot、deepseek）")

    if canonical == "kimi":
        coding_key = str(values.get(KIMI_CODING_KEY_ENV, "")).strip()
        open_key = str(values.get(KIMI_OPEN_KEY_ENV, "")).strip()
        model = str(values.get(KIMI_MODEL_ENV, "")).strip()
        base_override = str(values.get(KIMI_BASE_URL_ENV, "")).strip()

        def kimi(default_base: str, default_model: str, api_key: str, api_key_env: str) -> ProviderConfig:
            # 三条路径只有「默认端点 / 默认模型 / Key 来源」不同；KIMI_BASE_URL / KIMI_MODEL 一律可覆盖
            return ProviderConfig(
                name=canonical,
                base_url=base_override or default_base,
                model=model or default_model,
                api_key=api_key,
                api_key_env=api_key_env,
                base_url_env=KIMI_BASE_URL_ENV,
            )

        # 1) 显式配了 coding plan Key → 走 coding 端点
        if coding_key:
            return kimi(KIMI_CODING_BASE, KIMI_CODING_MODEL, coding_key, KIMI_CODING_KEY_ENV)

        # 2) 没有 Key → 复用 Kimi Code CLI 登录态（T-011，主路径）
        login = load_cli_login(home=home)
        if login is not None:
            if login.is_expired():
                raise LLMError(
                    f"Kimi Code CLI 登录态已过期（{login.source}），无法调用 {KIMI_CODING_BASE}。"
                    f"{RELOGIN_HINT}；也可以在 .env 配 {KIMI_CODING_KEY_ENV} 走 API Key。"
                )
            return kimi(KIMI_CODING_BASE, KIMI_CODING_MODEL, login.access_token, LOGIN_STATE_ENV_LABEL)

        # 3) 最后才是开放平台按量 Key
        if open_key:
            return kimi(KIMI_OPEN_PLATFORM_BASE, KIMI_OPEN_PLATFORM_MODEL, open_key, KIMI_OPEN_KEY_ENV)

        raise LLMError(
            "LLM 凭证缺失：三选一——"
            f"① 在 Kimi Code CLI 里 /login（工具会自动复用 {default_login_path(home).as_posix()} 的登录态）；"
            f"② 在 .env 填 {KIMI_CODING_KEY_ENV}（coding plan，端点 {KIMI_CODING_BASE}）；"
            f"③ 在 .env 填 {KIMI_OPEN_KEY_ENV}（开放平台按量，端点 {KIMI_OPEN_PLATFORM_BASE}）；"
            "其中 ②③ 两个 Key 不通用"
        )

    env_name, base_url, model = (
        "DEEPSEEK_API_KEY",
        "https://api.deepseek.com/v1",
        "deepseek-chat",
    )
    api_key = str(values.get(env_name, "")).strip()
    if not api_key:
        raise LLMError(
            f"LLM 凭证缺失：请在 .env 中填写 {env_name}（provider={canonical}，参考 .env.example）"
        )
    return ProviderConfig(
        name=canonical, base_url=base_url, model=model, api_key=api_key, api_key_env=env_name
    )


def resolve_provider(
    name: str | None,
    env_path: Path | str = DEFAULT_ENV_PATH,
    home: Path | str | None = None,
) -> str:
    """决定用哪个 provider：显式指定 > LLM_PROVIDER > 按 .env 里实际填了哪个 Key 兜底。"""
    if name:
        return name
    values = read_env_values(env_path)
    configured = (values.get("LLM_PROVIDER") or os.environ.get("LLM_PROVIDER", "")).strip().lower()
    if configured:
        return configured
    for key in ("KIMI_API_KEY", "MOONSHOT_API_KEY"):
        if (values.get(key) or "").strip():
            return "kimi"
    if (values.get("DEEPSEEK_API_KEY") or "").strip():
        return "deepseek"
    # 没有任何 Key：默认 kimi——有未过期的 CLI 登录态就走它（T-011 主路径），
    # 没有的话由 provider_config 报出「三选一」的配置提示。
    # （以前这里先读一遍登录态文件，但两个分支都返回 kimi，读了也白读。）
    return "kimi"


def read_env_values(env_path: Path | str = DEFAULT_ENV_PATH) -> dict[str, str]:
    """读取 .env（不存在时返回空表，允许纯环境变量运行）。"""
    try:
        return parse_env_file(env_path)
    except Exception:
        return {}


def config_for(
    provider: str | None = None,
    env_path: Path | str = DEFAULT_ENV_PATH,
    home: Path | str | None = None,
) -> ProviderConfig:
    values = read_env_values(env_path)
    merged = {name: os.environ.get(name, "") or values.get(name, "") for name in
              ("KIMI_API_KEY", "KIMI_BASE_URL", "KIMI_MODEL", "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY", "LLM_PROVIDER")}
    return provider_config(resolve_provider(provider, env_path, home=home), merged, home=home)


# T-024 M-04：可重试失败最多退避重试 2 次（1s → 2s）
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 1.0


class TransientLLMError(LLMError):
    """**可重试**的失败：429（限流）、5xx（服务端抽风）、超时/连接失败。

    T-024 M-04：与「额度用尽」「Key 无效」这类不可重试的失败区分开——
    前者退避重试有意义，后者重试只是浪费时间与额度。
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


# 额度/余额类关键字：这些 429/403 重试也没用，直接给中文提示
QUOTA_HINTS = (
    "insufficient",
    "quota",
    "balance",
    "exceeded your current",
    "billing",
    "credit",
    "余额",
    "额度不足",
)


def looks_like_quota_problem(detail: str) -> bool:
    text = str(detail or "").lower()
    return any(hint in text for hint in QUOTA_HINTS)


class RequestsTransport:
    """真实 HTTP 传输。失败只暴露状态码与异常类名，避免把 Key 或请求体带出去。"""

    def __init__(self, timeout: float = 120.0) -> None:
        self.timeout = timeout

    def request(self, method, url, *, headers=None, json_body=None, timeout=None):
        data = json.dumps(json_body, ensure_ascii=False).encode("utf-8") if json_body is not None else None
        request = urllib.request.Request(url, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                detail = ""
            # 429 / 5xx 归为可重试；额度类错误重试没意义，照旧当普通失败
            if (exc.code == 429 or 500 <= exc.code < 600) and not looks_like_quota_problem(detail):
                raise TransientLLMError(
                    f"LLM 返回 HTTP {exc.code}：{detail}", status=exc.code
                ) from None
            if exc.code == 429:
                raise LLMError(
                    f"LLM 额度或配额不足（HTTP 429）：{detail}；"
                    "请检查账户余额/套餐额度，或换个 provider（--provider deepseek）"
                ) from None
            raise LLMError(f"LLM 返回 HTTP {exc.code}：{detail}") from None
        except urllib.error.URLError as exc:
            # 超时与连接失败可重试
            reason = getattr(exc, "reason", exc)
            raise TransientLLMError(f"LLM 网络失败：{type(reason).__name__}") from None
        except TimeoutError:
            raise TransientLLMError("LLM 请求超时") from None
        except Exception as exc:
            raise LLMError(f"LLM 请求失败：{type(exc).__name__}") from None
        try:
            return json.loads(body)
        except ValueError:
            raise LLMError("LLM 返回了非 JSON 响应") from None


class LLMClient:
    """OpenAI 兼容的 chat/completions 客户端。"""

    def __init__(self, config: ProviderConfig, transport=None) -> None:
        self._config = config
        self._transport = transport if transport is not None else RequestsTransport()

    def __repr__(self) -> str:
        return f"LLMClient({self._config!r})"

    __str__ = __repr__

    @property
    def model(self) -> str:
        return self._config.model

    def complete(self, messages, *, temperature: float | None = None, sleep=None) -> str:
        """发起一次补全。

        T-024 M-04：429 / 5xx / 超时这类**可重试**失败会指数退避重试，最多 2 次；
        额度类与参数类失败**不重试**（重试只是白费时间）。
        """
        waiter = sleep or time.sleep
        attempts = max(1, MAX_RETRIES + 1)
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                return self._complete_once(messages, temperature=temperature)
            except TransientLLMError as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    break
                waiter(RETRY_BACKOFF_SECONDS * (2 ** attempt))
        raise LLMError(
            f"{last_error}（已重试 {MAX_RETRIES} 次仍失败；可能是网络或服务端限流，稍后再试）"
        ) from None

    def _complete_once(self, messages, *, temperature: float | None = None) -> str:
        url = self._config.base_url.rstrip("/") + "/chat/completions"
        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": list(messages),
            "stream": False,
        }
        # 实测：Kimi coding 模型只接受 temperature=1，传 0 会 HTTP 400
        # invalid temperature。默认不传该字段（交服务端默认值）；DeepSeek 无此限制，
        # 保持 temperature=0 以获得确定性输出。
        effective = temperature
        if effective is None and self._config.name == "deepseek":
            effective = 0.0
        if effective is not None:
            payload["temperature"] = effective
        try:
            response = self._transport.request(
                "POST",
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._config.api_key}",
                },
                json_body=payload,
            )
        except LLMError:
            raise
        except Exception as exc:
            # 传输层异常可能携带请求头（含 Key），只保留异常类型名
            raise LLMError(f"LLM 请求失败：{type(exc).__name__}") from None
        return _extract_content(response)


# --- 从 LLM 回复里取 JSON（提炼 / 出题 / 对齐 / 导入地图共用） -------------------

# 围栏必须**独占一行**（开头的 ``` 在行首、结尾的 ``` 独占一行）：JSON 字符串值里也可能出现 ```
# （比如步骤里写「参考 ```python …```」），不锚定行首的话会把那里当成围栏，取出半截 JSON。
# 合法 JSON 的字符串里不会有真换行，所以行首锚定的围栏不会落在字符串内部。
# 另：必须是 raw string——曾经 planner 写成普通字符串 "\\\\s"，正则匹配的是字面量 \s，围栏分支从来没生效过。
_JSON_FENCE_RE = re.compile(r"^```(?:json)?[ \t]*\n(.*?)\n```[ \t]*$", re.MULTILINE | re.DOTALL)
_JSON_DECODER = json.JSONDecoder()


class JSONExtractionError(ValueError):
    """LLM 回复里取不出 JSON。reason ∈ {"empty", "missing", "invalid"}，调用方据此给中文提示。"""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


def extract_json(raw: str):
    """从 LLM 回复里取出**第一个完整的 JSON 值**（对象或数组）。

    容忍三种实测出现过的"不听话"：```json 围栏、JSON 前面的寒暄、JSON 后面的说明文字
    （用 raw_decode，只解析到值结束为止）。先看围栏里的内容，围栏里取不到再看全文。

    失败抛 JSONExtractionError：empty（空回复）/ missing（没有 { 或 [）/ invalid（有但解析不了）。
    """
    text = str(raw or "").strip()
    if not text:
        raise JSONExtractionError("empty")

    candidates = []
    fenced = _JSON_FENCE_RE.search(text)
    if fenced:
        candidates.append(fenced.group(1).strip())
    candidates.append(text)

    saw_start = False
    last_error: Exception | None = None
    for candidate in candidates:
        for start in sorted(i for i in (candidate.find("{"), candidate.find("[")) if i >= 0):
            saw_start = True
            try:
                value, _ = _JSON_DECODER.raw_decode(candidate[start:])
                return value
            except ValueError as exc:
                last_error = exc
    if not saw_start:
        raise JSONExtractionError("missing")
    raise JSONExtractionError("invalid", str(last_error))


def _extract_content(response) -> str:
    if not isinstance(response, dict):
        raise LLMError("LLM 返回了非对象响应")
    if "error" in response and response.get("error"):
        error = response["error"]
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise LLMError(f"LLM 返回错误：{message}")
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMError("LLM 响应缺少 choices")
    first = choices[0] or {}
    message = first.get("message") or {}
    content = message.get("content")
    if content is None:
        raise LLMError("LLM 响应缺少 message.content")
    return str(content)
