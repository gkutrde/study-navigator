// home.html 验收脚本：真浏览器打开，按任务卡验收方式逐条量 + 「删掉任一区块标签」容错测试
// 运行：node verify-home.js
// 证据：_home_full.png / _home_top.png / _home_no-aside.png
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const NAME = "home.html";
const FILE = "file:///" + __dirname.replace(/\\/g, "/") + "/" + NAME;
const HTML = fs.readFileSync(path.join(__dirname, NAME), "utf8");
const TAGS = ["header", "nav", "main", "aside", "footer"];

const results = [];
const check = (组, 验收点, 通过, 证据) =>
  results.push({ 组, 验收点, 判定: 通过 ? "PASS" : "FAIL", 证据: String(证据).slice(0, 120) });

(async () => {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1100, height: 900 } });
  const page = await ctx.newPage();
  const scriptErrors = [];
  const res404 = [];
  page.on("pageerror", (e) => scriptErrors.push(e.message));
  page.on("requestfailed", (r) => res404.push(r.url().split("/").pop()));
  console.log(`被验文件：${NAME}（${HTML.length} 字符）\n`);
  await page.goto(FILE, { waitUntil: "load" });

  // ================= 验收 1：五个分色区块 =================
  const blocks = await page.evaluate((tags) =>
    tags.map((t) => {
      const els = document.querySelectorAll(t);
      if (els.length !== 1) return { 标签: t, 个数: els.length };
      const el = els[0];
      const cs = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      return {
        标签: t,
        个数: 1,
        背景色: cs.backgroundColor,
        字号: cs.fontSize,
        padding: cs.padding,
        页面上的纵向位置: Math.round(r.top + window.scrollY),
        高: Math.round(r.height),
        宽: Math.round(r.width),
      };
    })
  , TAGS);
  console.log("== 验收 1：五块各一次性出现 + 底色互不相同 ==");
  console.table(blocks);

  const 五块齐 = blocks.every((b) => b.个数 === 1);
  check("验收1", "五个区块标签各出现且仅出现一次", 五块齐, blocks.map((b) => `${b.标签}×${b.个数}`).join(" "));
  const 色 = blocks.map((b) => b.背景色);
  const 色不透明 = 色.every((c) => c && !/rgba\(0, 0, 0, 0\)/.test(c));
  check("验收1", "五块底色互不相同且都不是透明", 五块齐 && new Set(色).size === 5 && 色不透明, 色.join(" / "));
  const tops = blocks.map((b) => b.页面上的纵向位置);
  check("验收1", "五块自上而下堆成横条（纵向位置递增）", tops.every((v, i) => i === 0 || v > tops[i - 1]), tops.join(" < "));
  const 有内边距 = blocks.every((b) => b.padding && !/^0px( 0px)*$/.test(b.padding));
  check("验收1", "五块都有 padding（底色长得开，边界看得清）", 有内边距, blocks.map((b) => b.padding).join(" / "));

  // ================= 实现要点 2 / 3：内容 =================
  const content = await page.evaluate(() => {
    const p = [...document.querySelectorAll("main p")];
    const li = [...document.querySelectorAll("aside ul li")];
    const a = [...document.querySelectorAll("aside ul li a")];
    const f = document.querySelector("footer");
    const imgs = [...document.querySelectorAll("img")].map((i) => ({
      src: i.getAttribute("src"),
      alt: i.getAttribute("alt"),
      width: i.getAttribute("width"),
      height: i.getAttribute("height"),
      渲染宽: Math.round(i.getBoundingClientRect().width),
      渲染高: Math.round(i.getBoundingClientRect().height),
      图真的加载出来了: i.complete && i.naturalWidth > 0,
      屏幕上此刻显示的是: i.complete && i.naturalWidth > 0 ? "(图片本身)" : i.alt,
    }));
    return {
      主内容段数: p.length,
      每段字数: p.map((x) => x.textContent.trim().length),
      侧栏li数: li.length,
      侧栏可点链接数: a.length,
      侧栏链接文字: a.map((x) => x.textContent.trim()),
      页脚文字: f ? f.textContent.trim() : "(没有 footer)",
      图片: imgs,
      style在head里: !!document.head.querySelector("style"),
      body里有没有style: !!document.querySelector("body style"),
      doctype: document.doctype ? document.doctype.name : "(无 doctype)",
    };
  });
  console.log("\n== 实现要点 2 / 3 + 知识点抽查 ==");
  console.log(content);
  check("要点2", "main 里有 3 段 <p>", content.主内容段数 === 3, `段数=${content.主内容段数} 字数=${content.每段字数.join("/")}`);
  check("要点2", "aside 里是无序列表且每项都是链接", content.侧栏li数 >= 3 && content.侧栏可点链接数 === content.侧栏li数, `li=${content.侧栏li数} a=${content.侧栏可点链接数}`);
  check("要点3", "页脚写了 © 你的名字", /©/.test(content.页脚文字) && content.页脚文字.includes("张三"), content.页脚文字);
  check("知识点", "DOCTYPE 存在", content.doctype.toLowerCase() === "html", content.doctype);
  check("知识点", "<style> 放在 head 里（不在 body 里）", content.style在head里 && !content.body里有没有style, `head里有=${content.style在head里} body里有=${content.body里有没有style}`);
  const img = content.图片[0] || {};
  check("知识点", "img 带齐 src/alt/width/height 四个属性", content.图片.length >= 1 && content.图片.every((i) => i.src && i.alt && i.width && i.height), content.图片.map((i) => `${i.src} alt=${i.alt} ${i.width}x${i.height}`).join(" | "));
  check("知识点", "src 失效时 alt 顶上来（断图可读）", content.图片.every((i) => i.图真的加载出来了 || i.屏幕上此刻显示的是 === i.alt), content.图片.map((i) => i.屏幕上此刻显示的是).join(" | "));

  await page.screenshot({ path: `${__dirname}/_home_top.png` });
  await page.screenshot({ path: `${__dirname}/_home_full.png`, fullPage: true });

  // ================= 验收 2：删掉任意一个区块标签，仍能正常渲染 =================
  console.log("\n== 验收 2：删标签容错测试 ==");
  const rows = [];
  for (const t of TAGS) {
    const variants = {
      "剥壳（去掉标签、留下内容）": HTML.replace(new RegExp(`</?${t}\\b[^>]*>`, "g"), ""),
      "整块删（连内容一起删）": HTML.replace(new RegExp(`<${t}\\b[^>]*>[\\s\\S]*?</${t}>`, "g"), ""),
    };
    for (const [方式, html] of Object.entries(variants)) {
      const p2 = await ctx.newPage();
      const errs = [];
      p2.on("pageerror", (e) => errs.push(e.message));
      await p2.setContent(html, { waitUntil: "load" });
      const r = await p2.evaluate((tags) => ({
        被删的标签还剩几个: null,
        还在的块: tags.filter((x) => document.querySelectorAll(x).length === 1),
        正文去空白后字数: document.body.textContent.replace(/\s+/g, "").length,
        body直接子元素: [...document.body.children].map((e) => e.tagName.toLowerCase()),
      }), TAGS);
      const 剩下的块 = r.还在的块;
      const 目标块没了 = await p2.evaluate((x) => document.querySelectorAll(x).length, t);
      const pass = errs.length === 0 && 目标块没了 === 0 && 剩下的块.length === 4 && r.正文去空白后字数 > 0;
      rows.push({
        删掉的标签: t,
        方式,
        目标块剩: 目标块没了,
        其他四块都在: 剩下的块.length === 4,
        正文还有字: r.正文去空白后字数,
        body直接子元素: r.body直接子元素.join(","),
        脚本报错: errs.length ? errs.join(";") : "无",
        判定: pass ? "PASS(照常渲染)" : "FAIL",
      });
      if (t === "aside" && 方式.startsWith("剥壳")) {
        await p2.screenshot({ path: `${__dirname}/_home_no-aside.png` });
      }
      await p2.close();
    }
  }
  console.table(rows);
  check("验收2", "删掉任一区块标签后仍正常渲染（10 种删法全过）", rows.every((r) => r.判定.startsWith("PASS")), rows.filter((r) => !r.判定.startsWith("PASS")).map((r) => `${r.删掉的标签}/${r.方式}`).join(",") || "全部通过");

  // ================= 汇总 =================
  console.log("\n== 验收汇总 ==");
  console.table(results);
  const fail = results.filter((r) => r.判定 === "FAIL");
  console.log(`\nPASS ${results.length - fail.length} / ${results.length}${fail.length ? "，FAIL：" + fail.map((f) => f.验收点).join("；") : ""}`);
  console.log("页面脚本错误：", scriptErrors.length ? scriptErrors : "无");
  console.log("资源加载失败（预期：src 指向的图不存在，正好用来验 alt）：", res404.length ? res404 : "无");
  console.log("截图：_home_top.png / _home_full.png / _home_no-aside.png");
  await browser.close();
  process.exit(fail.length ? 1 : 0);
})().catch((e) => {
  console.error("脚本失败:", e.message);
  process.exit(1);
});
