# home.html 验收对照（页头 / 导航 / 主内容 / 侧栏 / 页脚 五区块）

- 任务：做一个 `home.html`，把一张页面拆成"页头 / 导航 / 主内容 / 侧栏 / 页脚"五个区块
- 提交版（接力上下文「本次提交的代码」，11 字符，未截断）：

```html
<h1>张三</h1>
```

- 判分脚本：`verify-home3.js`（真 Chrome 打开、真量计算样式与几何位置、真删标签再渲染，不是肉眼判断）
- 环境：Windows 11 + node v24.19.0 + playwright 1.63.0（`channel: "chrome"`, viewport 1100×900）
- 本轮新增文件（没覆盖任何既有文件）：`home-min.html`、`home-alt.html`、`verify-home3.js`、`verify-tolerance.js`、`verify-structure.js`、`verify-w3c.ps1`、`_bad-structure.html`。跟踪状态：前六个在 `git status` 里是 `??`；`_bad-structure.html`、所有 `_*.png` 被 `.gitignore` 的 `_*` 规则挡住；`notes/` 整个目录本来就不进仓库（你的笔记一贯如此）
- 判分明细（机器可读）：`_verify_home3.json`；原始回包 `_verify_home3.log`

## 一句话结论

**提交的 11 字符只提供了一行一级标题。验收方式 2 条：0 PASS / 2 FAIL；实现要点 4 条：0 命中 / 4 缺失；任务卡列的 4 个知识点：一个都没落到文件里。**

它不是「写错了」，是「还没写」——页面上没有第二个标签、没有一个属性、没有一块背景色，连一个能挑语法错的地方都没有。所以下面的「最小修改」不是打补丁，是把 `<h1>张三</h1>` 那一行**前后各包五段**。

## 表 A：验收方式原文（这一栏才决定过不过）

| # | 验收方式原文 | 提交版 | 判定依据（代码层） | 最小修改 |
|---|---|---|---|---|
| 1 | 浏览器打开能看到五个明显分色的横/纵区块 | **FAIL** | `header / nav / main / aside / footer` 五个选择器全部命中 0 个元素；全页只有一个 `<h1>`，无背景色、无 padding、无边框 | 五块标签并列摆进 `<body>`，每块一个浅色背景（三档任选，见下） |
| 2 | 删掉任意一个区块标签后页面仍然能正常渲染（说明结构本身合法） | **FAIL** | 没有区块标签可删，这条无从测起 | 结构合法之后自然成立；**但括号里的推论是错的，见「暗坑 1」** |

## 表 B：实现要点 4 条

| # | 要点原文 | 提交版 | 说明 |
|---|---|---|---|
| 1 | 五个区块分别用 `<header> <nav> <main> <aside> <footer>` | 缺 | 一个都没有。这五个是 HTML5 的**语义**标签，浏览器默认都当块级、各占一整行，所以纵向堆成五条不需要写任何 CSS |
| 2 | 主内容里放一篇 3 段的短文（`<p>`），侧栏放一个链接列表 | 缺 | 主内容 3 段 `<p>`、侧栏 `<ul><li><a>`，是本轮的「内容量」指标；判分脚本按 `main p` 数段、按 `aside ul li a` 数链接 |
| 3 | 页脚写明"© 你的名字" | 缺 | 提交版里的「张三」在 `<h1>` 里，是标题不是页脚；`©` 一个字都没有 |
| 4 | 用 `style` 或 `<style>` 给五个区块各加一个浅色背景 | 缺 | 提交版一个属性都没写。本轮三档给出两种写法：`style` 属性（档 0）与 `<head>` 里的 `<style>` 选择器（档 1、档 2） |

## 最小修改：三档，都已落盘并实跑过验收

任选一份覆盖你的 `home.html` 就能过。三档的差别只在「样式写在哪」，验收结果完全一致（13/13）。

### 档 0 —— 只求过验收，一行选择器都不写（`home-min.html`，2761 字符）

起点就是你那一行，五个块全部用 `style` 属性上色，`<head>` 里除了 `<meta>`/`<title>` 什么都不放：

