---
title: 【T-003】 LLM 连通验证与 prompt 雏形
aliases:
  - 当前任务卡
tags:
  - 项目
  - 任务
  - TDD
status: 已实现待验收（DeepSeek 已实测；Kimi 待客户 Key）
---

# 【T-003】 LLM 连通验证与 prompt 雏形

## 任务边界

- 所属模块：[[模块-知识画像]]
- 对应需求/验收：[[01-需求与范围确认]] F-02；A-02 的前置（本卡只出结构化结果，不写画像文件）
- 目标行为：给定一篇笔记文本，调用 LLM 输出结构化知识点列表：名称 + 状态（学过/做过/存疑）+ 证据。
- 本任务不做：不写/不合并 profile/knowledge.md（T-004）、不生成任务（T-005）、不做知识地图（T-010）、不串联五个命令（T-007）。
- 前置依赖：无。

## 验收示例

### 正常路径

- 给定：.env 中相应 provider 的 Key 有效，且有一篇笔记文件
- 当：python -m src.cli distill <笔记文件>
- 则：stdout 打印结构化知识点（每条含名称、状态、证据），退出码 0

### 异常或边界路径

- 给定：笔记文件不存在
- 当：执行 distill
- 则：退出码 2，提示文件路径
- 给定：LLM 返回不可解析内容或接口失败
- 当：执行 distill
- 则：退出码 1，报「笔记未改动」，画像/地图不受影响

## TDD 记录

### 1. 失败测试

- 测试文件/名称：tests/test_t003_llm_distill.py（40 项；全项目 94 项）
- 它要描述的行为：provider 解析与 Key 缺失报键名、chat/completions 请求形状、三态合法性与证据必填、LLM 失败可重试且不泄露 Key
- 首次失败原因：ModuleNotFoundError: No module named 'src.distill'（实现前）

### 2. 最小实现

- 拟修改文件：src/llm.py（新增）、src/distill.py（新增）、src/cli.py（新增 distill 命令并按命令拆分 handler）
- 最小改动说明：
  - src/llm.py：ProviderConfig + provider_config/resolve_provider/config_for + LLMClient（OpenAI 兼容 chat/completions）+ RequestsTransport（标准库 urllib）
  - src/distill.py：SYSTEM_PROMPT（三态约束 + 禁止臆断）、build_distill_messages、parse_knowledge_points、distill_note、format_points
  - src/cli.py：distill <笔记文件> [--json]；人读格式写 stderr、机器可读写 stdout；sync 行为不变
- 不新增的复杂度：不引入 openai SDK（标准库够用）、不加重试、不做流式、不做 JSON Mode（先用 prompt 约束 + 解析兜底）

## 实测结论（真实网络）

### provider 与模型（官方文档核对，2026-09-26）

| 项目 | 值 | 来源 |
| --- | --- | --- |
| Kimi base_url（OpenAI 兼容） | https://api.moonshot.cn/v1 | platform.kimi.com/docs/api/overview |
| Kimi 认证 | Authorization: Bearer $MOONSHOT_API_KEY | 同上 |
| Kimi 当前模型 | kimi-k3 / kimi-k2.7-code / kimi-k2.7-code-highspeed / kimi-k2.6 | platform.kimi.com/docs/models |
| 已下线 | moonshot-v1 全系列（含 moonshot-v1-8k）、kimi-k2 系列、kimi-latest | 同上 |

**踩坑并修正**：第一版把 Kimi 默认模型写成 moonshot-v1-8k，查官方文档发现该系列已于 2026-08-31 下线，已改为 kimi-k2.7-code，并补两条回归测试锁住「不得回退到已下线模型」。

### Kimi coding plan 是另一个平台（客户指出后查证并修正）

客户使用 Kimi Code 的 **coding plan（会员套餐）**，与开放平台按量是两个互不通用的平台。官方文档
（www.kimi.com/code/docs/kimi-code/faq.html）明确：

| 平台 | Base URL | 计费 | Key 入口 |
| --- | --- | --- | --- |
| Kimi Code 会员（coding plan） | 国内 https://api.kimi.com/coding/ ；海外 https://api.kimi.ai/coding/ | 会员订阅含额度 | Kimi Code 控制台 |
| Kimi 开放平台（按量） | 国内 https://api.moonshot.cn/v1 ；海外 https://api.moonshot.ai/v1 | 按量付费 | platform.kimi.com |

文档原文强调「Kimi Code 会员权益与 Kimi 开放平台**有不同的 Base URL**，配置时请注意 Base URL 与 API Key 的匹配」。
Kimi Code CLI 的 provider 文档也给出 `base_url = "https://api.kimi.com/coding/v1"`。

