---
title: 【T-002】 sync 命令完整实现
aliases:
  - 当前任务卡
tags:
  - 项目
  - 任务
  - TDD
status: 已实现待验收（A-01 单文档部分待客户手工复核）
---

# 【T-002】 sync 命令完整实现

## 任务边界

- 所属模块：[[模块-笔记同步]]
- 对应需求/验收：[[01-需求与范围确认]] F-01；A-01 的单文档部分
- 目标行为：执行 sync 后，文档块被拉全、按类型转成 markdown、写入 notes/<文档ID>.md；任何一步失败都不改动已有文件。
- 本任务不做：不递归子文档（T-009）、不做增量同步、不做知识提炼（[[模块-知识画像]]）、不串联其余四个命令（T-007）。
- 前置依赖：T-001（已验收）。

## 验收示例

### 正常路径

- 给定：.env 凭证有效、应用已开通权限
- 当：python -m src.cli sync <wiki链接>
- 则：生成 notes/<docxID>.md，标题/段落/列表/代码块结构正确，stderr 提示已写入路径，退出码 0

### 异常或边界路径

- 给定：notes/<id>.md 已存在
- 当：飞书接口失败或块结构损坏
- 则：报错、退出码 1，已有文件字节不变，且不残留 .tmp 文件

## TDD 记录

### 1. 失败测试

- 测试文件/名称：tests/test_t002_sync.py（23 项；全项目 51 项）
- 它要描述的行为：分页取全块、六类块正确转 markdown、未知块降级占位、落盘原子、失败不动旧文件
- 首次失败原因：ModuleNotFoundError: No module named 'src.sync'（实现前）

### 2. 最小实现

- 拟修改文件：src/sync.py（新增）、src/feishu.py（新增 fetch_blocks）、src/cli.py（sync 接完整链路）
- 最小改动说明：
  - src/sync.py：_Renderer 按块渲染（page/heading1-9/text/bullet/ordered/code/quote + 未知块占位）、render_markdown、write_note_atomic、sync_document
  - src/feishu.py：fetch_blocks 分页聚合（page_size=500，跟随 page_token）
  - src/cli.py：sync 先落盘再打印正文，stderr 报写入路径；新增 notes_dir 参数便于测试注入
- 不新增的复杂度：不引入 markdown 库、不做多层列表缩进美化、不做图片下载、不做表格渲染（降级占位）

### 3. 验证结果

| 验证项 | 结果 | 证据 |
| --- | --- | --- |
| 新增/修改测试 | 通过 | python -m pytest -q → 51 passed |
| 受影响的相关测试 | 通过 | T-001 的 28 项随 sync 流程变化同步更新后仍全绿 |
| 手工验收（真实文档） | 通过 | 4 次真实请求全成功，落盘 notes/Ueefd7CU9ovrKbxjAWXcFl5Xndb.md，23 行与飞书正文逐行对齐 |

## 真实文档实测（A-01 单文档部分）

真实凭证执行 sync <测试 wiki 链接>：

| 步骤 | 接口 | 结果 |
| --- | --- | --- |
| 1 | POST /auth/v3/tenant_access_token/internal | ok |
| 2 | GET /wiki/v2/spaces/get_node | ok（obj_type=docx） |
| 3 | GET /docx/v1/documents/{id}/blocks | ok，items=24，has_more=false |
| 4 | GET /docx/v1/documents/{id}/raw_content | ok |

落盘结果：notes/Ueefd7CU9ovrKbxjAWXcFl5Xndb.md，23 行，8 个 ## 、4 个 ###、0 个占位块、0 个残留 .tmp。

**内容一致性核对方法**：把「每个块的文本元素 + 提及标题」按块顺序拼起来，与飞书 raw_content 逐行比对——23 行全部对齐，唯一差异是提及在 markdown 里被标成 [文档提及: 标题]，属于不丢内容的有意标注。

## 实测发现的真实文档形状（重要，影响后续实现）

这四条都是打桩测试想不到、只有跑真实文档才暴露的：

1. **整篇文档的块都挂在 page 块下**（parent_id 都指向 page）。page 是容器不是层级，若当一层算，整篇笔记会统一多两个空格缩进。已修：page 的子块深度不递增。
2. **文档提及（mention_doc）旁边带一个空的 text_run**。只判 text_run 会把提及吞成空串；且飞书把 title 计入 raw_content（145 = 72 文本 + 73 提及标题），所以提及必须带标题渲染，否则就是静默丢内容。已修。
3. **块类型直方图**：1=page、2=text、3=headings1、4=heading2、12=bullet、13=ordered、14=code、15=quote_container；实测文档只出现 1/2/3/4。
4. **代码块 language 枚举**：1=plaintext、22=go、48=python。第一版代码块测试里我写错了这个数字，实测确认后改正。

## 实施日志（短期）

- 2026-09-26：先写 23 项失败测试，再实现 src/sync.py 与 fetch_blocks。
- 2026-09-26：修掉测试自身 4 处缺陷（合成 block_id 重复触发去重、style 嵌套位置写错、代码块 language 编号写错、T-001 stub 双重包装/未调用工厂）。
- 2026-09-26：真实文档跑通后，发现并修复 2 个打桩测不出的实现缺口（page 容器缩进、mention 吞文本），并补 3 条回归测试。
- 2026-09-26：收尾凭据审计：38 个文件扫描，凭证值泄漏 0 处；notes/ 已在 .gitignore。

## 完成结论

- 状态：已实现待验收（代码与实测均通过，等客户手工复核 A-01 内容一致）
- 交付结果：src/sync.py + fetch_blocks + CLI 落盘链路；全项目 51 项测试通过
- 需要回写的长期事实：[[模块-笔记同步]] 的真实文档形状与实现定位（本次已回写）
- 后续任务：T-009 子文档递归；T-007 串联其余命令