```html
<header style="background-color: #f7e6e6; padding: 14px 20px; border: 2px solid #8a8a8a;">
  <h1>张三的主页</h1>                                        <!-- ← 你原来的那一行思路，原样保留在页头 -->
  <img src="avatar.jpg" alt="张三的头像" width="120" height="120" style="border: 1px dashed #8a8a8a;">
</header>

<nav style="background-color: #e3eef7; padding: 14px 20px; border: 2px solid #8a8a8a; border-top: 0;">
  <a href="#home">首页</a> <span style="color: #8a8a8a;">|</span> <a href="#blog">日志</a> …
</nav>

<main id="home" style="background-color: #e9f5e4; padding: 14px 20px; border: 2px solid #8a8a8a; border-top: 0;">
  <h2>三段短文</h2>
  <p>第一段…</p><p>第二段…</p><p>第三段…</p>
</main>

<aside style="background-color: #fbf4dc; padding: 14px 20px; border: 2px solid #8a8a8a; border-top: 0;">
  <ul><li><a href="https://developer.mozilla.org/…">MDN：header 页头</a></li> … </ul>
</aside>

<footer style="background-color: #ece8f7; padding: 14px 20px; border: 2px solid #8a8a8a; border-top: 0;">
  <p>© 张三 · 2026-09-29 · 用 HTML 手写</p>
</footer>
```

代价很直观：同一句 `padding: 14px 20px; border: …` 抄了五遍，改一次要改五处。这就是档 1 存在的理由。

### 档 1 —— 有点代码洁癖（`home.html`，2596 字符）

把底色和边框挪进 `<head>` 的 `<style>` 块，五个标签名直接当选择器用（它们本来就是标签选择器，不需要 class）：

```css
header { background-color: #f7e6e6; }   /* 1 页头   · 浅粉 */
nav    { background-color: #e3eef7; }   /* 2 导航   · 浅蓝 */
main   { background-color: #e9f5e4; }   /* 3 主内容 · 浅绿 */
aside  { background-color: #fbf4dc; }   /* 4 侧栏   · 浅黄 */
footer { background-color: #ece8f7; }   /* 5 页脚   · 浅紫 */

header, nav, main, aside, footer {      /* 公共部分只写一次 */
  padding: 14px 20px;
  border: 2px solid #8a8a8a;
  border-top: 0;                        /* 相邻两块共用一条线，不叠成两条 */
}
header { border-top: 2px solid #8a8a8a; }
```

改一处、五处生效。这也是书上第 8 章 *getting started with CSS* 想让你走的路（那本书主张结构与呈现分离，所以更推荐这一档）。

### 档 2 —— 对照实验：不用语义标签，只用书里讲过的 `div`（`home-alt.html`，3249 字符）

五个块全部改成 `<div id="page-header"> … </div>`，靠 `id` 区分、靠选择器上色，效果一模一样；同时用 `<span>` 在段落里圈住标签名，验证「span 是行内的、不另起一行」。

这一档存在的理由：**Head First 那本书里根本没有这五个语义标签**（详见下面「书籍章节」）。它是「书第 11 章能带你走到哪里」的实物证据，也是「`div` 分块 vs 语义标签分块，屏幕上看不出区别，屏幕阅读器读得出区别」的对照物。

## 知识点落点自查（任务卡列的 4 项）

| 知识点 | 你（三档都）落在哪 |
|---|---|
| HTML 文档结构（DOCTYPE/head/body） | 第 1 行 `<!DOCTYPE html>`；`<html lang="zh-CN">` 包全文；`<head>` 只放 `meta`/`title`（档 1、档 2 另有 `<style>`）；所有可见内容在 `<body>` 里。判分脚本实测 `doctype = html` |
| 块元素与行内元素（div/span） | 五个区块标签**都是块级**，所以不写 CSS 也各占一整行、纵向堆叠（实测纵向位置 `0 < 202 < 259 < 610 < 1023`）；`<span>|</span>` 在导航里**不换行**，与 `<a>` 排在同一行；档 2 用 `div` 承担分块、`span` 承担行内标记，把这条区别摆在同一张页面上 |
| 列表（ul/ol/li） | 侧栏的链接列表 `<ul><li><a href="…">`（5 项，每项都是可点链接）；顺手加了一段 `<ol>` 复习有序列表。`ul` 是**有序号/圆点**的列表，`ol` 是**自动编号**的列表 |
| 图片 img 标签（src/alt/宽高） | 页头 `avatar.jpg`（120×120）、主内容 `photo.jpg`（240×160），四个属性齐；两张图**故意指向不存在的文件**，实测 `naturalWidth = 0` 时屏幕上显示的是 `alt` 文字——这就是「断图可读」的现场证据 |

