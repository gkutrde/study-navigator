# T-050 代码质量优化 · 变更清单

> 范围：后端 `src/`、看板 `src/dashboard.py`、DSH 插件 `plugin/src/`（含「插件只在「学习领航员」工作区启用」）。
> 分支：`opt/code-quality`（基于 `0a050be`）。日期：2026-10-02。

## 一、结论先看

| 项 | 结果 |
| --- | --- |
| 全量测试 | `python -m pytest -q` → **1113 passed**, 4 deselected（`real` 标记，默认跳过）。基线是 1029 passed + 2 failed（两条都是环境相关，见 §3.1） |
| 插件 | `pnpm build` ✅ / `pnpm typecheck` ✅（基线根本跑不起来）/ `pnpm test` ✅（两条契约脚本共 70 项检查） |
| 新增用例 | 82 条 pytest + 44 项插件契约检查；**后端/看板的 71 条新用例放到原代码（`0a050be` 的 worktree）上跑：59 条失败**，没失败的 12 条是守护这次重构的用例（原代码本来就对，防止被改坏），不对应 bug |
| 代码量 | `src/` 净减 309 行（+1275 / −1584），同时多了注释与新功能；`plugin/src/` 净增 254 行（工作区过滤 + 两代宿主接缝） |
| 修掉的问题 | **17 个**原有问题（§3.1–3.2，每个都有实测或复现，不是推测）+ 独立复审发现的 7 处（§3.3，其中 1 处是我这次引入的回归） |
| 真机 | 看板：浏览器在 `profile/` **副本**上实测改状态 / 讲解 / 删除 / 聊天渲染；插件：本机 **DSH 0.2.0-rc.1**（`E:\deepseek-harness` 源码构建）用**独立 `DSH_HOME`** 装插件实测，没碰你的 `~/.dsh` 与仓库真实数据 |
| 独立复审 | 交付前另起一个审查代理只读审了整份 diff：找出 1 个我引入的回归（统一后的 JSON 围栏正则没锚定行首，JSON 字符串里的 ``` 会被当成围栏）和 6 个小问题，**都已修掉并补了用例**（§3.3） |

## 二、需要原作者拍板的取舍

这些是我做了、但你可能有不同看法的决定；每条都容易回退。

1. **看板加了请求来源校验**（`dashboard.request_guard`）。看板绑 127.0.0.1，但浏览器里**任何网站**都能往它发请求：
   别的网站一个 `<form method=post action="http://127.0.0.1:8765/action/chat">` 就能触发 `chat`（会起一个能读写项目目录的 dsh 进程），
   DNS rebinding 还能读 `/file`。现在：`Host` 必须是本机回环名；写请求带了 `Origin/Referer` 就必须同源，否则 403。
   **不是登录鉴权**（01「明确不做」不变），不带 `Origin` 的请求（命令行、测试）照常放行，看板自己的页面完全不受影响（浏览器实测）。
2. **看板「提交作业」现在也会并进错题本**。T-035 ② 写的是「review 留档时……写入 weaknesses.md」，但以前只有命令行 `review` 会记，
   看板（主要入口）不记。现在两条路径共用 `cli._review_and_record`。
3. **插件首次引导**：宿主里还**没有任何**「学习领航员」工作区时，输入框上沿出现一行「学习面板只在「学习领航员」工作区启用。[把当前工作区设为「学习领航员」]」。
   没有它新用户找不到面板；一旦工作区存在，其它工作区里什么都不渲染。不想要：删 `WorkspaceOnboarding` 即可。
4. **插件默认项目根 = 「学习领航员」工作区的目录**（以前是从宿主进程 cwd 往上找 `README.md`）。手填路径仍优先。
5. **插件不再挂 `conversation.session.header.actions`**：宿主 0.2.0 起这个 slot 真的会渲染（会话标题栏），整块面板会出现两份。
6. **插件加了一个 devDependency `@types/node`**：`tsconfig.json` 一直声明 `types: ["node"]` 但依赖里没有，`pnpm typecheck` 以前直接报错。
   不是运行时依赖；锁文件只多了它和 `undici-types` 两条。
7. **`distill` 的 JSON 解析变宽松了**：四份「从 LLM 回复里取 JSON」合成一份 `llm.extract_json`（用 `raw_decode`）；
   以前 distill 遇到「JSON 后面还跟一句说明」会判失败，现在能解析（planner/syllabus/alignment 本来就这样）。
8. **conftest 隔离了 LLM 凭证**（非 `real` 用例）：清 `KIMI_API_KEY` 等环境变量；没显式传 `home` 时登录态指到空目录。
   原因见 §3.1——以前有用例会在你机器上**真的调 LLM**。
9. **两处用户可见的小口径变化**：`review --provider 未知名字` 现在和其它命令一样退出码 2 + 打印用法（以前是 1）；
   看板缺必填参数的报错不再叠一层「讲解 失败：」前缀（直接是「讲解需要一个知识点名称」）。

## 三、修掉的问题

### 3.1 基线就红的两条测试（环境相关，未改断言、只做隔离）

| 用例 | 原因 | 处理 |
| --- | --- | --- |
| `test_t039_contract::test_learning_contract_passes` | 契约脚本断言项目根 `endsWith('/study')`——克隆成别的目录名就挂 | 按真实路径比较；另加「从 `plugin/` 往上找不能停在插件目录」 |
| `test_t034::test_history_overflow_keeps_handoff_in_real_prompt` | 没打桩 LLM：有 Kimi 登录态的机器上**真的调 LLM**，没有的机器上走硬裁路径而失败 | 显式打桩摘要器；conftest 加全局隔离 |

### 3.2 代码里的真问题

| # | 位置 | 现象 | 根因 | 回归用例 |
| --- | --- | --- | --- | --- |
| 1 | `plugin/src/client/index.tsx` | 「讨论」按钮在任何宿主上都只会报「讨论失败：step is not defined」 | 调试残留：调用了 5 次未定义的 `step()`，catch 里又调一次 | `client.contract.mjs`（加载**构建产物**跑讨论流程）、`test_no_undefined_debug_tracer_left_in_bundle` |
| 2 | 同上 | 即使没有 #1，专用工作区路径也建不出会话 | `sessions.create({ workspaceId, cwd })` 两个一起传，宿主（0.1.5-rc.3 与 0.2.0-rc.1 源码）直接 `gateway/bad-request` | `v02_create_gets_workspace_only` 等 |
| 3 | 同上 | 宿主 0.2.0 上一个会话出现两份面板 | 同时注册了 `session.header.actions`，0.2.0 起该 slot 会渲染 | `only_dock_slot`、`test_client_only_mounts_input_dock` |
| 4 | `plugin/src/server/learning.ts` | 从插件目录往上探测项目根会停在 `plugin/` | 只认 `README.md`，而 `plugin/` 自己也有 | `resolve_root_skips_plugin_readme` |
| 5 | `plugin/` 工具链 | `pnpm typecheck` 跑不起来；`LearningPanel` 的类型错误一直没人发现 | 缺 `@types/node`；props 默认值 `= {}` 让 `createElement` 推断失败 | `pnpm typecheck` |
| 6 | `src/planner.py` | 复述过（「输出」态）的知识点在出题 prompt 里被列为「仍存疑」，还可能被选成「下一个新点」 | planner 自己的 `MASTERED_LEVELS = ("学过","做过")` 漏了 T-019 加的最高态；handoff/report 各写一份含「输出」的 | `test_output_points_are_mastered_in_task_prompt` 等 3 条 |
| 7 | `src/planner.py` | 出过第一道复习题后**再也不出复习题** | `count_new_tasks` 从新往旧遍历，遇到任何复习题就 `return 0`，从不数它之后的新题 | `test_review_is_due_again_in_the_second_cycle` |
| 8 | `src/planner.py` | ```json 围栏分支从未生效（只是靠后面的 raw_decode 兜住；围栏前的文字里有花括号就解析失败） | 普通字符串里写了 `"\\\\s"`，正则变成匹配字面量 `\s` | `test_parse_task_reads_fenced_json_after_prose_with_braces` |
| 9 | `src/weaknesses.py` | 错题本的「最近」日期每读一次丢一次，下次保存就从文件里消失；周报的「窗口内复现」因此不准 | 先按「首次」切掉行尾再找「最近」，而写出的格式是「首次：A，最近：B」 | `test_weaknesses_keep_both_dates_across_reload` 等 2 条 |
| 10 | `src/profile.py` | 看板手工改状态会把 `last_touched` 抹掉（复习队列被重置） | `set_level` 重建 `KnowledgePoint` 时漏了字段（T-035 修过 `mark_done` 的同一类问题） | `test_set_level_keeps_last_touched` |
| 11 | `src/cli.py` | `chat <时间戳>` 交互模式下 T-043 历史摘要从未生效，超长历史一律硬裁 | `_run_chat` 没有 `home` 参数，REPL 分支里的 `home` 是 NameError，被 `except Exception` 吞掉 | `test_repl_chat_builds_summarizer_with_home` |
| 12 | `src/cli.py` | 看板「提交作业」不进错题本（见 §二.2） | 看板与 CLI 各写一份点评流程，看板那份漏了 | `test_board_review_feeds_weaknesses` |
| 13 | `src/explain.py` | 用画像名 / 缩略名提问讲解时，缓存永远命不中（每次都调 LLM） | 读缓存用用户输入、写缓存用地图点名 | `test_explain_cache_hits_when_asked_by_another_name` |
| 14 | `src/dashboard.py` | 回答里的行内代码 `` `x` `` 从来没渲染成 `<code>` | 普通字符串里的 `"\1"` 是控制字符 `\x01`，不是反向引用 | `test_inline_code_is_rendered` |
| 15 | `src/dashboard.py` | 任务页每张卡片都有 `id="chat-panel"`，HTML 非法 | 固定 id | `test_chat_panels_do_not_share_an_id` |
| 16 | `src/dashboard.py` | 畸形 `Content-Length` 让处理线程抛异常断连接；超大请求体无上限地读进内存 | `int(...)` 未保护、没有上限 | `test_malformed_content_length_is_400`、`test_oversized_body_is_rejected_without_reading_it` |
| 17 | `src/dashboard.py` | 别的网站可以借浏览器触发看板动作 / DNS rebinding 读文件（见 §二.1） | 没有来源校验 | `test_t050_dashboard_quality.py` 前 12 条 |

