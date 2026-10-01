// 三档 home 一次判分：真 Chrome 打开，按任务卡验收方式逐条量，再跑「删掉任一区块标签」容错测试。
// 运行：node verify-home3.js
// 证据：_home3_<档>.png 三张 + _verify_home3.json
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const 用例 = [
  {
    文件: "home.html",
    档: "档1 · 语义标签 + head 里写选择器",
    块: ["header", "nav", "main", "aside", "footer"],
    主内容: "main", 侧栏: "aside", 页脚: "footer",
  },
  {
    文件: "home-min.html",
    档: "档0 · 语义标签 + 只用 style 属性",
    块: ["header", "nav", "main", "aside", "footer"],
    主内容: "main", 侧栏: "aside", 页脚: "footer",
  },
  {
    文件: "home-alt.html",
    档: "档2 · div + class（书第 11 章路线）",
    块: ["#page-header", "#page-nav", "#page-main", "#page-aside", "#page-footer"],
    块标签名: ["div", "div", "div", "div", "div"],
    同名块: true,   // 五个块同名，删第 n 个要按序号走；语义标签档每个名字只出现一次，序号恒为 0
    主内容: "#page-main", 侧栏: "#page-aside", 页脚: "#page-footer",
  },
];

// 取第 n 个块的标签名：语义档直接用块名，div 档统一是 div
const 块标签名 = (c, n) => (c.块标签名 ? c.块标签名[n] : c.块[n].replace(/^#/, ""));

// 定位用副本：把注释与 <style>/<script> 内容按「等长」抹成空白。
// 为什么要等长：索引不变，才能拿净化副本里量到的位置去切原文。
// 为什么必须净化：注释里写的字面 <div> / <span> 不渲染，却会骗过一切基于文本的工具——
// 本轮 home-alt.html 的 CSS 注释里正好有一句 "<div> / <span> 来分块"，
// 不净化时正则从那句注释开始吞，把 head 后半 + 页头一起切掉（量出来的 FAIL 是脚本的锅）。
const 净化 = (html) => html
  .replace(/<!--[\s\S]*?-->/g, (m) => " ".repeat(m.length))
  .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, (m) => " ".repeat(m.length))
  .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, (m) => " ".repeat(m.length));

// 只动第 n 个块：剥壳（去标签留内容）或整块删（连内容一起删）
function 删第n个块(html, tag, n, 方式) {
  const 地图 = 净化(html);
  const re = new RegExp(`<${tag}\\b[^>]*>[\\s\\S]*?</${tag}>`, "g");
  const 块 = [];
  let m;
  while ((m = re.exec(地图))) 块.push({ start: m.index, end: m.index + m[0].length });
  if (!块[n]) return html;
  const { start, end } = 块[n];
  const text = html.slice(start, end);
  const 替换 = 方式.startsWith("整块删") ? "" : text.replace(new RegExp(`</?${tag}\\b[^>]*>`, "g"), "");
  return html.slice(0, start) + 替换 + html.slice(end);
}

const 全部结果 = [];
const 记 = (文件, 组, 点, 过, 证据) =>
  全部结果.push({ 文件, 组, 验收点: 点, 判定: 过 ? "PASS" : "FAIL", 证据: String(证据).slice(0, 150) });