## 实跑证据（三档全跑过，39/39）

`node verify-home3.js`：

| 文件 | 验收1 五块分色 | 验收2 删标签容错 | 要点2 内容量 | 要点3 页脚 | 知识点 4 项 | pageerror |
|---|---|---|---|---|---|---|
| `home.html` | PASS（五色互异、`0<202<259<610<1023`、padding `14px 20px`） | PASS（10 种删法全过） | PASS（3 段：88/90/76 字；li 5 = a 5） | PASS（`© 张三 · 2026-09-29 · 用 HTML 手写`） | PASS（doctype/style 位置/断图 alt） | 无 |
| `home-min.html` | PASS（同上） | PASS（10 种删法全过） | PASS（3 段：90/90/78 字；li 5 = a 5） | PASS | PASS | 无 |
| `home-alt.html` | PASS（同上，块是 `div#page-*`） | PASS（10 种删法全过） | PASS（3 段：80/81/87 字；li 5 = a 5） | PASS | PASS | 无 |

**总计：PASS 39 / 39。** 截图：`_home3_home.png`、`_home3_home-min.png`、`_home3_home-alt.png`（均为整页长图）。

「删标签容错」的两种删法（判分脚本对每个块各做一遍）：
1. **剥壳**：只去掉 `<main>` 和 `</main>`、内容留下 → 页面照常渲染，其余四块都在。
2. **整块删**：连内容一起删 → 页面照常渲染，其余四块都在。

## 暗坑 1：「能渲染」不等于「合法」（本轮实测，推翻验收方式 2 的括号）

验收方式 2 写的是「删掉任意一个区块标签后页面仍然能正常渲染（**说明结构本身合法**）」。后半句不成立。

`_bad-structure.html` 里我故意塞了五处违规，用真 Chrome 打开（`node verify-tolerance.js`）的结果：

| 故意写的违规 | 浏览器的反应 |
|---|---|
| `<p><h1>标题</h1></p>`（p 里不许放块级标题） | 悄悄拆开：实际 DOM 变成 `<p></p><h1>标题</h1><p></p>` |
| `<ul><div>…</div></ul>`（ul 的直接子元素只能是 li） | 原样保留，不改、不报错、照样显示 |
| 两个 `<main>`（一个文档只允许一个） | 两个都活着，都上色 |
| `<div>` 忘写结束标签 | 自动补上，不影响后面的块 |
| `<p>` 忘写结束标签、`<footer>` 被包进去 | 自动闭合，页脚照样显示 |

**结果：五块全渲染、正文 61 字全显示、`pageerror` 零条。** 也就是说，删标签之后还能显示，证明的只是**浏览器足够宽容**（这是它从 1990 年代活下来的本事），不证明你的 HTML 合法。

正确读法：验收 2 测的是「标签配对和嵌套有没有把后面的内容带崩」，是个**必要条件的下限检查**，不是合法性判决。要真判合法，用校验器：把文件拖进 <https://validator.w3.org/nu/>（Head First 第 6 章讲的那个 W3C 校验器），它会逐条列出上面这五处违规。

顺带说：上面那张表其实就是书第 3 章的「BE the Browser」练习——书里让你自己判断浏览器会把畸形标签怎么改，这里用真浏览器把答案量出来了。

### 判据一：浏览器有没有偷偷改写你的结构（`verify-structure.js`）

原理：把源码里的标签序列抽出来，与浏览器解析后的 `document.documentElement.outerHTML` 标签序列**逐字**比对。一致 = 浏览器一次兜底都没触发；不一致 = 结构被它悄悄改了。

| 文件 | 源码标签数 | 浏览器标签数 | 首个不同 | 判定 |
|---|---|---|---|---|
| `home.html` | 83 | 83 | 无 | 未被改写 |
| `home-min.html` | 83 | 83 | 无 | 未被改写 |
| `home-alt.html` | 91 | 91 | 无 | 未被改写 |
| `_bad-structure.html` | **37** | **41** | 第 9 个：源码 `<h1>` → 浏览器 `</p>` | 被改写 |