### 3.3 独立复审发现、交付前已修

| 问题 | 处理 | 用例 |
| --- | --- | --- |
| 统一后的 `extract_json` 围栏正则没锚定行首：JSON 字符串里出现 ```` ``` ````（如「参考 ```python …```」）时会取出半截 JSON 或别的值（**我引入的回归**） | 围栏改为独占一行（行首 ``` … 行首 ```），合法 JSON 的字符串里不会有真换行 | `test_code_fence_inside_json_string_is_not_taken_as_the_fence`（4 种）、`test_syllabus_point_with_code_fence_survives` |
| 看板 `topics` 传了非列表（如数字）会变成 500 | 明确 400「topics 必须是主题名列表」 | `test_bad_topics_type_is_400_not_500` |
| 看板「提交作业」先建 LLM 客户端再查任务：时间戳写错时报的是 LLM 配置问题 | 先查任务 | `test_board_review_reports_unknown_task_before_llm_config` |
| `.env` 存成 GBK 时 `FEISHU_ROOT_DOC` 读成空（统一走严格解码后） | `.env` 解析容错解码（凭证读取也一并受益，以前直接抛 UnicodeDecodeError） | `test_env_file_in_gbk_still_yields_ascii_values` |
| 批量提炼按字节解码后 CRLF 原样送进 LLM（与单篇提炼不一致） | 统一成 `\n` | `test_batch_distill_sends_lf_text_like_single_note` |
| 插件 `taskFileId` 只认 ASCII 与 CJK，Python 的 `\w` 认全部 Unicode 字母数字 | 改用 `\p{L}\p{N}_`（`u` 标志） | 对照用例加了拉丁扩展、日韩文、全角/带圈数字 |
| HEAD 被拒时仍写了响应体；面板把纯文本 403 原因显示成笼统的「无法解析」 | HEAD 只回头部；短的纯文本原因直接显示 | `test_head_rejection_has_no_body`、`test_panel_js_shows_plain_text_reason` |

审查还确认了：新加的必需 `inject`（客户端 `uiWorkspace`、服务端 `workspaceRegistry`）在 0.1.5-rc.3 的 web 包里也存在
（`dsh-web-app@0.1.5-rc.3` 依赖 `dsh-client-ui-workspace` 与 `dsh-workspace`），所以 0.1.5 的兜底路径仍然可达。

## 四、插件：只在「学习领航员」工作区启用（任务书里的待做需求）

| 半边 | 做法 | 依据（宿主源码核对） |
| --- | --- | --- |
| 客户端注入 | 面板挂在会话作用域 slot `conversation.input.dock`，宿主传入 `sessionId`；订阅 `ctx.workspaces.list`，当前会话属于标题为「学习领航员」的工作区才渲染；每个请求带 `workspaceId` | `SessionStandardProps.sessionId`、`WorkspaceView.sessionIds`（0.1.5-rc.3 与 0.2.0-rc.1 一致） |
| 服务端路由 | `serveLearning` 先用 `ctx.workspaceRegistry.get(id)` 核验标题，不是「学习领航员」→ 403；拿不到注册表 → 503（失败即关闭）；**不信客户端自报的标题** | `WorkspaceRegistry.get/list`；服务端 `inject` 增加 `workspaceRegistry` |

同时适配了宿主 0.2.0-rc.1 的会话接缝（0.2 起 `ctx.sessions` 换成引用计数，`open/resolveAgentScope` 没了）：
0.2 走 `uiWorkspace.openSession` + `sessions.using(...).binding.session.prompt`，0.1.5 的链保留兜底；两套形状都有契约用例。

**真机（DSH 0.2.0-rc.1，独立 `DSH_HOME`，项目用副本）**：无该工作区时只出引导行 → 点引导，工作区改名、面板就地出现（订阅生效）；
面板读出 4 条任务 / 7 本书；`/api/learning` 对缺工作区 / 未知工作区 / 伪造标题一律 403；
「讨论」在该工作区建出原生会话，标题「时间戳 + 目标前 20 字」，**自动切过去**（README 以前记的已知限制随之消失），handoff 全文作为首条消息进入会话
（因为独立 home 没配模型 Key，会话随后报「no API key」——预期内，与插件无关）。

## 五、逐文件变更

### 后端 `src/`

| 文件 | 改了什么 | 为什么 |
| --- | --- | --- |
| `fileio.py`（新） | `write_text_atomic`（tmp + replace，失败清 tmp、原样抛 OSError）、`read_text_or_none` | 「先落临时文件再替换」原来在 11 个模块里手写了 13 遍；各模块仍抛自己的领域异常 |
| `llm.py` | 新增 `extract_json` / `JSONExtractionError`；Kimi 三条配置路径合成一个内部函数；删掉 `resolve_provider` 里读了也白读的登录态 | 四份 JSON 提取收敛（顺带修 #8）；重复构造 `ProviderConfig` |
| `profile.py` | `MASTERED_LEVELS` 唯一口径（含「输出」）；`PointNotFoundError` 取代 `"没有知识点" in str(exc)` 字符串匹配；`dataclasses.replace` 更新知识点；`resolve_point_name`；落盘走 `fileio` | 修 #6、#10；字符串匹配异常消息很脆 |
| `planner.py` | 用共享口径与 `extract_json`；删除未被引用的 `_legacy_next_unmet_point_for_books`（75 行）；`_topic_of` / `_book_points` 收敛重复表达式；选书的命中数只算一次；`count_new_tasks` 只读一次文件；`pick_review_point` 每点只算一次天数；`_field` 合并 `_field_in_block`；`append_review` / `delete_task_record` 共用 `_locate_task_block` / `_write_task_file`；读文件走 `read_text_or_none`；硬编码 8000 → `MAX_CODE_CHARS` | 修 #6、#7、#8；死代码与重复 |
| `cli.py` | `_parse_args` / `_UsageError` / `_check_provider` / `_profile_target` / `_completer_or_report` 取代 11 份手写参数循环；`main` 改为分派表；`_run_chat` 补 `home`；`_review_and_record` 供 CLI 与看板共用；`_forget_weaknesses`；`op_done` 删掉与 `_run_done` 重复的错题本移除；`_read_env_value` 复用 `.env` 解析；`capture` 用 `contextlib.redirect_*`；`op_explain` 兼容 `str` 路径；USAGE 去掉重复行、补全选项；docstring 更新 | 修 #11、#12；重复代码；缺参文案统一来自 `_OPTION_HINTS`（同一个选项在不同命令里说法不一的问题没了） |
| `distill.py` | 用 `extract_json` / `fileio`；批量提炼每篇只读一次（以前判空、算指纹、读正文各读一遍）；进度回调收敛 | 性能、重复 |
| `sync.py` | `_payload_key` 收敛两处同样的推导；BFS 队列用 `deque`；正则折叠空行；落盘走 `fileio` | `list.pop(0)` 是 O(n)；重复 |
| `feishu.py` | `_paginate` 合并「列子节点」与「取文档块」两份分页循环 | 重复；报错口径一致 |
| `alignment.py` / `syllabus.py` | 用 `extract_json` / `fileio`；`TYPE_CHECKING` 导入；删掉未使用的 `_FENCE_RE`、`_CHAPTER_RE`、`FRONTMATTER_PATTERN`；正则预编译 | 重复与死代码 |
| `explain.py` | 缓存按地图点名存取；每个蒸馏稿只读一次（书名、source 前缀、章节正文共用一份文本）；`TRUNCATED_NOTE` 由常量生成；去掉未用导入 | 修 #13；性能 |
| `handoff.py` | 用共享 `MASTERED_LEVELS`、`fileio` | 口径统一 |
| `chat.py` / `chat_session.py` | `MAX_PROMPT_CHARS` 与 prompt 头尾只定义在 `chat.py`；留档写入两份重复实现合并为 `_compose_archive` + `_write_archive`；`chr(10)` 拼接改成正常字符串；删掉写了从不读的 memo | 注释写着「同一个上限避免口径漂移」，实际却定义了两份 |
| `weaknesses.py` | 时间戳段整段解析；清空清单也走同一条原子写 | 修 #9 |
| `review.py` | 硬编码 8000 → 常量；LLM 异常带原因、未知异常只报类型名 | 与其它模块同一错误口径（不把请求体/Key 带出来） |
| `report.py` | 用共享口径；拼接改 f-string（**输出逐字节不变**，用合成数据前后对比过） | 可读性 |
| `assignments.py` | 重排版（原文件定义之间没有空行）、正则改 raw string、挑题时画像集合只算一次 | 可读性、性能 |

### 看板 `src/dashboard.py`

| 改了什么 | 为什么 |
| --- | --- |
| `request_guard` + 处理器接入；请求体上限 1 MiB、畸形 `Content-Length` 回 400 | 修 #16、#17 |
| `PANEL_JS`：四处 `fetch` 收敛为 `postAction`，非 JSON 回包给出带状态码的中文原因（以前一律「网络错误」）；删掉注释里的 `',` 残渣；讲解失败不再叠两层前缀 | 重复与错误处理一致性 |
| 聊天 JSON 回包增加 `html`（同一个 markdown 渲染器、先转义再渲染），面板就地显示富文本；用户输入仍只走 `textContent` | 以前就地回答是纯文本、刷新后才变富文本 |
| `_run_operation` 改为参数表 `REQUIRED_PARAMS` 驱动；缺参报错不再被包成「讲解 失败：讲解需要…」 | 去掉长 if 链 |
| 只保留最近一条动作结果；复习角标用 `planner.is_review_record`；去掉重复 id；`_inline` 正则修复；docstring 改成交互版的真实边界 | 修 #14、#15；以前结果列表只增不减 |

