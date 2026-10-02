# dsh-learning-navigator（学习领航员 DSH 插件）

把「学习领航员」的本地 Python 核心搬进 DeepSeek Harness 界面。

## 架构边界（F-16 决策）

方向是**我们写进 DSH**：

| 半边 | 职责 |
| --- | --- |
| 插件（本目录，TypeScript） | **只做界面与宿主集成** |
| Python 核心（仓库上层 src/、profile/） | **数据与逻辑后端**——画像、任务、知识地图、出题、点评 |

插件不重新实现业务逻辑：它读 `profile/` 下的文件，需要动作时经 `python -m src.cli` 子进程执行。

## 只在「学习领航员」工作区启用（T-050）

插件**只在「学习领航员」工作区启用**，客户端与服务端两道过滤：

| 半边 | 怎么过滤 | 依据 |
| --- | --- | --- |
| 客户端（注入） | 面板挂在会话作用域的 slot 上，宿主把当前会话的 `sessionId` 传进来；订阅 `ctx.workspaces.list`，**当前会话属于标题为「学习领航员」的工作区**才渲染面板，否则什么都不渲染 | 宿主快照里每个工作区的 `sessionIds`（宿主按会话目录核过，不靠路径字符串比对） |
| 服务端（路由） | 每个请求带上工作区 id；`/api/learning` 到宿主的 `ctx.workspaceRegistry.get(id)` 核验标题，不是「学习领航员」一律 **403**（中文原因）；拿不到注册表接缝 → **503**（失败即关闭） | 宿主工作区注册表——**不信客户端自报的标题** |

- **默认项目根 = 工作区目录**：面板里「项目路径」留空时，服务端用「学习领航员」工作区的目录当项目根
  （T-046 正是把项目目录登记成了这个工作区）；手填的路径仍然优先。
- **首次使用的引导**：宿主里**还没有任何**「学习领航员」工作区时，输入框上沿会出现一行
  「学习面板只在「学习领航员」工作区启用。[把当前工作区设为「学习领航员」]」——点一下就把当前工作区
  登记并改名（规则同 T-046：只在标题不对、且没有别的工作区占用该标题时才改）。一旦有了这个工作区，
  其它工作区里就什么都不渲染。不想要这个引导：删掉 `src/client/index.tsx` 里的 `WorkspaceOnboarding` 即可。
- 想手工建：DSH 侧栏「添加工作区」选项目目录，再把它重命名为「学习领航员」。

## 面板怎么工作（T-039）

```
浏览器（面板）  --POST /api/learning-->  插件服务端  --核验工作区-->  ctx.workspaceRegistry
     (带 workspaceId)                          \--读文件-->  profile/*.md
                                               \--白名单-->  python -m src.cli <sub>
```

- 通道是宿主的**精确 Fetch 路由**（`ctx.connection.fetch.register`），挂在 `/api` 的认证栅栏之后
  （宿主先做 Host/Origin 校验与浏览器鉴权），浏览器同源 POST 即可——**不需要伪造 cookie、不需要绕过鉴权**。
- 动作走**白名单**：`profile / tasks / syllabus`（只读）、`sync / next / done`（跑 CLI）。
  客户端只能报这些名字，服务端不接受任何命令字符串。
- 跑 CLI 用 `spawn` + 参数数组 + `shell: false`：用户输入永远只作为数组元素，
  分号/反引号/管道都只是普通字符。
- 失败在面板内**原地显示中文错误**（CLI 非零退出会带上 stderr 摘要；接口回包不是 JSON 也会给出带状态码的原因）。
- 展开面板时画像 / 任务 / 地图三份数据**并发**读取。

### 任务讨论（T-040）

任务列表每一项后面有「讨论」按钮：

1. **主路径——原生会话**：插件在**宿主进程内**用 `ctx.sessions` 建一个原生会话（建在当前「学习领航员」工作区里），
   切过去，把这道题的 handoff 上下文整段预填进去，你在**原生会话**里继续追问（思考流、文件引用、格式都是原生的）。
   因为插件就在宿主进程里，**不受 T-031 那套 CORS/cookie 限制**。
2. **降级路径**：拿不到会话接缝（或创建失败）→ 面板内显示明确提示，
   改调 `python -m src.cli chat <时间戳> "<上下文>"` 并把回答渲染在面板里。

**绝不绕过鉴权**：两条路径都不伪造 cookie/令牌、不去 hack 桌面令牌；拿不到接缝就降级。

两代宿主的会话接缝不一样，插件两条都走（按源码核对）：

| 宿主 | 建会话 | 切过去 | 预填 |
| --- | --- | --- | --- |
| 0.2.0-rc.1 | `ctx.sessions.create({ workspaceId })` | `ctx.uiWorkspace.openSession(id)` | `ctx.sessions.using(id, { source }, ref => ref.binding.session.prompt(...))` |
| 0.1.5-rc.3 | 同上 | `ctx.sessions.open(id)` | 轮询 `resolveAgentScope(id)` → `sessionOf(agentCtx)` 拿输入面后 `prompt(...)` |