三档成品零改写；反面教材凭空多出 4 个标签，从第 9 个标签起就被拆了。红绿对照成立——所以这个检测不是走过场，它抓得住东西。

### 判据二：W3C 官方校验引擎（`verify-w3c.ps1`）

validator.w3.org 背后跑的就是 `vnu.jar`。本机装一份，纯本地跑，31 MB，装在系统 TEMP 里不进项目目录：

```powershell
npm install vnu-jar --prefix "$env:TEMP\vnu-check" --no-audit --no-fund
pwsh -File verify-w3c.ps1        # 自动找 jar；三档要 0 条消息，反面教材要有 error
```

回包（`error 0 / 其他 0` = 干净）：

| 文件 | 期望 | error | 其他 | 判定 |
|---|---|---|---|---|
| `home.html` | clean | **0** | 0 | 符合期望 |
| `home-min.html` | clean | **0** | 0 | 符合期望 |
| `home-alt.html` | clean | **0** | 0 | 符合期望 |
| `_bad-structure.html` | dirty | 5 | 0 | 符合期望 |

反面教材那 5 条 error，逐条命中我故意埋的违规——校验器把一个字都没放过：

| 行 | 校验器原话 | 对应我埋的哪一处 |
|---|---|---|
| 24 | No "p" element in scope but a "p" end tag seen. | `<p><h1>…</h1></p>` |
| 30 | Element "div" not allowed as child of element "ul" in this context. | `<ul><div>…</div></ul>` |
| 36 | A document must not include more than one visible "main" element. | 两个 `<main>` |
| 40 | Unclosed element "div". | aside 里那个忘关的 `<div>` |
| 42 | End tag "aside" seen, but there were open elements. | 同一个 div 引发的连锁 |

**所以「结构合法」有两道机器判据，都过才算数：源码标签序列与 DOM 逐字一致（必要条件）+ 校验器 0 条 error（判定条件）。** 验收方式 2 原来只有第一道的弱化版（删了标签还能渲染），而「能渲染」连第一道都保证不了——它只证明浏览器够宽容。

## 暗坑 2：注释里写的标签，会骗过一切文本工具（本轮真踩）

`home-alt.html` 的 CSS 注释里有一句话：

```css
/* … 只用这本书里真讲过的 <div> / <span> 来分块 … */
```

这句注释**不渲染**，但它让我的判分脚本第一版翻车：脚本用正则 `<div\b[^>]*>[\s\S]*?</div>` 找「第一个 div 块」，结果从那句注释里的 `<div>` 开始匹配，一路吞到页头结束——把 `<head>` 后半和页头整块切掉了。量出来的是一条假 FAIL（正文 0 字），页面本身完全没问题。

修法：定位前先把「注释」和 `<style>`/`<script>` 的内容按**等长**抹成空白，索引不变，再拿这个净化副本去量位置、切原文：

```js
const 净化 = (html) => html
  .replace(/<!--[\s\S]*?-->/g, (m) => " ".repeat(m.length))
  .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, (m) => " ".repeat(m.length))
  .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, (m) => " ".repeat(m.length));
```

同一类坑，这是**第二次**了：nav 那轮的正则把注释里的 `href="#xxx"` 也匹配进来，多报了一个不存在的 `id`（记在 `notes/nav-验收对照.md` 的「踩坑提醒」）。要记进本能的规矩是：**注释不渲染，但会骗过 grep / 正则 / 爬虫 / 批量替换——写自动化的时候，先把注释摘掉。**

## 书籍章节（把任务卡第 4 段那个空填上）

主用书：**《Head First HTML 与 CSS（第 2 版）》**，Elisabeth Freeman & Eric Freeman，O'Reilly（中文版中国电力出版社）。工作区里三份材料各有用处：

- 快速读：`books/蒸馏-HeadFirst-HTML-CSS-2e.md`
- 查原话：`books/_src/head-first-html-css.txt`（29,395 行，CRLF，下面行号都是在这份里现查的）
- 章名核对：`books/_src/head-first-html-css.toc.md`

### 先说一件必须交代的事：这本书里没有 `header`/`nav`/`main`/`aside`/`footer`

