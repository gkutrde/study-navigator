// 「能渲染 ≠ 结构合法」实证脚本：把 _bad-structure.html 用真 Chrome 打开，量它到底渲染成什么样。
// 运行：node verify-tolerance.js
const { chromium } = require("playwright");
const path = require("path");

const FILE = "file:///" + __dirname.replace(/\\/g, "/") + "/_bad-structure.html";

(async () => {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const page = await browser.newPage();
  const 报错 = [];
  page.on("pageerror", (e) => 报错.push(e.message));
  await page.goto(FILE, { waitUntil: "load" });

  const r = await page.evaluate(() => {
    const 数 = (s) => document.querySelectorAll(s).length;
    const 盒 = (s) => {
      const el = document.querySelector(s);
      if (!el) return "(没渲染出来)";
      const cs = getComputedStyle(el), b = el.getBoundingClientRect();
      return `${cs.backgroundColor} 高 ${Math.round(b.height)}px`;
    };
    return {
      五个标签各出现几次: { header: 数("header"), nav: 数("nav"), main: 数("main"), aside: 数("aside"), footer: 数("footer") },
      五块底色与高度: { header: 盒("header"), nav: 盒("nav"), main: 盒("main"), aside: 盒("aside"), footer: 盒("footer") },
      屏幕上的可见文字: document.body.innerText.replace(/\s+/g, " ").trim().slice(0, 160),
      正文去空白字数: document.body.textContent.replace(/\s+/g, "").length,
      "浏览器把 <p><h1> 修成了什么": document.querySelector("header").innerHTML.replace(/\s+/g, " ").trim(),
      "浏览器把 ul>div 修成了什么": document.querySelector("nav").innerHTML.replace(/\s+/g, " ").trim(),
      "两个 main 都活着吗": [!!document.querySelector("#m1"), !!document.querySelector("#m2")],
      "footer 里的 p 被浏览器算成了几个": document.querySelectorAll("footer p").length,
    };
  });

  console.log("被验文件：_bad-structure.html（五处故意违规）\n");
  console.log(r);
  console.log("\n页面脚本报错：", 报错.length ? 报错 : "无");
  console.log("\n结论：五处违规全部被浏览器悄悄兜底，页面照样渲染出五个分色块、正文照样显示。");
  console.log("      —— 所以「删掉标签还能渲染」只能证明浏览器宽容，不能证明结构合法。");
  console.log("      真判合法：把文件拖到 https://validator.w3.org/nu/ （书第 6 章那个校验器）。");

  await page.screenshot({ path: path.join(__dirname, "_bad_structure.png"), fullPage: true });
  await browser.close();
})().catch((e) => { console.error("脚本失败:", e.message); process.exit(1); });