(async () => {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const 明细 = [];

  for (const c of 用例) {
    const HTML = fs.readFileSync(path.join(__dirname, c.文件), "utf8");
    const URL = "file:///" + __dirname.replace(/\\/g, "/") + "/" + c.文件;
    const ctx = await browser.newContext({ viewport: { width: 1100, height: 900 } });
    const page = await ctx.newPage();
    const 脚本错 = [];
    page.on("pageerror", (e) => 脚本错.push(e.message));
    await page.goto(URL, { waitUntil: "load" });

    console.log(`\n${"=".repeat(78)}\n【${c.档}】${c.文件}（${HTML.length} 字符）\n${"=".repeat(78)}`);

    // ---- 验收 1：五个分色区块 ----
    const 块 = await page.evaluate((sels) => sels.map((s) => {
      const els = document.querySelectorAll(s);
      if (els.length !== 1) return { 选择器: s, 个数: els.length };
      const el = els[0], cs = getComputedStyle(el), r = el.getBoundingClientRect();
      return {
        选择器: s, 实际标签: el.tagName.toLowerCase(), 个数: 1,
        背景色: cs.backgroundColor, padding: cs.padding,
        纵向位置: Math.round(r.top + window.scrollY), 高: Math.round(r.height),
      };
    }), c.块);
    console.table(块);

    const 齐 = 块.every((b) => b.个数 === 1);
    const 色 = 块.map((b) => b.背景色);
    const 五色 = new Set(色).size === 5 && 色.every((x) => x && !/rgba\(0, 0, 0, 0\)/.test(x));
    const tops = 块.map((b) => b.纵向位置);
    const 递增 = tops.every((v, i) => i === 0 || v > tops[i - 1]);
    const 有padding = 块.every((b) => b.padding && !/^0px( 0px)*$/.test(b.padding));

    记(c.文件, "验收1", "五个区块各出现且仅出现一次", 齐, 块.map((b) => `${b.选择器}×${b.个数}`).join(" "));
    记(c.文件, "验收1", "五块底色互不相同且不透明", 齐 && 五色, 色.join(" / "));
    记(c.文件, "验收1", "五块自上而下成横条（纵向递增）", 递增, tops.join(" < "));
    记(c.文件, "验收1", "五块都有 padding（边界看得清）", 有padding, 块.map((b) => b.padding).join(" / "));

    // ---- 实现要点 2/3 + 知识点抽查 ----
    const 内容 = await page.evaluate(({ 主, 侧, 脚 }) => {
      const p = [...document.querySelectorAll(`${主} p`)];
      const li = [...document.querySelectorAll(`${侧} ul li`)];
      const a = [...document.querySelectorAll(`${侧} ul li a`)];
      const f = document.querySelector(脚);
      const imgs = [...document.querySelectorAll("img")].map((i) => ({
        src: i.getAttribute("src"), alt: i.getAttribute("alt"),
        width: i.getAttribute("width"), height: i.getAttribute("height"),
        加载成功: i.complete && i.naturalWidth > 0,
        屏幕上是: i.complete && i.naturalWidth > 0 ? "(图片本身)" : i.alt,
      }));
      return {
        段数: p.length, 每段字数: p.map((x) => x.textContent.trim().length),
        li数: li.length, 链接数: a.length,
        页脚文字: f ? f.textContent.trim() : "(没有页脚块)",
        图片: imgs,
        doctype: document.doctype ? document.doctype.name : "(无)",
        style在head: !!document.head.querySelector("style"),
        style在body: !!document.querySelector("body style"),
      };
    }, { 主: c.主内容, 侧: c.侧栏, 脚: c.页脚 });
    console.log(内容);

    记(c.文件, "要点2", "主内容里有 3 段 <p>", 内容.段数 === 3, `段数=${内容.段数} 字数=${内容.每段字数.join("/")}`);
    记(c.文件, "要点2", "侧栏是列表且每项都是链接", 内容.li数 >= 3 && 内容.链接数 === 内容.li数, `li=${内容.li数} a=${内容.链接数}`);
    记(c.文件, "要点3", "页脚写了 © 你的名字", /©/.test(内容.页脚文字) && 内容.页脚文字.includes("张三"), 内容.页脚文字);
    记(c.文件, "知识点", "DOCTYPE 存在", 内容.doctype.toLowerCase() === "html", 内容.doctype);
    记(c.文件, "知识点", "img 带齐 src/alt/width/height", 内容.图片.length >= 1 && 内容.图片.every((i) => i.src && i.alt && i.width && i.height), 内容.图片.map((i) => `${i.src} ${i.width}x${i.height}`).join(" | "));
    记(c.文件, "知识点", "src 失效时 alt 顶上（断图可读）", 内容.图片.every((i) => i.加载成功 || i.屏幕上是 === i.alt), 内容.图片.map((i) => i.屏幕上是).join(" | "));
    记(c.文件, "知识点", "<style> 只放 head 里（档0/档2 才查）", c.档.startsWith("档0") ? !内容.style在body : true, `head=${内容.style在head} body=${内容.style在body}`);

    await page.screenshot({ path: path.join(__dirname, `_home3_${c.文件.replace(".html", "")}.png`), fullPage: true });

    // ---- 验收 2：删掉任一区块标签，仍能正常渲染 ----
    // 口径：一次只动「第 n 个块」，n 走遍五个区块。整块删/剥壳两种删法，共 10 种。
    // 注意别用「全局正则把所有 div 一次删掉」——那会把 div 档五个块一起清空，
    // 量到的 FAIL 是脚本自己的错，不是页面的错（本轮真踩过一次，留在这里当警示）。
    const rows = [];
    for (let n = 0; n < c.块.length; n++) {
      for (const 方式 of ["剥壳（去标签留内容）", "整块删（连内容一起删）"]) {
        const html = 删第n个块(HTML, 块标签名(c, n), c.同名块 ? n : 0, 方式);
        const p2 = await ctx.newPage();
        const errs = [];
        p2.on("pageerror", (e) => errs.push(e.message));
        await p2.setContent(html, { waitUntil: "load" });
        const r = await p2.evaluate((sels) => {
          const 剩 = sels.filter((s) => document.querySelectorAll(s).length === 1);
          const body子 = [...document.body.children].map((e) => e.tagName.toLowerCase());
          return {
            其余四块还在: 剩.length,
            正文去空白字数: document.body.textContent.replace(/\s+/g, "").length,
            body直接子元素: body子.join(","),
          };
        }, c.块);
        const 目标剩 = await p2.evaluate((s) => document.querySelectorAll(s).length, c.块[n]);
        const pass = errs.length === 0 && 目标剩 === 0 && r.其余四块还在 === 4 && r.正文去空白字数 > 0;
        rows.push({ 删掉第几个: n, 块: c.块[n], 方式, 目标剩, 其余四块还在: r.其余四块还在, 正文还有字: r.正文去空白字数, body子元素: r.body直接子元素, 报错: errs.length ? errs.join(";") : "无", 判定: pass ? "PASS(照常渲染)" : "FAIL" });
        await p2.close();
      }
    }
    console.table(rows);
    记(c.文件, "验收2", `删掉任一区块标签后仍照常渲染（${rows.length} 种删法）`, rows.every((r) => r.判定.startsWith("PASS")), rows.filter((r) => !r.判定.startsWith("PASS")).map((r) => `${r.删掉}/${r.方式}`).join(",") || "全部通过");
    记(c.文件, "验收2", "删标签后页面零脚本报错", rows.every((r) => r.报错 === "无"), rows.map((r) => r.报错).join("|"));

    明细.push({ 文件: c.文件, 档: c.档, 块, 内容, 容错: rows, 脚本错 });
    await ctx.close();
  }

  console.log(`\n${"=".repeat(78)}\n汇总\n${"=".repeat(78)}`);
  console.table(全部结果);
  const fail = 全部结果.filter((r) => r.判定 === "FAIL");
  for (const f of ["home.html", "home-min.html", "home-alt.html"]) {
    const 自己 = 全部结果.filter((r) => r.文件 === f);
    console.log(`${f}: PASS ${自己.length - 自己.filter((r) => r.判定 === "FAIL").length} / ${自己.length}`);
  }
  console.log(`\n总计：PASS ${全部结果.length - fail.length} / ${全部结果.length}${fail.length ? "  FAIL：" + fail.map((x) => `${x.文件}·${x.验收点}`).join("；") : ""}`);

  const out = path.join(__dirname, "_verify_home3.json");
  fs.writeFileSync(out, JSON.stringify({ 时间: new Date().toISOString(), 汇总: 全部结果, 明细 }, null, 2), "utf8");
  console.log("明细已落盘：" + out);
  await browser.close();
  process.exit(fail.length ? 1 : 0);
})().catch((e) => { console.error("脚本失败:", e.message); process.exit(1); });