蒸馏稿第 1015–1019 行写得很直白：**源材料未提供证据**。这本书出版于 2005–2006 年，全书正文与附录（含"十大未覆盖话题"清单）里都没有这五个 HTML5 语义元素；标签速查表（蒸馏稿 384–423 行）里也没有它们。能查到的最新边界是 XHTML 1.0 Strict + CSS 2.1。

**所以本次任务里「五个语义标签」这一项，书里查不到——看 MDN：**

- <https://developer.mozilla.org/zh-CN/docs/Web/HTML/Element/header>（页头）
- <https://developer.mozilla.org/zh-CN/docs/Web/HTML/Element/nav>（导航）
- <https://developer.mozilla.org/zh-CN/docs/Web/HTML/Element/main>（主内容，一页只能一个）
- <https://developer.mozilla.org/zh-CN/docs/Web/HTML/Element/aside>（侧栏）
- <https://developer.mozilla.org/zh-CN/docs/Web/HTML/Element/footer>（页脚）

书里能替代的只有第 11 章的 `div + class`——档 2 `home-alt.html` 就是那条路的成品。**但任务卡列的 4 个知识点，书里全都有出处**，这才是你真正要读的部分：

| 知识点 | 章节（章名照书里原名） | 行号（`_src/head-first-html-css.txt`） | 重点看 | 跳过 |
|---|---|---|---|---|
| HTML 文档结构（DOCTYPE/head/body） | 第 1 章 *getting to know HTML*（1266–2881）；doctype 在第 6 章 *standards, compliance, and all that jazz*（10275–11872） | 骨架 `<head>`/`<body>` 首次讲 **1297–1355**；`<style>` 放进 `<head>` **2361–2381**；第一条 CSS 就用上 `background-color` **2421–2432**；doctype **10542 起** | 第 1 章：`<html>` 包住全文、`<head>` 装"关于页面的信息"、`<body>` 装可见内容，三者是嵌套关系不是并列；`<style>` **必须**在 `<head>` 里。第 6 章：doctype 放第一行是为了避开 quirks mode | 第 1 章的"Web 服务器怎么发回页面"整段（`1326–1396`）先扫一眼就行；第 6 章的 HTML 简史、strict doctype 迁移清单可以跳过 |
| 块元素与行内元素（div/span） | 第 3 章 *building blocks*（4461–6373）；`div`/`span` 第 11 章 *divs and spans*（18339–20914） | 块级 vs 内联 **5091–5135**（5095 行点名 block = `h1~h6`/`p`/`blockquote`；5096 行点名 inline = `q`/`a`/`em`）；`div` 分块 **18470–18532** | 「**块级元素各占一整行，内联元素跟在同一行里流**」——这一条直接解释了本次验收：五个区块标签为什么不用写一行 CSS 就纵向堆成五条。`span` 只圈行内几个字 | 第 11 章后半的伪类（`a:link`/`:visited`）、层叠、特异性（`744–753`）现在看会糊；第 12 章 *layout and positioning* 的 `float`/`position`/`z-index` 整章留到后面 |
| 列表（ul/ol/li） | 第 3 章 *building blocks*（4461–6373）；属性细节在第 13 章 *tables and more lists*（23654–25529） | 列表的两步构造 **5470–5518**（5470 行原文：先决定用 `<ol>` 还是 `<ul>` 包住列表项；5518 行书里自己反问 `<ol>` 到底是块级还是内联） | 重点：`<ul>` 配 `<li>`、`<ol>` 配 `<li>`，两者只差"要不要自动编号"；列表能嵌套。本次侧栏用的是 `ul`，顺手那段编号是 `ol` | 第 13 章整章的表格（`table`/`tr`/`th`/`td`、`rowspan`/`colspan`、斑马纹）全部跳过；`list-style-type` 去圆点那点留到你要做横排导航时再回来看 |
| 图片 img 标签（src/alt/宽高） | 第 5 章 *adding images*（8189–10274） | **alt 属性 8655–8669**（8655 行 "use the alt attribute for accessibility"；8669 行"给 img 元素补上 alt"）；`<img>` 的正式介绍在第 5 章开头（蒸馏稿记作书页 `411`） | 重点：**一定要写 `alt`**（8662 行：alt 要的是一句简短的描述），以及"图片太大是常见错误"。本次两张图故意指向不存在的文件——书里那个练习正是让你看浏览器怎么处理 `alt` | 第 5 章后半的 GIF/JPEG/PNG 格式之争、透明与 matte 底色配色（`8378–8492` 一带）整段跳过，那是选图阶段的活；第 2 章的相对路径排查也先跳过（本次图片名是随手编的） |

