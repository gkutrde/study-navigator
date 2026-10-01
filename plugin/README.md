# dsh-learning-navigator（学习领航员 DSH 插件）

把「学习领航员」的本地 Python 核心搬进 DeepSeek Harness 界面。

## 架构边界（F-16 决策）

方向是**我们写进 DSH**：

| 半边 | 职责 |
| --- | --- |
| 插件（本目录，TypeScript） | **只做界面与宿主集成** |
| Python 核心（仓库上层 src/、profile/） | **数据与逻辑后端**——画像、任务、知识地图、出题、点评 |

插件不重新实现业务逻辑：它读 `profile/` 下的文件，需要动作时经 `python -m src.cli` 子进程执行。

## 面板怎么工作（T-039）

```
浏览器（面板）  --POST /api/learning-->  插件服务端  --读文件-->  profile/*.md
                                              \--白名单-->  python -m src.cli <sub>
```

- 通道是宿主的**精确 Fetch 路由**（`ctx.connection.fetch.register`），挂在 `/api` 的认证栅栏之后，
  浏览器同源 POST 即可——**不需要伪造 cookie、不需要绕过鉴权**。
- 动作走**白名单**：`profile / tasks / syllabus`（只读）、`sync / next / done`（跑 CLI）。
  客户端只能报这些名字，服务端不接受任何命令字符串。
- 跑 CLI 用 `spawn` + 参数数组 + `shell: false`：用户输入永远只作为数组元素，
  分号/反引号/管道都只是普通字符。
- 失败在面板内**原地显示中文错误**（CLI 非零退出会带上 stderr 摘要）。

### 任务讨论（T-040）

任务列表每一项后面有「讨论」按钮：

1. **主路径——原生会话**：插件在**宿主进程内**调 `ctx.sessions`（create → open → prompt），
   把这道题的 handoff 上下文整段预填进去，你在**原生会话**里继续追问（思考流、文件引用、格式都是原生的）。
   因为插件就在宿主进程里，**不受 T-031 那套 CORS/cookie 限制**。
2. **降级路径**：拿不到会话接缝（或创建失败）→ 面板内显示明确提示，
   改调 `python -m src.cli chat <时间戳> "<上下文>"` 并把回答渲染在面板里。

**绝不绕过鉴权**：两条路径都不伪造 cookie/令牌、不去 hack 桌面令牌；拿不到接缝就降级。

#### 实测要点（0.1.5-rc.3）

- `ctx.sessions.create({ cwd })` 会**真的建一个原生会话**；`prompt()` 的文本会落成
  `agent/inbox/spliced` 事件——可以在 `~/.dsh/sessions/<工作区>/session-*/session.v*.jsonl.zstd` 里核对。
- `open()` **异步生效**，立刻 `prompt()` 会返回看似成功但消息没进日志。
  代码里轮询等输入面就绪 + 失败重试 3 次。
- **已知限制**：讨论会话建好后，Web 界面**不会自动切过去**（主区仍是「选择一个工作区开始」），
  需要用户点一下侧栏那条新会话（标题就是首条消息的开头）。会话与预填内容都已就绪，只是没被自动聚焦。


### 讨论会话归属：专用工作区（T-046）

客户反馈：讨论会话混在**默认工作区**里。修法：讨论前先准备好专用工作区，再把会话建进去。

```
ctx.workspaces.create({ path: <项目目录> })   → 拿到 workspaceId（幂等：同目录只会有一个）
ctx.workspaces.rename(workspaceId, '学习领航员')  → 只在标题不对、且没人占用时改
ctx.sessions.create({ workspaceId, cwd })     → 会话建在专用工作区里
face.rename('<任务时间戳> <目标前 20 字>')      → 会话标题
```

#### ⚠️ 宿主限制（实测 0.1.5-rc.3，如实记录）

| 限制 | 说明 |
| --- | --- |
| `ctx.workspaces.create` **只接受目录路径** | 参数只有 `{ path }`，**不能直接指定标题**；工作区标题由目录派生 |
| `rename` 是**全局**的 | 没有 per-caller 作用域——改名会影响所有看到这个工作区的人 |
| 一个目录只有一个工作区 | `create` 幂等：同一路径反复调用只会解析到同一个工作区 |

**所以「名为『学习领航员』的独立工作区」需要它自己的目录。**
没有独立目录时，本插件的**降级方案**是：

1. 复用/登记**项目目录**那个工作区；
2. 标题不是「学习领航员」、且**没有别的**工作区占用该标题时，把它改名为「学习领航员」；
   - 已有同名工作区 → **不抢名字**（宿主要报 `workspace/name-conflict`），只保证会话归属正确；