### 插件 `plugin/`

| 文件 | 改了什么 |
| --- | --- |
| `src/shared.ts`（新） | 两半共用：`WORKSPACE_TITLE`、数据形状、`errorText` |
| `src/server/learning.ts` | `checkWorkspace` / `serveLearning`（工作区过滤 + 默认项目根）；只读动作表驱动；`runCli` 只结算一次；`taskFileId` 与 Python `task_file_id` 同规则（pytest 逐条对照）；项目根探测认 `profile/` + `src/cli.py` |
| `src/index.ts` | 服务端 `inject` 增加 `workspaceRegistry` |
| `src/client/index.tsx` | `LearningSlot` 工作区过滤 + 首次引导；`openNativeDiscussion` 两代宿主接缝、修 #1 #2；只挂 dock（#3）；三份数据并发读取；`call` 处理非 JSON；`React.createElement` 简写与小组件拆分 |
| `tests/client.contract.mjs`（新）、`tests/learning.contract.mjs` | 客户端契约（加载构建产物）；服务端补工作区过滤 11 项 |
| `package.json` / `tsconfig.json` | `test` 脚本、`@types/node`；`allowImportingTsExtensions` |
| `lib/` | 重新构建（宿主只认入库产物） |
| `README.md` | 工作区过滤、两代接缝、0.2.0-rc.1 兼容矩阵、已知坑 |