#### 实测要点

- `ctx.sessions.create` **只接受 `workspaceId` 或 `cwd` 之一**——两个都给，宿主直接回 `gateway/bad-request`
  （0.1.5-rc.3 与 0.2.0-rc.1 的 `session-controller/commands` 源码都是这条规则）。
  T-046 的代码两个一起传，专用工作区路径因此**从来没建成过会话**；现在有工作区就只给 `workspaceId`。
- 0.1.5：`open()` **异步生效**，立刻 `prompt()` 会返回看似成功但消息没进日志——那条路径保留轮询等输入面就绪 + 重试。
- 0.2.0：会话按引用计数持有（`retain` / `using`），用完即还；引用来源标签是 `learningNavigator`。
- `prompt()` 的文本会落成 `agent/inbox/spliced` 事件——可以在 `$DSH_HOME/sessions/...` 的会话日志里核对。
- 以前「会话建好后 Web 界面不会自动切过去」的已知限制：0.2.0 起用 `uiWorkspace.openSession` 切过去，实测会自动打开。

### 讨论会话归属：专用工作区（T-046）

客户反馈：讨论会话混在**默认工作区**里。T-050 起面板本身就只在「学习领航员」工作区出现，
讨论会话直接建在**当前这个工作区**里（`ctx.sessions.create({ workspaceId })`）。

工作区的登记/改名（首次引导用）：

```
ctx.workspaces.create({ path: <目录> })   → 拿到 workspaceId（幂等：同目录只会有一个）
ctx.workspaces.rename(workspaceId, '学习领航员')  → 只在标题不对、且没人占用时改
```

#### ⚠️ 宿主限制（实测 0.1.5-rc.3，0.2.0-rc.1 源码核对未变，如实记录）

| 限制 | 说明 |
| --- | --- |
| `ctx.workspaces.create` **只接受目录路径** | 参数只有 `{ path }`，**不能直接指定标题**；工作区标题由目录派生 |
| `rename` 是**全局**的 | 没有 per-caller 作用域——改名会影响所有看到这个工作区的人 |
| 一个目录只有一个工作区 | `create` 幂等：同一路径反复调用只会解析到同一个工作区 |

**所以「名为『学习领航员』的独立工作区」需要它自己的目录。**
降级方案（也是首次引导的做法）：

1. 复用/登记**当前工作区的目录**；
2. 标题不是「学习领航员」、且**没有别的**工作区占用该标题时，把它改名为「学习领航员」；
   - 已有同名工作区 → **不抢名字**（宿主要报 `workspace/name-conflict`），在引导行里说明；
3. 拿不到 `workspaces` 接缝 → 引导行里说明「当前宿主没有工作区接缝」，**不绕过鉴权**。

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

面板里可填；留空则用**「学习领航员」工作区的目录**（T-050；以前是从插件进程 cwd 往上找含 `README.md` 的目录——
`plugin/` 自己也有 `README.md`，会停在插件目录）。自动探测现在认 `profile/` + `src/cli.py`。
Python 解释器可用环境变量 `LEARNING_PYTHON` 或插件配置 `python` 覆盖。

## 安装（本地开发）

```bash
cd plugin
pnpm install
pnpm build            # 产出 lib/index.js + lib/client.js（已入库，git 安装不需要构建）
pnpm typecheck        # tsc --noEmit
pnpm test             # 两条契约测试：服务端源码 + 客户端构建产物

# 装进 web profile
dsh plugin --profile web add <本目录绝对路径>
```

装完重启 `dsh --profile web`，在「学习领航员」工作区的会话里，输入框上沿应出现「学习」面板。

> 仓库若放在 exFAT 盘上（不支持符号链接），pnpm 默认的链接方式会失败：
> 设环境变量 `npm_config_node_linker=hoisted` 再跑上面的命令（只影响本机，不用改仓库配置）。

## 接缝清单（本插件实际用到的）

只使用**公开** `ctx` 接缝。下面每条都标注了用途与首次测得的宿主版本。