3. 改名失败**不影响归属**：会话仍然建在这个工作区里；
4. 拿不到 `workspaces` 接缝 → 直接在面板里说明「讨论会话会落在默认工作区」，**不绕过鉴权**。

> 想真正做到「一工作区、一任务一对话」且不影响别处：给这个项目**单独一个目录**当工作区，
> 或者用宿主界面手动建一个独立工作区再指过去。

#### 会话标题

`任务时间戳 + 任务目标前 20 字`（超 20 字加省略号，例如 `2026-09-27 10:00 做一个 \`card.html\`，展示一张…`）。
### 面板按钮

| 按钮 | 动作 | 跑什么 |
| --- | --- | --- |
| 同步并提炼 | `sync` | `python -m src.cli sync <文档ID或wiki链接>` |
| 出题 | `next` | `python -m src.cli next` |
| 回写 | `done` | `python -m src.cli done <知识点> <产出路径>` |
| 讨论（每项任务） | `discuss` | 原生会话（`ctx.sessions`）；降级才调 `chat` |

### 项目路径

面板里可填；留空则**自动探测**（从进程 cwd 往上找含 `README.md` 的目录）。
Python 解释器可用环境变量 `LEARNING_PYTHON` 或插件配置 `python` 覆盖。

## 安装（本地开发）

```bash
cd plugin
pnpm install
pnpm build            # 产出 lib/client.js（已入库，git 安装不需要构建）

# 装进 web profile
dsh plugin --profile web add <本目录绝对路径>
```

装完重启 `dsh --profile web`，界面上应出现「学习」面板。

## 接缝清单（本插件实际用到的）

只使用**公开** `ctx` 接缝。下面每条都标注了用途与首次测得的宿主版本。

| 接缝 | 侧 | 用途 | 首次验证版本 |
| --- | --- | --- | --- |
| `ctx.slots.inject(slot, cb)` | 客户端 | 声明「我要往这个 slot 里塞东西」 | 0.1.5-rc.3 |
| `ctx.slots.register({ name, id, order }, Component)` | 客户端 | 注册面板组件 | 0.1.5-rc.3 |
| `ctx.slots.registerFactory()` / `renderFactorySlot()` | 客户端 | 需要独立渲染 occurrence 时才用（**本插件暂未用**） | 0.1.5-rc.3 |
| `window.__ModuleLoader__.load({ id, factory })` | 客户端 | 宿主 shell 加载客户端 bundle 的握手协议 | 0.1.5-rc.3 |
| `ctx.connection.fetch.register({ path, methods, requestBody, fetch })` | 服务端 | **精确 Fetch 路由**：面板的 `/api/learning` 通道（T-039） | 0.1.5-rc.3 |
| `ctx.sessions.create({ cwd })` | 客户端 | 开一个**原生会话**（T-040 讨论主路径） | 0.1.5-rc.3 |
| `ctx.sessions.open(id)` | 客户端 | 把它切到当前会话 | 0.1.5-rc.3 |
| `ctx.sessions.get(id).prompt([{ type: 'text', text }], 'queue')` | 客户端 | 把 handoff 上下文**预填**进原生会话 | 0.1.5-rc.3 |
| `package.json` → `dsh.bundle.patch` | 服务端 | 告诉宿主挂哪个 patch 文件 | 0.1.5-rc.3 |
| `package.json` → `dsh.client` | 客户端 | 声明客户端半边（`platform: web`） | 0.1.5-rc.3 |
| `package.json` → `exports["./client"]` | 客户端 | 宿主按这个路径取 bundle | 0.1.5-rc.3 |
| `export const name` / `inject` / `apply(ctx, rowConfig)` | 服务端 | 插件模块约定 | 0.1.5-rc.3 |
| `ctx.effect(fn)` | 服务端 | 注册可回收副作用（T-039 起会用） | 0.1.5-rc.3 |
| `ctx.inject(services, cb)` | 服务端 | 等某个服务就绪再接线（T-039 起会用） | 0.1.5-rc.3 |
| `ctx.systemPrompt.section({...})` | 服务端 | 往系统提示词插一段（**本插件暂未用**） | 0.1.5-rc.3 |

### 本插件挂载的 slot

| slot 名 | 位置 |
| --- | --- |
| `conversation.input.dock` | **实测有效**：输入框上沿——「学习」面板挂在这里（真机截图见仓库 项目文档/assets/DSH插件-学习面板.png） |
| `conversation.session.header.actions` | 名字在宿主 slot 清单里存在，但**首页会话上没有渲染出来**（已一并注册，作为升级后的备选） |

### 宿主里确实存在的 slot（备查，未全部使用）

从宿主 `app.asar` 里抽出来的真实 slot 名，按前缀分组。升级后如果某个名字消失，
说明接缝变动，需要按兼容矩阵逐项核对。

