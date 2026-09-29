---
title: 【T-033】 handoff 自动弹终端
tags: [项目, 任务, TDD]
status: 已验收
---

# 【T-033】 handoff 自动弹终端

## 客户反馈

> 点「在 DSH 中继续」没有跳转终端。

## 修法

| 项 | 做法 |
| --- | --- |
| 新模块 | `src/terminal.py`：`quote_for_cmd` / `build_chat_command_line` / `build_start_argv` / `launch_chat_terminal` |
| 弹窗 | `cmd /c start "" cmd /k <chat 命令>`——**空标题**是必须的（不加的话 start 会把命令当窗口标题） |
| 保活 | `/k` 让窗口留着继续追问；用 **Popen 不等待**（`run` 会被 /k 挂住，实测超时） |
| 引号 | 路径带空格自动加双引号；内部引号按 cmd 规则翻倍 |
| 静默降级 | 非 Windows / 无 cmd / 任何异常 → 返回 `False`，**不报错**，原文字指引照旧 |
| 按钮 | 文案改「在 DSH 中继续（弹终端）」，且**从 `ACTION_LABELS` 取**（避免改了标签忘改按钮） |

## TDD 记录

- `tests/test_t033_terminal.py`（22 项）：引号规则 / 命令构造 / `start` argv（含 /k 与空标题）/
  非 Windows 降级 / OSError·FileNotFoundError·RuntimeError 全吞 / Popen 不等待 / 空格路径加引号 / 按钮文案 /
  弹窗失败动作仍成功 / 输出含降级与鉴权说明
- 全项目 **742 项测试通过**

## 实测（真机 Windows）

| 项 | 结果 |
| --- | --- |
| 命令构造 | `argv = [cmd.exe, /c, start, "", cmd, /k, <chat 命令>]`，7 个元素 |
| 真机解析 | `quote_for_cmd(r"C:\\Program Files\\Py\\py.exe")` → 带双引号 ✅ |
| **真弹一次** | `launch_chat_terminal(...)` 返回 `True`，**控制台进程 37 → 39** |
| 走 HTTP 点按钮 | 303 → `/tasks#task-2026-09-27-10-00`，控制台进程 **37 → 39**（新窗口真的出现） |
| 按钮文案 | 页面上有「在 DSH 中继续（弹终端）」 |
| 输出文本 | 含【已弹出终端】+ 手动指引领 + **不绕过鉴权**说明 |

## 途中修掉的两处回归

1. **T-031 的降级说明被我删了**——它的测试立刻报红（`test_handoff_result_explains_why_manual`）。
   已把「直连需要 19387 同源 cookie、不绕过鉴权」这段在**两条分支里都保留**（这是事实，跟弹不弹窗无关）。
2. **README 目录树缺 `terminal.py`**——目录树一致性测试抓出来的。

## 完成结论

- 状态：**已验收**；全项目 742 项测试通过
- 交付：`src/terminal.py`（新）、`src/cli.py`（op_handoff 弹窗 + 静默降级）、`src/dashboard.py`（按钮文案取 ACTION_LABELS）
- 安全性：弹窗命令用**列表参数 + shell=False**；引号由我们按 cmd 规则处理，不把控制权交给 shell