| 接缝 | 侧 | 用途 | 首次验证版本 |
| --- | --- | --- | --- |
| `ctx.slots.inject(slot, cb)` | 客户端 | 声明「我要往这个 slot 里塞东西」 | 0.1.5-rc.3 |
| `ctx.slots.register({ name, id, order }, Component)` | 客户端 | 注册面板组件（会话作用域 slot 的组件会收到 `sessionId` prop） | 0.1.5-rc.3 |
| `ctx.slots.registerFactory()` / `renderFactorySlot()` | 客户端 | 需要独立渲染 occurrence 时才用（**本插件暂未用**） | 0.1.5-rc.3 |
| `window.__ModuleLoader__.load({ id, factory })` | 客户端 | 宿主 shell 加载客户端 bundle 的握手协议 | 0.1.5-rc.3 |
| `ctx.workspaces.list.getSnapshot()` / `.subscribe()` | 客户端 | **工作区过滤**：当前会话属于哪个工作区（T-050） | 0.2.0-rc.1 |
| `ctx.workspaces.create({ path })` / `.rename(id, title)` | 客户端 | 首次引导：登记并改名专用工作区（T-046） | 0.1.5-rc.3 |
| `ctx.sessions.create({ workspaceId } \| { cwd })` | 客户端 | 开一个**原生会话**（T-040；两个参数只能给一个） | 0.1.5-rc.3 |
| `ctx.sessions.using(id, { source }, op)` | 客户端 | 0.2.0 起持有会话引用、拿 `binding.session` 输入面 | 0.2.0-rc.1 |
| `ctx.uiWorkspace.openSession(id)` | 客户端 | 0.2.0 起把新会话切成当前会话 | 0.2.0-rc.1 |
| `ctx.sessions.open(id)` + `resolveAgentScope(id)` → `sessionOf(agentCtx)` | 客户端 | 0.1.5 的切换与取输入面（兜底保留） | 0.1.5-rc.3 |
| `face.rename(title)` / `face.prompt([{ type: 'text', text }], 'queue')` | 客户端 | 会话标题 + 把 handoff 上下文**预填**进原生会话 | 0.1.5-rc.3 |
| `ctx.connection.fetch.register({ path, methods, requestBody, fetch })` | 服务端 | **精确 Fetch 路由**：面板的 `/api/learning` 通道（T-039） | 0.1.5-rc.3 |
| `ctx.workspaceRegistry.get(id)` | 服务端 | **工作区过滤**：核验请求来自「学习领航员」工作区（T-050） | 0.2.0-rc.1 |
| `package.json` → `dsh.bundle.patch` | 服务端 | 告诉宿主挂哪个 patch 文件 | 0.1.5-rc.3 |
| `package.json` → `dsh.client` | 客户端 | 声明客户端半边（`platform: web`） | 0.1.5-rc.3 |
| `package.json` → `exports["./client"]` | 客户端 | 宿主按这个路径取 bundle | 0.1.5-rc.3 |
| `export const name` / `inject` / `apply(ctx, rowConfig)` | 服务端 | 插件模块约定（服务端 inject：`connection`、`workspaceRegistry`） | 0.1.5-rc.3 |
| `ctx.effect(fn)` | 服务端 | 注册可回收副作用（**本插件暂未用**） | 0.1.5-rc.3 |
| `ctx.systemPrompt.section({...})` | 服务端 | 往系统提示词插一段（**本插件暂未用**） | 0.1.5-rc.3 |

客户端 `inject`：`['slots', 'sessions', 'workspaces', 'uiWorkspace']`（少声明一个，访问时宿主会拒绝）。

### 本插件挂载的 slot

| slot 名 | 位置 |
| --- | --- |
| `conversation.input.dock` | **实测有效**：输入框上沿——「学习」面板挂在这里（会话作用域，组件拿得到 `sessionId`；真机截图见仓库 项目文档/assets/DSH插件-学习面板.png） |

> 以前还注册了 `conversation.session.header.actions` 当「升级备选」。宿主 0.2.0 起这个 slot **真的会渲染**
> （会话标题栏右侧，放模型预设、后台任务这类紧凑按钮），整块面板会被塞进标题栏，一个会话里出现两份面板——已不再注册。

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
| 0.2.0-rc.1 | 2026-10-02 | ✅ 工作区过滤 + 讨论原生会话可用 | 本机源码构建（apps/cli/lib/bin.js，4878cda），独立 `DSH_HOME` + `dsh plugin --profile web add` 安装；node v22.20.0 / pnpm 11.21.0。实测：无「学习领航员」工作区时只出引导行 → 点引导后工作区改名、面板就地出现；面板读出 4 条任务 / 7 本书；服务端对缺工作区 / 未知工作区 / 伪造标题一律 403；「讨论」在该工作区建出原生会话、标题为「时间戳 + 目标前 20 字」、**自动切过去**、handoff 全文作为首条消息进入会话 |

### 构建环境要求

| 项 | 要求 |
| --- | --- |
| Node | >= 22（实测 v24.19.0 / v22.20.0） |
| pnpm | 11.x（实测 11.25.0 / 11.21.0） |
| tsdown | 0.15.x |

### 已知的交互坑

- **点不动的 `span`**：面板折叠/展开最初写成 `<span onClick>`，在这个宿主里**点不动**
  （没有原生点击语义）。改用真正的 `<button>` 后正常，顺带键盘可达。