### 测试与文档

| 文件 | 说明 |
| --- | --- |
| `tests/conftest.py` | LLM 凭证隔离（§二.8） |
| `tests/test_t034_chat_panel.py` | 溢出用例显式打桩摘要器（断言未改） |
| `tests/test_t050_quality_fixes.py` / `test_t050_dashboard_quality.py` / `test_t050_plugin_workspace.py`（新） | 本次所有修复与收敛的回归用例 |
| `README.md`、`项目文档/04`、`项目文档/07` | 看板来源校验、插件工作区过滤、测试数、T-050 记录 |

**没有删任何测试**；既有断言一条没放宽。

## 六、红线核对

| 红线 | 结论 |
| --- | --- |
| 架构边界与模块分工 | 不变。新增的 `src/fileio.py` 是与 `silent.py` 同类的基础设施（不承担业务）；插件仍只做界面与宿主集成、动作仍经 `python -m src.cli` |
| 不加运行时依赖 | 后端仍是标准库 + requests；插件运行时依赖不变（只加了 devDependency `@types/node`，见 §二.6） |
| 不改数据文件 | `notes/`、`profile/` 零改动（`git diff 0a050be -- notes profile` 为空）；所有手工验证都在副本上做 |
| 安全边界 | 固定动作集、入参白名单、`/file` 白名单、无自由命令入口全部保留；看板**多了**来源校验；插件服务端**多了**工作区过滤 |
| 不替用户写答案代码 | 未涉及 |

## 七、发现了但没动（超出「代码质量」范围，供排期）

- T-035 写的是「last_touched 在 distill / done / review 时刷新」，目前只有 done 会刷新；distill 新增的点与 review 都不刷。
- `llm.RequestsTransport` 名字叫 Requests，实际用的是 `urllib`（`feishu` 那个才是 requests）——改名会动接口，没动。
- `dashboard.build_pages`（没接看板时的纯只读模式）仍保留，只有测试在用。
- 插件服务端的 `readProfile` / `readTasks` 用正则再解析一遍 Python 写的 markdown——架构上就是「插件读文件」，但两边格式要一起改。
- DSH 0.2.0 的 web 首次启动会弹「添加 API Key」对话框，独立 `DSH_HOME` 下必然出现，与插件无关。

## 八、怎么验证

```bash
python -m pytest -q
cd plugin && pnpm install && pnpm build && pnpm typecheck && pnpm test
```

回归用例在原代码上会失败（证明它们确实盯住了问题）：把 `tests/test_t050_quality_fixes.py` 拷到 `0a050be` 的工作区跑即可
（文件开头的 `MASTERED_LEVELS` 导入需要换成本地定义，因为原代码没有这个常量）。
