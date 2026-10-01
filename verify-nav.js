// nav.html 验收脚本：真浏览器打开、真点链接、量滚动位置
// 运行：node verify-nav.js
const { chromium } = require("playwright");

// 默认验 nav.html；也可以验别的对等文件：node verify-nav.js nav-min.html
const NAME = process.argv[2] || "nav.html";
const STEM = NAME.replace(/\.html?$/i, "");
const FILE = "file:///" + __dirname.replace(/\\/g, "/") + "/" + NAME;

(async () => {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  console.log(`被验文件：${NAME}`);
  await page.goto(FILE, { waitUntil: "load" });

  // ---------- 验收 3：id 与 href 一一对应 ----------
  const links = await page.evaluate(() =>
    [...document.querySelectorAll(".nav a")].map((a) => {
      const href = a.getAttribute("href");
      return {
        text: a.textContent.trim(),
        href,
        target: a.getAttribute("target") || "(无)",
        idExists: href.startsWith("#") ? !!document.querySelector(href) : "—外站—",
      };
    })
  );
  console.log("== 验收 3：id / href 对应表 ==");
  console.table(links);

  // ---------- 实现要点 2、4：li 排成一行 + 导航背景色 ----------
  const layout = await page.evaluate(() => {
    const lis = [...document.querySelectorAll(".nav li")];
    const tops = lis.map((li) => Math.round(li.getBoundingClientRect().top));
    return {
      liTops: tops,
      一行: new Set(tops).size === 1,
      liDisplay: [...new Set(lis.map((li) => getComputedStyle(li).display))],
      导航背景色: getComputedStyle(document.querySelector(".nav")).backgroundColor,
    };
  });
  console.log("== 实现要点 2 / 4 ==");
  console.log(layout);

  // ---------- 验收 1：点每一项都滚到对应小节 ----------
  console.log("\n== 验收 1：逐项点击，量滚动 ==");
  const rows = [];
  for (const l of links.filter((x) => x.href.startsWith("#"))) {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(150);
    const before = await page.evaluate(() => window.scrollY);
    await page.click(`.nav a[href="${l.href}"]`);
    await page.waitForTimeout(400);
    const after = await page.evaluate((id) => {
      const el = document.querySelector(id);
      const r = el.getBoundingClientRect();
      return {
        scrollY: Math.round(window.scrollY),
        hash: location.hash,
        rectTop: Math.round(r.top),
        vh: window.innerHeight,
      };
    }, l.href);
    rows.push({
      点的是: l.text,
      href: l.href,
      点击前scrollY: before,
      点击后scrollY: after.scrollY,
      位移: after.scrollY - before,
      小节顶部距视口: after.rectTop,
      地址栏hash: after.hash,
      判定:
        after.hash !== l.href
          ? "FAIL(哈希没变)"
          : Math.abs(after.rectTop) <= 2
          ? "PASS(顶到视口顶)"
          : after.rectTop >= 0 && after.rectTop < after.vh
          ? "PASS(进了视口但没到顶)"
          : "FAIL(没滚到)",
    });
  }
  console.table(rows);

  // ---------- 验收 2：外部链接真的开新标签页 ----------
  console.log("\n== 验收 2：外部链接新标签页 ==");
  const ext = links.find((x) => !x.href.startsWith("#"));
  const popupPromise = ctx.waitForEvent("page", { timeout: 10000 }).catch(() => null);
  await page.click(`.nav a[href="${ext.href}"]`);
  const popup = await popupPromise;
  console.log({
    链接文本: ext.text,
    href: ext.href,
    target属性: ext.target,
    是否弹出新标签: !!popup,
    原页面是否还在: !page.isClosed(),
    新标签URL: popup ? popup.url().slice(0, 60) : "(未捕获)",
  });
  if (popup) await popup.close();

  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(200);
  await page.screenshot({ path: `${__dirname}/_${STEM}_top.png` });
  await page.click('.nav a[href="#skills"]');
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${__dirname}/_${STEM}_after_click.png` });

  console.log("\npageerror:", errors.length ? errors : "无");
  await browser.close();
})().catch((e) => {
  console.error("脚本失败:", e.message);
  process.exit(1);
});
