---
title: 【T-011】 Kimi 登录态复用
aliases:
  - 当前任务卡
tags:
  - 项目
  - 任务
  - TDD
status: 已验收（实测通过）
---

# 【T-011】 Kimi 登录态复用

## 任务边界

- 所属模块：[[模块-知识画像]]
- 对应需求/验收：[[04-任务与验收清单]] T-011（P1）；LLM 凭证来源的可用性改进
- 目标行为：主路径改为复用 Kimi Code CLI 的登录态——读 ~/.kimi-code/credentials/kimi-code.json 的 access_token，以 Bearer 调 api.kimi.com/coding/v1；过期时提示去 CLI 重新登录，不实现自动刷新。
- 本任务不做：不做 OAuth 自动刷新、不写回 CLI 凭证文件、不代理/转发、不改 sync 与提炼的业务逻辑。
- 前置依赖：T-003（已验收）。

## 验收示例

### 正常路径

- 给定：.env 未配任何 Kimi Key，但本机 Kimi Code CLI 已登录
- 当：python -m src.cli distill <笔记文件> --provider kimi
- 则：成功返回结构化知识点，退出码 0

### 异常或边界路径

- 给定：登录态已过期且 .env 没有 Key
- 当：执行同一命令
- 则：退出码 1，中文提示「登录态已过期…请重新登录」（不自动刷新）
- 给定：显式配了 KIMI_API_KEY
- 当：执行同一命令
- 则：按 Key 走，不悄悄改用登录态

## TDD 记录

### 1. 失败测试

- 测试文件/名称：tests/test_t011_kimi_login.py（19 项；全项目 115 项）
- 它要描述的行为：登录态读写与过期判定、登录态优先于 Key、过期给中文可操作提示、令牌不泄漏、coding 端点的请求形状
- 首次失败原因：ModuleNotFoundError: No module named 'src.cli_login'（实现前）

### 2. 最小实现

- 拟修改文件：src/cli_login.py（新增）、src/llm.py（provider 选择接登录态、temperature 按 provider 处理）、src/cli.py（distill 增加 --provider 与 home 注入）
- 最小改动说明：
  - src/cli_login.py：CliLogin + load_cli_login（文件缺失/损坏/无 token 一律返回 None）+ 过期判定 + 重新登录提示文案
  - src/llm.py：provider=kimi 时凭证优先级 = KIMI_API_KEY > CLI 登录态 > MOONSHOT_API_KEY；登录态过期则报错提示重新登录
  - src/cli.py：--provider kimi|deepseek（显式指定就不再自动降级）、home 参数便于测试注入
- 不新增的复杂度：不做 refresh_token 自动续期、不做凭证缓存落盘、不引入 OAuth 客户端库

## 实测结论（真实登录态）

环境里**没有任何 Kimi Key**（KIMI_API_KEY / MOONSHOT_API_KEY 均未设置），仅凭 CLI 登录态调用：

| 项目 | 结果 |
| --- | --- |
| 登录态来源 | ~/.kimi-code/credentials/kimi-code.json（scope=kimi-code，token_type=Bearer） |
| 调用结果 | 退出码 0，耗时 9.2s |
| 输出 | 3 个知识点（列表/字典/循环，均「学过」，证据非空） |
| 令牌泄漏 | 否（stderr/stdout 均不含 access_token） |

### 实测发现的三个关键事实

1. **可用模型名与开放平台不同**：登录态端点 GET /coding/v1/models 返回
   kimi-for-coding、kimi-for-coding-highspeed、k3、k3-256k。我此前按平台文档猜的 kimi-k2.7-code
   在 coding 端点并不适用，已改为 kimi-for-coding（可用 KIMI_MODEL 覆盖）。
2. **coding 模型只接受 temperature=1**：传 0 会 HTTP 400 invalid temperature。
   已改为默认不传 temperature（交服务端默认），DeepSeek 仍传 0 保持确定性。
3. **凭证文件是 OAuth 结构**：含 access_token / refresh_token / expires_at / scope / token_type；
   expires_at 是秒级时间戳，可离线判断是否过期。实测时观察到 token 有效期约 10 分钟级别，
   因此「过期提示重新登录」是常见路径而不是罕见分支。

## 实施日志（短期）

- 2026-09-26：先写 19 项失败测试，再实现 src/cli_login.py 与 provider 选择。
- 2026-09-26：实测报 HTTP 400 invalid temperature，据此修 temperature 策略（先写测试再改）。
- 2026-09-26：发现 T-003 的「缺 Key」用例会被本机真实登录态污染（T-011 之后多了一条凭证路径），
  给 T-003 测试加了 autouse fixture 隔离，并将 3 处模型名断言按实测更新为 kimi-for-coding。
- 2026-09-26：凭据审计：登录态令牌未出现在任何文件与输出中。

## 完成结论

- 状态：已验收（三项验收项均实测通过）
- 交付结果：src/cli_login.py + provider 优先级调整 + distill 的 --provider 参数；全项目 115 项测试通过
- 需要回写的长期事实：[[模块-知识画像]] 的凭证优先级与 coding 模型名；本次已回写
- 后续任务：T-004 画像文件结构与合并逻辑
