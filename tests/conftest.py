"""测试环境隔离：清掉外层进程注入的凭证 / 开关（T-048）。

背景（2026-09-29 实测，不是推测）：
DSH 面板把 `.env` 的值注入到了**进程级**环境变量里。实测本机 shell 进程内
`LLM_PROVIDER=kimi`、`FEISHU_APP_ID=<20 字符>` 同时存在，而用户级（持久）没有。
这两条会被下面两处实现读到，于是「在 tmp_path 写一个干净的 .env」的用例被击穿：

- `src/llm.py:167`  `resolve_provider` → `os.environ.get("LLM_PROVIDER")`
- `src/credentials.py:56`  `_lookup` → 优先 `os.environ`，其次 .env 文件
  （`src/llm.py:166` 读文件里的 LLM_PROVIDER 优先于 os.environ，所以只清
   os.environ 里的值不会改掉「文件说了算」的既有语义）

实跑回包（未加本 fixture 时）：
    tests/test_t003_llm_distill.py::test_resolve_provider_prefers_configured_then_available_key
        AssertionError: assert 'kimi' == 'deepseek'
        （tmp 里只写了 DEEPSEEK_API_KEY，却被 os.environ 的 LLM_PROVIDER 顶掉）
    tests/test_t001_feishu_connectivity.py::test_load_credentials_missing_key_names_key_not_value
        Failed: DID NOT RAISE CredentialError
        （tmp .env 故意缺 FEISHU_APP_ID，被 os.environ 补齐，于是不报缺键）

同一批文件里的兄弟用例本来就各自 `monkeypatch.delenv`（test_t001:83、
test_t002:111、test_t003:527），说明「测前先清外部注入」是本项目既有口径；
本 fixture 只把它提到全局，省得下次再漏一个。

monkeypatch 自带用后还原，测试内 `monkeypatch.setenv(...)` 依旧生效。

T-050 补充（同一类问题的第二个口子）：**LLM 凭证也会从真机漏进来**。
`make_llm_completer()` 在没传 home 时会去读 `~/.kimi-code/credentials/kimi-code.json`；
作者本机有登录态、协作者机器没有，于是同一条用例在两边走不同分支——
`test_t034_chat_panel.py::test_history_overflow_keeps_handoff_in_real_prompt`
在协作者机器上稳定失败，在作者机器上则会**真的去调 LLM**。
所以非 `real` 用例一律：

- 清掉 LLM Key 类环境变量（KIMI_API_KEY / MOONSHOT_API_KEY / DEEPSEEK_API_KEY …）；
- 把「没显式传 home」时的登录态路径指到一个空目录（显式传 home 的用例不受影响）。

`real` 用例（默认跳过，`-m real` 才跑）保持读真机环境。
"""

from __future__ import annotations

import pytest

# 实测会被外层注入、且会被 src 读到的键。
LEAKY_ENV_KEYS = (
    "LLM_PROVIDER",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
)

# 会让 make_llm_completer 在测试里「意外可用」的键（T-050）。
LLM_ENV_KEYS = (
    "KIMI_API_KEY",
    "KIMI_BASE_URL",
    "KIMI_MODEL",
    "MOONSHOT_API_KEY",
    "DEEPSEEK_API_KEY",
)


def _is_real(request: pytest.FixtureRequest) -> bool:
    return request.node.get_closest_marker("real") is not None


@pytest.fixture(autouse=True)
def _isolate_ambient_env(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """每个用例开跑前清掉外层注入的凭证 / 开关，保证 tmp_path 里的 .env 说话算数。"""
    for key in LEAKY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    if _is_real(request):
        return
    for key in LLM_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def _isolate_cli_login(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """没显式传 home 的调用读不到真机 Kimi 登录态（T-050）。"""
    if _is_real(request):
        return
    from src import cli_login

    empty_home = tmp_path_factory.mktemp("no-login-home")
    real_default = cli_login.default_login_path
    monkeypatch.setattr(
        cli_login,
        "default_login_path",
        lambda home=None: real_default(empty_home if home is None else home),
    )
