---
title: 【T-031】 DSH 接力（F-14）
tags: [项目, 任务, TDD, AgentTeam]
status: 已验收（降级路径）
---

# 【T-031】 DSH 接力（F-14）

## 客户要求

> 提交作业后任务卡片出现「在 DSH 中继续」。

## ① 先探测：本机 harness web 有没有「创建会话」的 API

任务卡要求先探测再决定直通/降级。**用 Agent Team 分两条线并行**：

| 角色 | 任务 | 产物 |
| --- | --- | --- |
| prober（只读取证） | 找会话创建 API 与鉴权机制 | `profile/_t031_probe.md`（382 行） |
| handoff-dev | 只做 `src/handoff.py` 上下文组装 | 23 项测试 |
| Lead（我） | 接线 + 实测 + 降级判定 | `src/dashboard.py`/`src/cli.py` + 17 项测试 |

### prober 的结论：**有 API**

- `POST http://127.0.0.1:19387/api/session/create`，endpoint = `session/create`；配套 `session/prompt`/`list`/`fork`
  权威来源：app.asar 内**可读的 ESM 源码** `dsh-api-session-controller/lib/typert.host.js`（端点命名规则见 `dsh-api-gateway/lib/client.js`）
- 401 不是没有接口，而是**认证先于路由**（只有 `/api` 通道、只收 POST）
- 建议的零令牌方案：**看板与 19387 同源时**，页内 fetch 自动带 HttpOnly cookie

### 我的复核（决定性）

对 prober 的「同源」前提做了浏览器实测，**前提不成立**：

| 探测 | 结果 |
| --- | --- |
| 看板端口（8945）跨源调 19387 `/api/session/create` | **CORS 挡下**：not a secure context and the resource is in more-private address space loopback |
| 新开浏览器上下文访问 19387 | 正文是 `dsh web authentication required`，**cookie 列表为空** |
| 在 19387 页面内同源 fetch | **401**（没有有效 cookie 就是 401） |

而桌面版把 `--no-open` 写死、启动令牌只经 IPC 上报（`dsh-desktop-host/lib/index.js`），**令牌无磁盘副本、事后不可取回**。

> `.credentials.yaml` 里有 `browser-session.payload.secret`，**理论上可以自签 cookie**——
> 但那是**绕过鉴权**，本任务明确不做；prober 也主动记录了「未使用」。
> 所以：**直通不可用 → 走降级**，并把原因如实写进结果里，而不是含糊说「请手动」。

## ② 修法

| 层 | 做法 |
| --- | --- |
| 新模块 | `src/handoff.py`（handoff-dev 交付）：五段上下文 + 提问引导；一任务一文件；原子写 |
| 固定动作 | `handoff` 进白名单，参数白名单**恰为** `{task}` |
| 看板 | 任务卡片上「在 DSH 中继续」**次按钮**（描边），位置在「提交作业」下方；成功后 303 带该卡锚点 |
| 结果 | 接力文件路径（**可照抄**）+ 五段说明 + 为什么不自动开 + 可粘贴的 4 条提问 + headless 替代命令 |

## ③ TDD 记录

- `tests/test_t031_handoff.py`（handoff-dev，23 项）
- `tests/test_t031_handoff_wiring.py`（我，17 项）：白名单 / 按钮位置 / 锚点 / 生成文件 / 重复点击同文件 /
  未知时间戳 / 带提交代码 / **降级说明必须如实** / **路径可照抄**
- 全项目 **684 项测试通过**

## ④ 实测（真实 HTTP + 真实 Chrome）

| 项 | 结果 |
| --- | --- |
| 按钮 | 1 个、可见、文案「在 DSH 中继续」、次按钮样式 129×35、**在「提交作业」下方** |
| 点击 | 303 → `/tasks#task-2026-09-27-10-00`（带锚点） |
| 生成 | `profile/handoff/2026-09-27-1000.md`，五段齐全、含提交的代码、含画像状态、含书籍章节 |
| 重复点击 | 仍是**同一个文件**（1 个） |
| 白名单 | 多给 `cmd` → **400**「动作 handoff 不接受参数：cmd」；缺 `task` → 400 |
| 结果文本 | 含「不绕过鉴权」「同源 cookie」「--profile headless」与 4 条可粘贴提问 |
| `pageerror` | 无 |

![任务中心：DSH 接力按钮](项目文档/assets/任务中心-DSH接力按钮.png)

## ⑤ 我在验收时抓到并修掉的两个问题

1. **结果里的路径不能照抄**。原来按 `target.parent.parent` 算相对路径，把 `profile/` 前缀吃掉了，
   给出 `_t031_scratch\handoff\….md`——用户照抄去跑命令会找不到文件。
   改成 `os.path.relpath(path, Path.cwd())`，并补了一条「路径照抄必须存在」的回归测试。
2. **提交过的代码没有进上下文**。交接时发现 `ReviewRecord` 只存了评价/建议，
   代码写进了 `<details>` 但 `parse_reviews` 没读回来 → 接力文件里没有学生的代码。
   已给 `ReviewRecord` 加 `code` 字段并从围栏里解析回来。

## ⑥ 完成结论

- 状态：**已验收（降级路径）**；全项目 684 项测试通过
- 交付：`src/handoff.py`（新）、`src/dashboard.py`、`src/cli.py`、`src/planner.py`（ReviewRecord.code）
- **直通未实现**：本机桌面版拿不到会话凭据，且不绕过鉴权；结论与证据留在 `profile/_t031_probe.md`
- 需要客户拍板的开放项（若要真正「一键在 DSH 里继续」，需要其中一条）：
  ① 看板由 DSH web 同源托管；② 用户手动把带令牌的 URL 交给看板一次；③ 用 `dsh --profile headless` 走命令行（现已作为替代路径写在结果里）。