- `conversation.`：`chat.assistant-actions`、`composer.bar`、`composer.dock`、`header.leading`、
  `hero.brand.mark`、`hero.workspace`、`input.activity`、`input.dock`、`input.left`、`input.right`、
  `input.overlay`、`session.header`、`session.header.actions`、`session.header.corner`、
  `session.header.lineage`、`session.header.utilities`、`approval.detail`
- `sidebar.`：`footer.action`、`left.toggle`、`right.pane.tab`、`right.tab.document`、
  `right.tab.guide`、`right.toggle`、`session.row.leading`、`toggle.badge`、`workspaces.session.menu.item`
- `settings.`：`enter.title`、`general.item`、`links.sidebar`、`links.title`、`models.footer`

> 这些名字的权威来源是宿主 web 包里的 slot 定义。**升级后请重新抽取核对**，
> 不要凭记忆写 slot 名——写错了不会报错，只是静静不出现。

## 版本兼容矩阵

| 宿主版本 | 实测日期 | 结果 | 备注 |
| --- | --- | --- | --- |
| 0.1.5-rc.3 | 2026-09-29 | ✅ 骨架 + 面板 v1 可用 | node v24.19.0 / pnpm 11.25.0 / tsdown 0.15.12；浏览器实测「学习」面板可在输入框上沿展开，读出 170 个知识点 / 3 条任务 / 7 本书；点「出题」8 秒内真出一题并刷新面板 |

### 构建环境要求

| 项 | 要求 |
| --- | --- |
| Node | >= 22（实测 v24.19.0） |
| pnpm | 11.x（实测 11.25.0） |
| tsdown | 0.15.x |

### 已知的交互坑

- **点不动的 `span`**：面板折叠/展开最初写成 `<span onClick>`，在这个宿主里**点不动**
  （没有原生点击语义）。改用真正的 `<button>` 后正常，顺带键盘可达。

### 已知的构建坑

- **React 必须标成 external**：tsdown 0.15 里只在 `deps.neverBundle` 写 `react` **不生效**，
  实测会被内联进产物（46 KB），界面上等于塞了第二份 React。必须同时给顶层 `external: ["react", ...]`，
  产物会回到 2.4 KB 并变成 `require("react")`。
- **产物要入库**：宿主按 `exports["./client"]` 直接取文件，git 安装不会帮你构建。
- **服务端半边也要构建**：宿主按 `main` 加载 `lib/index.js`。只构建客户端时 profile 直接起不来：
  `Cannot find module .../dsh-learning-navigator/lib/index.js`。本项目用 tsdown 的**数组配置**同时产出两侧。
- **客户端 `inject` 必须含 `slots`**：少了它，宿主报
  `cannot get property "slots" without inject`，界面顶部显示红色的 `Failed to load plugins`，面板不出现。
  注意**服务端**那半边的 `inject` 保持空数组是对的（骨架阶段不注入服务）。

## 每次 dsh 升级后的冒烟（三步）

1. **hello world 面板**：重启 `dsh --profile web`，界面上出现「学习」面板；
2. **一次出题**：调一次本地 CLI（T-039 起由面板按钮触发），确认子进程链路通；
3. **一次讨论**：开一次原生会话/降级链路（T-040），确认上下文预填成功。

三步任一失败 → 按上面的**接缝清单**逐项核对，把结论补进**版本兼容矩阵**。

## 适配铁律（长期有效）

- **只用公开 `ctx` 接缝**：不 import 宿主内部模块、不碰 `process.binding` 之类私有入口；
- **绝不绕过鉴权**：拿不到会话接缝就降级，不去伪造 cookie 或桌面令牌；
- **接缝变动按矩阵核对**：升级后先跑冒烟，再逐项填表，不要凭印象判断「应该没变」。

## 目录结构

```
plugin/
├── package.json           # dsh.bundle.patch + dsh.client 清单、exports
├── tsdown.config.ts       # 客户端构建（ModuleLoader 包装）
├── cordis.patch.yml       # 服务端挂载点
├── src/
│   ├── index.ts           # 服务端入口（骨架阶段：仅证明可加载）
│   └── client/index.tsx   # 界面入口：注入「学习」面板
└── lib/client.js          # 构建产物（已入库）
```

## 路线图

| 任务 | 内容 |
| --- | --- |
| T-038（本卡） | 插件骨架：装得上、界面出「学习」面板、接缝与兼容矩阵成文 |
| T-039 ✅ | 学习面板 v1：画像/任务/地图 + 按钮经 `python -m src.cli` 子进程执行；项目路径可配（浏览器真机验收见 项目文档/assets/DSH插件-学习面板v1.png） |
| T-040 ✅ | 任务讨论原生会话：用 `ctx.sessions` 预填 handoff；无接缝则降级到 headless + 面板自渲染 |