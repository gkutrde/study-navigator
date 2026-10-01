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

刻意只清这三个键：其余（KIMI_API_KEY / DEEPSEEK_API_KEY / …）实测未注入，
不动它们以免影响 `/real` 用例。monkeypatch 自带用后还原，测试内
`monkeypatch.setenv(...)` 依旧生效。
"""

from __future__ import annotations

import pytest

# 实测会被外层注入、且会被 src 读到的键。
LEAKY_ENV_KEYS = (
    "LLM_PROVIDER",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
)


@pytest.fixture(autouse=True)
def _isolate_ambient_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个用例开跑前清掉外层注入的凭证 / 开关，保证 tmp_path 里的 .env 说话算数。"""
    for key in LEAKY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