- **调试残留会让整条链路必然失败**（T-050 修）：`openNativeDiscussion` 里曾调用 5 次未定义的 `step()`，
  第一次调用就抛 ReferenceError，catch 里那次又抛一次——「讨论」按钮在任何宿主上都只会报「讨论失败：step is not defined」。
  现在有契约测试守着（`tests/client.contract.mjs` 加载**构建产物**真跑一遍讨论流程）。

### 已知的构建坑

- **React 必须标成 external**：tsdown 0.15 里只在 `deps.neverBundle` 写 `react` **不生效**，
  实测会被内联进产物（46 KB），界面上等于塞了第二份 React。必须同时给顶层 `external: ["react", ...]`，
  产物会变成 `require("react")`。
- **产物要入库**：宿主按 `exports["./client"]` 直接取文件，git 安装不会帮你构建。
- **服务端半边也要构建**：宿主按 `main` 加载 `lib/index.js`。只构建客户端时 profile 直接起不来：
  `Cannot find module .../dsh-learning-navigator/lib/index.js`。本项目用 tsdown 的**数组配置**同时产出两侧。
- **客户端 `inject` 必须含 `slots`**：少了它，宿主报
  `cannot get property "slots" without inject`，界面顶部显示红色的 `Failed to load plugins`，面板不出现。
- **两半共用的东西放 `src/shared.ts`**：工作区名、数据形状、`errorText`。导入写 `.ts` 后缀
  （tsconfig 开了 `allowImportingTsExtensions`），这样契约测试能用 Node 类型剥离直接加载源码。
- **`pnpm typecheck` 要 `@types/node`**：tsconfig 一直声明了 `types: ["node"]`，但依赖里没有，以前 typecheck 根本跑不起来
  （也就没发现 `LearningPanel` 的 props 默认值让 `createElement` 类型推断失败）；现在是 devDependency。

## 每次 dsh 升级后的冒烟（三步）

1. **hello world 面板**：重启 `dsh --profile web`，在「学习领航员」工作区的会话里出现「学习」面板；
   在别的工作区里不出现；
2. **一次出题**：调一次本地 CLI（面板按钮触发），确认子进程链路通；
3. **一次讨论**：开一次原生会话/降级链路（T-040），确认会话进了「学习领航员」工作区、上下文预填成功。

三步任一失败 → 按上面的**接缝清单**逐项核对，把结论补进**版本兼容矩阵**。

## 适配铁律（长期有效）

- **只用公开 `ctx` 接缝**：不 import 宿主内部模块、不碰 `process.binding` 之类私有入口；
- **绝不绕过鉴权**：拿不到会话接缝就降级，不去伪造 cookie 或桌面令牌；
- **接缝变动按矩阵核对**：升级后先跑冒烟，再逐项填表，不要凭印象判断「应该没变」；
- **核对以宿主源码为准**：接缝形状随版本变（0.1.5 → 0.2.0 的会话接缝就整套换了），写进代码前先读对应版本的类型声明。

## 目录结构

```
plugin/
├── package.json           # dsh.bundle.patch + dsh.client 清单、exports、build/typecheck/test 脚本
├── tsdown.config.ts       # 两侧构建（客户端用 ModuleLoader 包装）
├── cordis.patch.yml       # 服务端挂载点
├── src/
│   ├── index.ts           # 服务端入口：接线 + inject（connection / workspaceRegistry）
│   ├── shared.ts          # 两半共用：工作区名、数据形状、errorText
│   ├── server/learning.ts # 服务端逻辑：工作区过滤、读 profile/、白名单跑 CLI
│   └── client/index.tsx   # 界面入口：工作区过滤后注入「学习」面板、讨论原生会话
├── tests/
│   ├── learning.contract.mjs  # 服务端契约（类型剥离加载源码）
│   └── client.contract.mjs    # 客户端契约（加载构建产物 lib/client.js）
└── lib/                   # 构建产物（已入库）
```

## 路线图

| 任务 | 内容 |
| --- | --- |
| T-038 ✅ | 插件骨架：装得上、界面出「学习」面板、接缝与兼容矩阵成文 |
| T-039 ✅ | 学习面板 v1：画像/任务/地图 + 按钮经 `python -m src.cli` 子进程执行；项目路径可配（浏览器真机验收见 项目文档/assets/DSH插件-学习面板v1.png） |
| T-040 ✅ | 任务讨论原生会话：用 `ctx.sessions` 预填 handoff；无接缝则降级到 headless + 面板自渲染 |
| T-046 ✅ | 讨论会话归入「学习领航员」专用工作区 |
| T-050 ✅ | 只在「学习领航员」工作区启用（客户端注入 + 服务端路由都按工作区过滤）；适配宿主 0.2.0-rc.1 会话接缝；修讨论链路的两处必然失败 |