**端点协议探测**（用无效 Key 打三个候选端点）：`/coding/v1/chat/completions`、`/coding/v1/messages`、
`/coding/v1/models` 均返回 401 `invalid_authentication_error`——是鉴权错误而不是 404，
说明这些路由存在；因此 **coding 端点支持 OpenAI 兼容的 chat/completions**，现有 LLMClient 可直接复用。

据此修正实现：

- `provider=kimi` 优先用 `KIMI_API_KEY` 走 `https://api.kimi.com/coding/v1`（coding plan）；
- 只有 `KIMI_API_KEY` 缺失、但配了 `MOONSHOT_API_KEY` 时，才退回开放平台按量端点；
- 两个 Key 都没有时，报错同时点出两个键名与「两者不通用」；
- 支持 `KIMI_BASE_URL` 覆盖端点（走代理/自建网关）；
- model 为 `kimi-k2.7-code`，并保留「不得回退到已下线的 moonshot-v1」回归测试。

**降级说明**：客户 `.env` 里 `LLM_PROVIDER=deepseek`，所以默认仍走 DeepSeek；
要用 coding plan，把 `KIMI_API_KEY` 填上并把 `LLM_PROVIDER` 改成 `kimi` 即可（也可不填 LLM_PROVIDER，代码会自动选中已配 Key 的 provider）。

### DeepSeek 实测（真实 Key，未打印任何凭证）

样例笔记（三小节：列表/字典/循环）的输出：

    [学过] 列表（Python 基础） — 证据：「列表」小节：列表用方括号定义…
    [学过] 字典（Python 基础） — 证据：「字典」小节：字典用花括号定义…
    [学过] for 循环（Python 基础） — 证据：「循环」小节：for 循环可以遍历列表和字典。
    [存疑] while 循环（Python 基础） — 证据：「循环」小节仅一句：while 循环靠条件控制，无示例或细节。

- 4 个知识点，level 全在三态内，证据全部非空。
- 模型自己把「只有一句、无示例」的 while 循环判成「存疑」——「不得臆断已掌握」这条规则确实生效。

真实飞书笔记（notes/Ueefd7CU9ovrKbxjAWXcFl5Xndb.md，265 字，实际是一份主题清单）：

- 11 个知识点，等级分布 存疑 11 / 学过 0 / 做过 0，全部带证据，topic 为「Python 基础」。
- 这份笔记确实只有标题与主题提及、没有解释和代码，**全判存疑是正确结果**，不是提炼失败。
- 完整结果留在 notes/_distill_result_sample.json（notes/ 已 gitignore，由客户自行查看）。

### Kimi 实测状态

- MOONSHOT_API_KEY 目前为空，因此 **Kimi 未做真实网络验证**，待客户填 Key 后重跑。
- 降级路径已实现并有测试：首选 provider 没配 Key 而另一个配了，会自动降级并在 stderr 说明；实测 env 为 LLM_PROVIDER=deepseek，直接走 deepseek，不触发降级。

## 实施日志（短期）

- 2026-09-26：先写 32 项失败测试，再实现 src/llm.py、src/distill.py 与 CLI distill。
- 2026-09-26：查官方文档修正 Kimi 模型名（moonshot-v1-8k 已下线 → kimi-k2.7-code），补回归测试。
- 2026-09-26：修掉自己的 4 个错误：provider 降级逻辑（首选缺 Key 时直接抛错、没走到备份 provider），：占位符替换把 docstring 吃掉（语法错误）、围栏正则残留占位符导致 json 围栏解析失败、证据回填误把「文件路径」当笔记正文搜索。
- 2026-09-26：客户指出用的是 Kimi coding plan；查官方文档确认 coding plan 与开放平台是两个平台（端点、Key 均不同），并探测确认 coding 端点支持 OpenAI 兼容协议；据此把 provider 表改成 coding plan 优先，补 7 条测试（全项目 94 项）。
- 2026-09-26：收尾凭据审计：真实密钥（DEEPSEEK_API_KEY / FEISHU_APP_ID / FEISHU_APP_SECRET）泄漏 0 处。

## 完成结论

- 状态：已实现待验收（DeepSeek 实测通过；Kimi 等 Key）
- 交付结果：src/llm.py + src/distill.py + distill 命令；全项目 94 项测试通过
- 需要回写的长期事实：[[模块-知识画像]] 的实现定位与 prompt 约定；[[02-系统架构]] 的 LLM 模型名更新（本次已回写）
- 后续任务：T-004 画像文件结构与合并逻辑（前置 T-003 已满足）
