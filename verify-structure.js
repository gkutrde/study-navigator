// 「浏览器到底有没有偷偷改写你的结构」检测：源码里的标签序列 vs 浏览器解析后的标签序列。
// 一致 = 浏览器零改写（结构的必要条件通过）；不一致 = 触发了容错，说明写坏了。
// 这是 BE the Browser（Head First 第 3 章练习）的机器版，也是「删标签还能渲染 ≠ 合法」的正面判据。
// 运行：node verify-structure.js
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const 待检 = [
  { 文件: "home.html", 期望: "未被改写（应该一致）" },
  { 文件: "home-min.html", 期望: "未被改写（应该一致）" },
  { 文件: "home-alt.html", 期望: "未被改写（应该一致）" },
  { 文件: "_bad-structure.html", 期望: "被改写（故意违规，应该不一致）" },
];

// 抽标签序列：先按等长抹掉注释与 style/script 内容，再抓 <tag> 与 </tag>（含属性文字，去掉多余空白）
function 抽标签(html) {
  const 干净 = html
    .replace(/<!--[\s\S]*?-->/g, (m) => " ".repeat(m.length))
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, (m) => " ".repeat(m.length))
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, (m) => " ".repeat(m.length));
  const 出 = [];
  const re = /<(\/?)([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>/g;
  let m;
  while ((m = re.exec(干净))) {
    const 闭 = m[1] === "/";
    const 名 = m[2].toLowerCase();
    const 属性 = (m[3] || "").replace(/\s+/g, " ").trim();
    出.push(闭 ? `</${名}>` : `<${名}${属性 ? " " + 属性 : ""}>`);
  }
  return 出;
}

(async () => {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const 结果 = [];
  for (const c of 待检) {
    const 源码 = fs.readFileSync(path.join(__dirname, c.文件), "utf8");
    const page = await browser.newPage();
    await page.goto("file:///" + __dirname.replace(/\\/g, "/") + "/" + c.文件, { waitUntil: "load" });
    const 浏览器版 = await page.evaluate(() => document.documentElement.outerHTML);
    await page.close();

    const A = 抽标签(源码);
    const B = 抽标签(浏览器版);
    const 最短 = Math.min(A.length, B.length);
    const 首个不同 = (() => {
      for (let i = 0; i < 最短; i++) if (A[i] !== B[i]) return { 位置: i, 源码: A[i], 浏览器: B[i] };
      if (A.length !== B.length) return { 位置: 最短, 源码: A[最短] ?? "(源码到此结束)", 浏览器: B[最短] ?? "(浏览器到此结束)" };
      return null;
    })();

    const 一致 = !首个不同;
    结果.push({
      文件: c.文件,
      期望: c.期望,
      源码标签数: A.length,
      浏览器标签数: B.length,
      判定: 一致 ? "未被改写" : "被改写",
      首个不同: 首个不同 ? `第 ${首个不同.位置} 个：源码 ${首个不同.源码} → 浏览器 ${首个不同.浏览器}` : "无",
      符合期望: 一致 === c.期望.startsWith("未被改写"),
    });
  }
  console.table(结果);
  const 全对 = 结果.every((r) => r.符合期望);
  const 坏页 = 结果.find((r) => r.文件 === "_bad-structure.html");
  console.log(`\n反面教材 _bad-structure.html 的现场：${坏页.首个不同}`);
  console.log(全对
    ? "结论：三档成品的标签序列与浏览器解析结果逐字一致 —— 浏览器一次兜底都没触发；反面教材被改写。红绿对照成立。"
    : "结论：有文件与期望不符，见上表「符合期望」列。");
  await browser.close();
  process.exit(全对 ? 0 : 1);
})().catch((e) => { console.error("脚本失败:", e.message); process.exit(1); });