**读的顺序**：第 3 章 5091–5135（块级/内联，这一条最值钱）→ 第 3 章 5470–5518（列表）→ 第 5 章 8655–8669（alt）→ 第 1 章 1297–1355 与 2361–2381（骨架与 `<style>` 的位置）→ 第 6 章 10542 起（doctype 与校验器，配合上面的「暗坑 1」读）。

**这次明确不用读的**：第 4 章（托管 / 域名 / FTP / 默认页 index.html）、第 7 章（XHTML 强制语法，这条路已被 HTML5 取代）、第 10 章（盒模型细节，本次只用到了 `padding` 和 `border`）、第 12 章（浮动与定位——等你要把 `main` 和 `aside` 摆成左右两栏时再来）、第 13 章（表格）、第 14 章（表单）。

## 顺手：接力上下文第 4 段为什么整段是空的

你手上这份是 `profile/handoff/2026-09-29-1338.md`（第 37–42 行原样就是那四行"知识地图里找不到"）。这是**修复前**生成的版本：`op_handoff` 用原始地图去查（地图点写的是书上原话，如「id 做页面内锚点」），而任务卡记的是画像概念名（如「列表（ul/ol/li）」），精确同名交集为 0；且 `next` 早就做了 `apply_alignment`，handoff 这条路径漏了。T-047 已修（`apply_alignment` + 新增 `merge_aligned_names`，测试 `tests/test_t047_handoff_alignment.py`）。

证据：`profile/handoff/2026-09-29-1341.md`（修复后生成的那份 nav 任务接力上下文）第 35–40 行已经正常输出「《Head First HTML 与 CSS（第 2 版）》· 第 2 章 深入超文本」这种格式了。**所以 home 这个任务在看板上再点一次「在 DSH 中继续」重新生成，第 4 段就会自己填上。** 本文档上面那张表是人工逐条核到行号的结果，比自动映射更细（自动映射只到章）。

## 回滚

本轮文件全是新增，没覆盖任何既有文件，所以回滚 = 删掉（被 `.gitignore` 挡住的实验件与截图，删掉同样干净）：

```powershell
Remove-Item home-min.html, home-alt.html, verify-home3.js, verify-tolerance.js, verify-structure.js, verify-w3c.ps1, _bad-structure.html -ErrorAction SilentlyContinue
Remove-Item _home3_home.png, _home3_home-min.png, _home3_home-alt.png, _bad_structure.png -ErrorAction SilentlyContinue
Remove-Item _verify_home3.json, _verify_home3.log -ErrorAction SilentlyContinue
Remove-Item "$env:TEMP\vnu-check" -Recurse -Force -ErrorAction SilentlyContinue   # W3C 校验引擎（31 MB，装在系统 TEMP，不在项目里）
```

只删演示件、想留下自己的版本：`Copy-Item home-min.html home.html -Force`（或换成 `home.html` / `home-alt.html`）。注意 `home.html` 是本轮之前就存在的文件，本文档没有改动它。

## 复跑（任何一档改完都这样验）

```powershell
node verify-home3.js       # 三档一起：五块分色 + 内容量 + 知识点 + 10 种删标签容错
node verify-structure.js   # 浏览器有没有偷偷改写你的结构（三档零改写 / 反面教材被改写）
pwsh -File verify-w3c.ps1  # W3C 官方引擎：三档 0 条消息 / 反面教材 5 条 error
node verify-tolerance.js   # 「能渲染 ≠ 合法」的现场（看反面教材怎么被悄悄兜底）
```

四个脚本的退出码全是 0 才叫全绿：`verify-home3.js` 为 0 表示 39 项全过，有 FAIL 返回 1 并列出是哪份文件、哪一条；`verify-structure.js` 为 0 表示四份文件的改写判定都与期望一致；`verify-w3c.ps1` 为 0 表示三档干净、反面教材有错（找不到 jar 时返回 2 并打印安装命令）。
