"""本地互动看板（serve 命令）：T-012 起步的只读看板，T-013 起升级为「固定动作集」交互版。

边界（[[01-需求与范围确认]]「明确不做」、[[02-系统架构]] 2026-09-27 决策）：

- 只用标准库 http.server，绑定 localhost（127.0.0.1），默认端口 8765；
- 页面是 GET；写操作只有 POST /action/<固定动作>（动作名与入参键都走白名单），
  **没有任何自由命令入口**；PUT/DELETE/PATCH 一律 405；
- 只读文件端点 /file 只认项目目录内的相对路径（挡绝对路径与 .. 穿越）；
- 请求来源校验（T-050）：Host 必须是本机回环名（挡 DNS rebinding），
  写请求带了 Origin/Referer 就必须同源（挡别的网站用表单偷偷触发动作）；
- 每次请求现读文件（单机自用，量级很小）；
- 视觉层（PANEL_STYLE / PANEL_JS）内联、零外部依赖，与渲染逻辑分开存放。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import html
import re
from urllib.parse import parse_qs, urlsplit

from .planner import is_review_record

from .profile import (
    DEFAULT_TOPIC,
    LEVELS,
    KnowledgeProfile,
    ProfileError,
    normalize_point_name,
    write_profile_atomic,
)

TITLE = "学习领航员 · 本地看板"
READ_METHODS = ("GET", "HEAD")
WRITE_METHODS = ("POST", "PUT", "DELETE", "PATCH")

PAGES = (
    ("knowledge", "知识画像", "knowledge.md"),
    ("tasks", "任务记录", "tasks.md"),
    ("syllabus", "知识地图", "syllabus.md"),
)

STYLE = """
  body { font-family: system-ui, "Segoe UI", sans-serif; margin: 2rem auto; max-width: 52rem; line-height: 1.7; color: #222; padding: 0 1rem; }
  nav a { margin-right: 1rem; }
  h1, h2, h3 { line-height: 1.3; }
  code { background: #f2f2f2; padding: 0 .2rem; }
  pre { background: #f7f7f7; padding: .8rem; overflow-x: auto; }
  table { border-collapse: collapse; }
  th, td { border: 1px solid #ddd; padding: .3rem .6rem; }
  .meta { color: #666; font-size: .9rem; }
  /* 待美化：配色、卡片、暗色模式、字号层级都故意留白，方便自己练手 */
"""


# T-015：看板视觉层（内联 CSS + 原生 JS，零外部依赖）。
# 与 STYLE 分开存放，便于后续继续美化而不动渲染逻辑。
PANEL_STYLE = """
:root{
  --bg:#f6f7f9; --surface:#ffffff; --surface-2:#f2f4f7; --border:#e4e7ec;
  --text:#1f2430; --muted:#667085; --accent:#3b5bdb; --accent-weak:#edf0fd;
  --learned:#2563eb; --learned-bg:#e8f0fe;
  --done:#0f9d58; --done-bg:#e6f6ee;
  --unsure:#d97706; --unsure-bg:#fdf3e3;
  --output:#7c3aed; --output-bg:#f1e9fe;
}
*{box-sizing:border-box}
body{background:var(--bg); color:var(--text); -webkit-font-smoothing:antialiased}
.topbar{display:flex; align-items:center; gap:1rem; flex-wrap:wrap; margin-bottom:1.2rem}
.brand{font-weight:700; font-size:1.05rem; letter-spacing:.2px}
.nav a{color:var(--accent); text-decoration:none; margin-right:.9rem; font-size:.95rem}
.nav a:hover{text-decoration:underline}
.actions{display:flex; gap:.6rem; flex-wrap:wrap; margin-bottom:.6rem}
.actions form{display:inline}
button{cursor:pointer; border:1px solid transparent; border-radius:10px; padding:.55rem .95rem; font-size:.95rem;
  background:var(--accent); color:#fff; transition:transform .06s ease, filter .15s ease}
button:hover{filter:brightness(1.06)} button:active{transform:translateY(1px)}
button[disabled]{opacity:.55; cursor:progress}
button.ghost{background:var(--surface); color:var(--accent); border-color:var(--border)}
.grid{display:grid; grid-template-columns:repeat(auto-fill, minmax(21rem, 1fr)); gap:.9rem; margin:0 0 1.4rem}
.card{background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:1rem 1.1rem;
  box-shadow:0 1px 2px rgba(16,24,40,.05); margin-bottom:.9rem}
h1{font-size:1.5rem; margin:0 0 .3rem}
h2{font-size:1.15rem; margin:1.4rem 0 .6rem}
h3{font-size:.95rem; color:var(--muted); text-transform:none; margin:1rem 0 .5rem}
.point{background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:.85rem 1rem;
  box-shadow:0 1px 2px rgba(16,24,40,.05); display:flex; flex-direction:column; gap:.5rem}
.point .point-name{font-weight:600; font-size:1rem}
.evidence{color:var(--muted); font-size:.86rem; line-height:1.5}
.level{display:inline-block; font-size:.76rem; font-weight:600; padding:.12rem .5rem; border-radius:999px;
  border:1px solid transparent; margin-right:.4rem; vertical-align:middle}
.level-学过{color:var(--learned); background:var(--learned-bg); border-color:#c7d7fb}
.level-做过{color:var(--done); background:var(--done-bg); border-color:#bfe6d3}
.level-存疑{color:var(--unsure); background:var(--unsure-bg); border-color:#f3ddb8}
.level-输出{color:var(--output); background:var(--output-bg); border-color:#ddcdfb}
.status-form{display:flex; gap:.4rem; flex-wrap:wrap; align-items:center; margin-top:.2rem}
select,input[type=text]{border:1px solid var(--border); border-radius:9px; padding:.38rem .5rem; font-size:.88rem;
  background:var(--surface); color:var(--text)}
select:focus,input:focus{outline:2px solid var(--accent-weak); border-color:var(--accent)}
.chips{display:flex; gap:.35rem; flex-wrap:wrap}
.chip{border:1px solid var(--border); background:var(--surface); color:var(--muted); border-radius:999px;
  padding:.2rem .6rem; font-size:.82rem; cursor:pointer; font-family:inherit}
.chip[aria-pressed="true"]{border-color:var(--accent); color:var(--accent); background:var(--accent-weak)}
.chip:hover{border-color:var(--accent); color:var(--accent)}
.task-card{background:var(--surface); border:1px solid var(--border); border-left:3px solid var(--accent);
  border-radius:12px; padding:1rem 1.1rem; margin-bottom:.8rem; box-shadow:0 1px 2px rgba(16,24,40,.05)}
.task-head{display:flex; align-items:center; gap:.6rem; justify-content:space-between; margin-bottom:.4rem}
.task-when{color:var(--muted); font-size:.86rem; font-variant-numeric:tabular-nums}
.task-goal{font-weight:600; font-size:1.02rem; margin-bottom:.3rem}
.acceptance{color:var(--muted); font-size:.88rem; margin-top:.4rem}
/* T-030：提交作业是主要动作，用主按钮样式（醒目、可点区域更大） */
.btn-primary{background:var(--accent); border:1px solid var(--accent); color:#fff; font-weight:600;
  border-radius:8px; padding:.5rem .95rem; font-size:.92rem; cursor:pointer; font-family:inherit}
.btn-primary:hover{filter:brightness(.94)}
.btn-primary:disabled{opacity:.6; cursor:default}
.review-form{display:flex; flex-direction:column; gap:.45rem; margin-top:.55rem}
.review-form textarea{width:100%; box-sizing:border-box; font-family:ui-monospace,Consolas,monospace;
  font-size:.86rem; padding:.5rem; border:1px solid var(--border); border-radius:8px; resize:vertical}
.review-form .btn-primary{align-self:flex-start}
/* T-031：DSH 接力是次要动作，用次按钮（描边，不与主按钮抢注意力） */
.btn-secondary{background:var(--surface); border:1px solid var(--accent); color:var(--accent);
  font-weight:600; border-radius:8px; padding:.45rem .9rem; font-size:.9rem; cursor:pointer; font-family:inherit}
.handoff-form{margin-top:.5rem}
/* T-034：卡片下方聊天面板 */
.chat-panel{margin-top:.6rem; border-top:1px dashed var(--border); padding-top:.6rem}
.btn-chat-toggle{background:var(--surface); border:1px dashed var(--accent); color:var(--accent);
  border-radius:8px; padding:.45rem .9rem; font-size:.9rem; cursor:pointer; font-family:inherit}
.chat-body{margin-top:.5rem}
.chat-log{display:flex; flex-direction:column; gap:.5rem; max-height:22rem; overflow-y:auto; padding-right:.2rem}
.chat-turn{display:flex; gap:.5rem; align-items:flex-start; font-size:.92rem}
.chat-who{flex:0 0 3.2rem; color:var(--muted); font-size:.82rem; padding-top:.15rem}
.chat-user{flex-direction:row-reverse}
.chat-user .chat-who{text-align:right}
.chat-user .chat-text{background:var(--accent-weak, #eef2ff); border-radius:8px; padding:.4rem .6rem}
.chat-stamp{display:block; font-size:.72rem; color:var(--muted); margin-top:.1rem}
.chat-thinking{margin-top:.35rem; font-size:.85rem}
.chat-thinking summary{cursor:pointer; color:var(--muted)}
.chat-thinking-body{margin-top:.3rem; padding:.5rem; background:var(--surface);
  border:1px dashed var(--border); border-radius:8px; white-space:pre-wrap}
.file-link{color:var(--accent); text-decoration:underline}
.chat-markdown p{margin:.35rem 0}
.chat-markdown table{border-collapse:collapse; margin:.4rem 0}
.chat-markdown th,.chat-markdown td{border:1px solid var(--border); padding:.2rem .5rem}
.chat-assistant .chat-text{background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:.4rem .6rem}
.chat-text{white-space:pre-wrap; word-break:break-word; flex:0 1 auto; max-width:88%}
.chat-user .chat-text{margin-left:auto}
.chat-assistant .chat-text{margin-right:auto}
.chat-form{display:flex; gap:.5rem; margin-top:.55rem}
.chat-input{flex:1; padding:.5rem; border:1px solid var(--border); border-radius:8px; font-size:.92rem}
.chat-inline-error{margin-top:.4rem; color:#a3302b; font-size:.85rem}
.chat-hint{margin-top:.4rem}
/* T-035：复习角标 + 薄弱点清单 */
.badge-review{background:#fff4e5; border:1px solid #f0c48a; color:#8a5a00; border-radius:999px;
  padding:.1rem .5rem; font-size:.78rem; margin-left:.5rem}
.weakness-card ul{margin:.4rem 0 0 1.1rem; padding:0}
.weakness-card li{margin:.15rem 0}
/* T-030：被锚点定位到的卡片闪一下，让用户看清"就是这张" */
@keyframes task-flash{from{box-shadow:0 0 0 3px var(--accent)}to{box-shadow:0 1px 2px rgba(16,24,40,.05)}}
.task-flash{animation:task-flash 1.6s ease-out}
.chip.danger{border-color:#f5c6c4; color:#a3302b}
.chip.danger:hover{background:#fdecec; border-color:#f0a8a5; color:#8f2420}
.point-chip{border-color:#c7d7fb; color:var(--learned)}
.point-chip:hover{background:var(--learned-bg); border-color:var(--accent)}
.nav a.active{font-weight:600; text-decoration:underline}
.topic-filter{display:flex; align-items:center; gap:.5rem; flex-wrap:wrap; margin-top:.5rem}
.topic-item{display:flex; align-items:center; gap:.25rem; font-size:.88rem; cursor:pointer}
/* 任务卡里是 markdown 渲染结果：收敛标题层级，避免与区块标题打架 */
.task-card h1{font-size:1.05rem; margin:.2rem 0 .6rem; color:var(--muted); font-weight:600}
.task-card h2{font-size:1.05rem; margin:1rem 0 .4rem}
.task-card h3{font-size:.95rem; margin:.8rem 0 .3rem; color:var(--text)}
.task-card p{margin:.35rem 0}
.task-card ol,.task-card ul{margin:.3rem 0 .3rem 1.1rem; padding:0}
.task-card li{margin:.18rem 0}
.result-ok,.result-err{border-radius:12px; padding:.7rem .9rem; margin:.6rem 0; font-size:.92rem; border:1px solid transparent}
.result-ok{background:var(--done-bg); color:#0b6b3d; border-color:#bfe6d3}
.result-err{background:#fdecec; color:#a3302b; border-color:#f5c6c4}
/* T-026：原地失败提示（不跳变、不刷新） */
/* 默认（无 JS）：js-only 元素不显示——功能由表单兜底 */
.js-only{display:none}
/* 有 JS 时由脚本打开；chips 恢复可见，状态表单的按钮隐藏 */
html.js .js-only{display:flex}
.inline-error{margin-top:.4rem; color:#a3302b; font-size:.85rem}
.inline-error[hidden]{display:none}
.status-submit{margin-left:.4rem}
.status-form select{min-width:5.5rem}
.meta{color:var(--muted)}
.stats{display:flex; gap:.5rem; flex-wrap:wrap; margin:.4rem 0 .2rem}
.stat{background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:.5rem .8rem; font-size:.88rem}
.stat b{font-size:1.05rem}
footer{margin:2rem 0 1rem; color:var(--muted); font-size:.82rem}
@media (max-width: 640px){
  body{margin:1rem auto; padding:0 .8rem}
  .grid{grid-template-columns:1fr}
  h1{font-size:1.3rem}
  .actions button{width:100%}
  .status-form{flex-direction:column; align-items:stretch}
}
@media (prefers-color-scheme: dark){
  :root{--bg:#14161a; --surface:#1c1f24; --surface-2:#22262c; --border:#2e333b; --text:#e7eaf0; --muted:#98a2b3;
    --accent-weak:#222a45; --learned-bg:#1b2a4a; --done-bg:#12332a; --unsure-bg:#3a2c14;
    --output-bg:#2c2145}
}
"""

PANEL_JS = """
(function () {
  // 有 JS 的标记：CSS 用它打开 js-only 元素（chips），没有它时这些元素不显示。
  document.documentElement.className += " js";

  // 渐进增强：没有 JS 时表单照旧能提交（POST 后 303 回跳），下面只是把体验做顺。

  // ---- 0. 所有原地动作共用一个请求函数：POST JSON → 结果对象 {ok, message, ...} ----
  // 服务端回了非 JSON（比如 500 的纯文本）也给出带状态码的中文原因，
  // 只有真正连不上时才走调用方的 catch（"网络错误"）。
  function postAction(url, payload) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (response) {
      return response.text().then(function (text) {
        var data = null;
        try { data = JSON.parse(text); } catch (err) { data = null; }
        if (!data || typeof data !== "object") {
          // 纯文本的短原因（比如来源校验的 403）直接给人看；HTML 错误页之类的就只报状态码
          var brief = text && text.length < 200 && text.indexOf("<") === -1 ? text : "";
          data = {
            ok: false,
            message: brief
              ? "HTTP " + response.status + "：" + brief
              : "服务端返回了无法解析的内容（HTTP " + response.status + "）"
          };
        }
        if (!response.ok) { data.ok = false; }
        return data;
      });
    });
  }

  // ---- 1. 提交后禁用按钮，避免连点 ----
  document.querySelectorAll("form[action^='/action/']").forEach(function (form) {
    form.addEventListener("submit", function () {
      form.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
    });
  });

  // ---- 2. 改状态即时化（T-026）：原地 fetch，不刷新、不滚动 ----
  function showInlineError(box, message) {
    var slot = box.querySelector(".inline-error");
    if (!slot) { return; }
    slot.textContent = message;
    slot.hidden = false;
  }

  function clearInlineError(box) {
    var slot = box.querySelector(".inline-error");
    if (slot) { slot.hidden = true; slot.textContent = ""; }
  }

  function syncChipState(card, level) {
    if (!card) { return; }
    card.querySelectorAll(".chip").forEach(function (chip) {
      chip.setAttribute("aria-pressed", chip.dataset.level === level ? "true" : "false");
    });
  }

  // 失败时把界面恢复成"服务端仍认为的状态"，不做假更新
  function revertSelect(select, box) {
    var card = box.closest(".point");
    if (card && card.dataset.level) { select.value = card.dataset.level; syncChipState(card, card.dataset.level); }
  }

  function applyCounts(counts) {
    Object.keys(counts).forEach(function (level) {
      var node = document.querySelector('[data-stat="' + level + '"] b');
      if (node) { node.textContent = counts[level]; }
    });
  }

  function applyCardLevel(card, level) {
    if (!card) { return; }
    card.dataset.level = level;
    var badge = card.querySelector(".level");
    if (badge) {
      var old = badge.className.match(/level-\\S+/);
      if (old) { badge.classList.remove(old[0]); }
      badge.classList.add("level-" + level);
      badge.textContent = level;
    }
    syncChipState(card, level);
  }

  function submitStatus(form, select) {
    var box = form.parentNode || document;
    var card = form.closest(".point");
    var payload = { name: form.querySelector('input[name="name"]').value, level: select.value };
    select.disabled = true;
    clearInlineError(box);
    postAction("/action/status", payload).then(function (data) {
      select.disabled = false;
      if (!data.ok) {
        revertSelect(select, box);
        showInlineError(box, data.message || "保存失败，请重试");
        return;
      }
      applyCardLevel(card, data.level);
      applyCounts(data.counts || {});
      clearInlineError(box);
    }).catch(function () {
      select.disabled = false;
      revertSelect(select, box);
      showInlineError(box, "网络错误：状态没改动，请重试");
    });
  }

  document.querySelectorAll("form[action='/action/status']").forEach(function (form) {
    var select = form.querySelector("select[name='level']");
    if (!select) { return; }
    var card = form.closest(".point");
    if (card) { syncChipState(card, select.value); }
    // 有 JS：藏掉兜底按钮，改选即提交
    var button = form.querySelector("button");
    if (button) { button.hidden = true; }
    select.addEventListener("change", function (event) {
      event.preventDefault();
      submitStatus(form, select);
    });
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      submitStatus(form, select);
    });
  });

  // ---- 2.5 出题主题多选：选择记进 localStorage（T-029）----
  var TOPIC_KEY = "study-navigator.topics";
  var topicBoxes = document.querySelectorAll('.topic-filter input[name="topics"]');
  if (topicBoxes.length) {
    try {
      var saved = JSON.parse(window.localStorage.getItem(TOPIC_KEY) || "null");
      if (saved && saved.length) {
        topicBoxes.forEach(function (box) { box.checked = saved.indexOf(box.value) !== -1; });
      }
    } catch (err) { /* localStorage 不可用就按默认全选 */ }

    function rememberTopics() {
      var picked = [];
      topicBoxes.forEach(function (box) { if (box.checked) { picked.push(box.value); } });
      try { window.localStorage.setItem(TOPIC_KEY, JSON.stringify(picked)); } catch (err) {}
    }
    topicBoxes.forEach(function (box) { box.addEventListener("change", rememberTopics); });
    var allButton = document.querySelector("[data-topics-all]");
    if (allButton) {
      allButton.addEventListener("click", function () {
        topicBoxes.forEach(function (box) { box.checked = true; });
        rememberTopics();
      });
    }
    var noneButton = document.querySelector("[data-topics-none]");
    if (noneButton) {
      noneButton.addEventListener("click", function () {
        topicBoxes.forEach(function (box) { box.checked = false; });
        rememberTopics();
      });
    }
  }

  // ---- 2.7 锚点定位（T-030）：带 #task-... 进来时滚到那张卡片并高亮 ----
  // 服务器在出题/回写/提交后就是靠这个锚点回跳的；
  // 这里再补一次是为了兼容"浏览器没自动滚"以及页面内点击的情况。
  function revealAnchor() {
    var hash = window.location.hash;
    if (!hash || hash.indexOf("#task-") !== 0) { return; }
    var card = document.getElementById(hash.slice(1));
    if (!card) { return; }
    if (card.scrollIntoView) { card.scrollIntoView({ block: "center" }); }
    card.classList.add("task-flash");
    window.setTimeout(function () { card.classList.remove("task-flash"); }, 1600);
  }
  revealAnchor();
  window.addEventListener("hashchange", revealAnchor);

  // ---- 2.8 聊天面板（T-034）：就地连续对话，不刷新、不跳滚动 ----
  // markup 只来自服务端：已经转义过再渲染的 markdown（与刷新后看到的历史同一个渲染器）。
  // 用户输入永远走 textContent，不当 HTML 解析（T-037 的 XSS 约定）。
  function chatSay(log, who, text, markup) {
    var turn = document.createElement("div");
    turn.className = "chat-turn " + (who === "你" ? "chat-user" : "chat-assistant");
    var label = document.createElement("span");
    label.className = "chat-who";
    label.textContent = who;
    var body = document.createElement("div");
    body.className = "chat-text";
    if (markup) {
      body.className += " chat-markdown";
      body.innerHTML = markup;
    } else {
      body.textContent = text;
    }
    turn.appendChild(label);
    turn.appendChild(body);
    log.appendChild(turn);
  }

  function chatError(panel, text) {
    var slot = panel.querySelector(".chat-inline-error");
    if (!slot) { return; }
    slot.textContent = text;
    slot.hidden = false;
  }

  function chatSend(panel, message) {
    var log = panel.querySelector("[data-chat-log]");
    var input = panel.querySelector(".chat-input");
    var button = panel.querySelector(".chat-send");
    var task = panel.dataset.chatTask;
    var slot = panel.querySelector(".chat-inline-error");
    if (slot) { slot.hidden = true; }
    if (message) { chatSay(log, "你", message); }
    if (input) { input.value = ""; }
    if (button) { button.disabled = true; }
    var pending = document.createElement("div");
    pending.className = "chat-turn chat-assistant chat-pending";
    pending.textContent = "DSH 正在回答…";
    log.appendChild(pending);

    postAction("/action/chat", { task: task, message: message }).then(function (data) {
      pending.remove();
      if (button) { button.disabled = false; }
      if (!data.ok) {
        chatError(panel, data.message || "追问失败，请重试");
        return;
      }
      chatSay(log, "DSH", data.output || "(空回答)", data.html);
    }).catch(function () {
      pending.remove();
      if (button) { button.disabled = false; }
      chatError(panel, "网络错误：这一轮没发出去，请重试");
    });
  }

  document.querySelectorAll(".chat-panel").forEach(function (panel) {
    var toggle = panel.querySelector("[data-chat-toggle]");
    var body = panel.querySelector(".chat-body");
    var form = panel.querySelector("[data-chat-form]");
    if (toggle && body) {
      toggle.addEventListener("click", function () {
        var opening = body.hidden;
        body.hidden = !opening;
        toggle.textContent = opening
          ? "\U0001F4AC 收起聊天面板"
          : "\U0001F4AC 展开聊天面板（就地连续追问）";
        // A 方案（安全收口）：展开面板**不自动发问**。
        // dsh headless 是有工具权限的子进程、工作区就是本仓库（实测会读项目文件），
        // 所以第一次调用必须由用户按「发送」显式触发，不给"点一下就自动跑"的便利。
      });
    }
    if (form) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        var input = panel.querySelector(".chat-input");
        var text = input ? input.value.trim() : "";
        if (!text) { return; }
        chatSend(panel, text);
      });
    }
  });

  // ---- 3. 任务卡片上的知识点 chip = 行内讲解（T-027，走 explain 缓存）----
  function showExplanation(chip) {
    var slot = document.getElementById("explain-slot");
    if (!slot) { return; }
    var name = chip.dataset.explain;
    slot.hidden = false;
    slot.textContent = "正在取「" + name + "」的讲解…";
    postAction("/action/explain", { name: name }).then(function (data) {
      if (!data.ok) {
        // 服务端的失败消息已经自带「讲解 失败：」前缀，这里不再叠一层
        slot.textContent = data.message || "讲解失败，请重试";
        slot.classList.add("result-err");
        return;
      }
      slot.classList.remove("result-err");
      slot.textContent = data.output || "(空)";
    }).catch(function () {
      slot.classList.add("result-err");
      slot.textContent = "网络错误：取讲解失败，请重试";
    });
  }

  document.querySelectorAll(".point-chip[data-explain]").forEach(function (chip) {
    chip.addEventListener("click", function (event) {
      event.preventDefault();
      showExplanation(chip);
    });
  });

  // ---- 4. 任务卡片上的「删除」----
  document.querySelectorAll("[data-delete-task]").forEach(function (button) {
    button.addEventListener("click", function (event) {
      event.preventDefault();
      var when = button.dataset.deleteTask;
      if (!window.confirm("删除任务 " + when + " ？")) { return; }
      var card = button.closest(".task-card");
      postAction("/action/delete_task", { when: when }).then(function (data) {
        if (data.ok) {
          if (card) { card.remove(); }
          return;
        }
        if (card) { showInlineError(card, data.message || "删除失败"); }
      }).catch(function () { window.alert("网络错误：删除失败，请重试"); });
    });
  });

  // ---- 5. 点 chip = 选中该状态并立即生效 ----
  document.querySelectorAll(".chip").forEach(function (chip) {
    chip.addEventListener("click", function () {
      var box = chip.closest(".point") || document;
      var select = box.querySelector("select[name='level']");
      if (!select) { return; }
      select.value = chip.dataset.level;
      var form = select.form;
      if (form) { submitStatus(form, select); }
    });
  });
})();
"""


def _tokenize_table(lines: "list[str]", index: int) -> "tuple | None":
    if index + 1 >= len(lines) or "|" not in lines[index]:
        return None
    sep = lines[index + 1].strip()
    if not re.fullmatch(r"\|?[\s:|-]+\|?", sep) or "-" not in sep:
        return None

    def cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    header = cells(lines[index])
    rows = []
    i = index + 2
    while i < len(lines) and "|" in lines[i] and lines[i].strip():
        rows.append(cells(lines[i]))
        i += 1
    return header, rows, i


FENCE = chr(96) * 3
# T-037：在线查看的文本文件上限（防止把大文件灌进响应）
MAX_SERVED_FILE_BYTES = 512 * 1024
# 请求体上限：动作入参都很小（代码提交本身就截到 8000 字符），1 MiB 绰绰有余
MAX_REQUEST_BYTES = 1024 * 1024
# 本机回环名：看板只绑 127.0.0.1，浏览器里合法的 Host 只有这几种写法
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _authority(value: str) -> tuple[str, int | None] | None:
    """把 Host 头或 Origin/Referer 拆成 (主机名, 端口)；拆不出返回 None。"""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parts = urlsplit(text if "//" in text else "//" + text)
        return (parts.hostname or "").lower(), parts.port
    except ValueError:  # 端口不是数字之类的畸形值
        return None


def request_guard(method: str, host: str = "", origin: str = "", referer: str = "") -> str | None:
    """请求来源校验：返回拒绝原因（中文），None 表示放行。

    看板只绑本机，但浏览器里**任何网站**都能往 127.0.0.1 发请求：
    - DNS rebinding：攻击者域名解析到 127.0.0.1，浏览器把它当同源——此时 Host 头是攻击者域名，
      所以 Host 必须是本机回环名（GET 也查：/file 端点能读项目文件）；
    - 跨站表单：别的网站用 <form method=post action="http://127.0.0.1:8765/action/chat"> 就能
      触发动作（chat 会起一个能读写项目目录的 dsh 进程）——浏览器发跨站 POST 一定带 Origin，
      所以写请求带了 Origin/Referer 就必须与 Host 同源。
    都不带 Origin/Referer 的写请求（命令行工具、测试）照常放行。
    这不是登录鉴权（01「明确不做」），只是确认请求真的来自看板自己的页面。
    """
    if host:
        authority = _authority(host)
        if authority is None or authority[0] not in LOOPBACK_HOSTS:
            return "只接受本机访问（Host 不是 127.0.0.1 / localhost）"
    if str(method or "").upper() not in ("POST", "PUT", "DELETE", "PATCH"):
        return None
    source = origin or referer
    if not source:
        return None
    if source.strip().lower() == "null":
        return "拒绝来源不明的写请求（Origin: null）"
    claimed = _authority(source)
    expected = _authority(host) if host else None
    if claimed is None or claimed[0] not in LOOPBACK_HOSTS:
        return "拒绝跨站写请求：动作只能从看板页面本身发起"
    if expected is not None and claimed != expected:
        return "拒绝跨站写请求：动作只能从看板页面本身发起"
    return None
# 项目根的标志文件：往上找到含这些的目录就当项目根
_PROJECT_MARKERS = ("README.md", ".git", "pyproject.toml", "setup.py")


def _guess_project_root(profile_dir: Path) -> Path:
    """从画像目录往上找项目根；找不到就用画像目录的上一级。"""
    current = Path(profile_dir).resolve()
    for _ in range(6):
        if any((current / marker).exists() for marker in _PROJECT_MARKERS):
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return Path(profile_dir).resolve().parent


# 只把这些前缀下的路径变成可点链接（都在项目目录里，且端点还会再校验一次）
LINKABLE_PREFIXES = ("profile/", "books/", "notes/", "src/", "tests/", "项目文档/")
_PATH_LINK_RE = re.compile(
    r"(?<![\w/.])((?:profile|books|notes|src|tests)/[\w\u4e00-\u9fff./\-]+\.\w+)"
)


def linkify_project_paths(html_text: str) -> str:
    """把已经转义过的 HTML 里的项目内路径变成只读文件端点的链接。

    只在**已转义**的文本上跑（所以不会误伤标签本身：转义后没有 "<" 了）。
    """
    def replace(match: re.Match) -> str:
        raw = match.group(1)
        if raw.startswith("../") or "/../" in raw:
            return match.group(0)
        href = "/file?path=" + html.escape(raw, quote=True)
        return '<a class="file-link" href="' + href + '">' + raw + "</a>"

    return _PATH_LINK_RE.sub(replace, html_text)


def markdown_to_html(markdown: str) -> str:
    """极简 markdown → HTML：先转义，再识别标题/列表/引用/代码块/表格/粗体。"""
    text = (markdown or "").replace("\r\n", "\n")
    lines = text.split("\n")
    out: list[str] = []
    index = 0
    in_ul = in_ol = False

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()

        if stripped.startswith(FENCE):
            close_lists()
            block: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith(FENCE):
                block.append(html.escape(lines[index]))
                index += 1
            index += 1  # 跳过收尾围栏
            out.append("<pre><code>" + "\n".join(block) + "</code></pre>")
            continue

        table = _tokenize_table(lines, index)
        if table:
            close_lists()
            header, rows, index = table
            out.append("<table>")
            out.append("<tr>" + "".join(f"<th>{_inline(c)}</th>" for c in header) + "</tr>")
            for row in rows:
                out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in row) + "</tr>")
            out.append("</table>")
            continue

        if not stripped:
            close_lists()
            index += 1
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            close_lists()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            index += 1
            continue

        if stripped.startswith(">"):
            close_lists()
            out.append(f"<blockquote>{_inline(stripped.lstrip('> ').strip())}</blockquote>")
            index += 1
            continue

        bullet = re.match(r"^[-*]\s+(.*)$", stripped)
        if bullet:
            if not in_ul:
                close_lists()
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_inline(bullet.group(1))}</li>")
            index += 1
            continue

        ordered = re.match(r"^\d+\.\s+(.*)$", stripped)
        if ordered:
            if not in_ol:
                close_lists()
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{_inline(ordered.group(1))}</li>")
            index += 1
            continue

        close_lists()
        out.append(f"<p>{_inline(stripped)}</p>")
        index += 1

    close_lists()
    return "\n".join(out)


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
# 行内代码：一串反引号 … 同样长度的一串反引号。必须是 raw string——
# 以前写成普通字符串 "(" + TICK + "+)(.+?)\1"，"\1" 变成了控制字符 \x01，行内代码从来没渲染过。
_INLINE_CODE_RE = re.compile(r"(`+)(.+?)\1")


def _inline(text: str) -> str:
    """行内元素：先转义再处理粗体与行内代码。"""
    escaped = html.escape(text)
    escaped = _BOLD_RE.sub(r"<strong>\1</strong>", escaped)
    return _INLINE_CODE_RE.sub(r"<code>\2</code>", escaped)


def render_page(title: str, body: str, *, nav: str = "", meta: str = "") -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{STYLE}{PANEL_STYLE}</style></head><body>"
        f"<nav>{nav}</nav>"
        f"<h1>{html.escape(title)}</h1>"
        + (f'<p class="meta">{meta}</p>' if meta else "")
        + f"<main>{body}</main>"
        + f"<script>{PANEL_JS}</script>"
        "</body></html>"
    )


def _read(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _modified(path: Path) -> str:
    if not path.is_file():
        return "（文件不存在）"
    stamp = datetime.fromtimestamp(path.stat().st_mtime)
    return f"文件更新于 {stamp:%Y-%m-%d %H:%M:%S}"


def build_pages(profile_dir: Path | str) -> dict[str, str]:
    """构建全部页面（key 为路径）。每次调用都现读文件。"""
    directory = Path(profile_dir)
    nav_items = [f'<a href="/">首页</a>']
    rendered: dict[str, str | None] = {}
    for slug, label, filename in PAGES:
        markdown = _read(directory / filename)
        rendered[slug] = markdown
        nav_items.append(f'<a href="/{slug}">{label}</a>')
    nav = " · ".join(nav_items)

    pages: dict[str, str] = {}

    # 首页：文件清单与更新时间
    cards = []
    for slug, label, filename in PAGES:
        path = directory / filename
        if rendered[slug] is None:
            cards.append(f"<li>{label}：<em>还没有（{filename} 不存在）</em></li>")
        else:
            cards.append(f'<li><a href="/{slug}">{label}</a> — <span class="meta">{_modified(path)}</span></li>')
    pages[""] = render_page(
        TITLE,
        "<p>本页只读：只接受 GET 请求，不会改动任何文件。</p><ul>" + "".join(cards) + "</ul>",
        nav=nav,
        meta=f"生成于 {datetime.now():%Y-%m-%d %H:%M:%S}",
    )
    pages["index"] = pages[""]

    for slug, label, filename in PAGES:
        markdown = rendered[slug]
        if markdown is None:
            body = f"<p>还没有 {filename}：先运行相应命令生成（sync / distill / next / import）。</p>"
        else:
            body = markdown_to_html(markdown)
        pages[slug] = render_page(
            label, body, nav=nav, meta=_modified(directory / filename)
        )

    return pages


# --- T-013：交互层（固定动作集 + 手工改状态） --------------------------------

def task_anchor(when: str, order: int | None = None) -> str:
    """任务卡片的锚点 id：把时间戳变成 URL 片段能用的形式（T-030）。

    "2026-09-27 11:00" → "task-2026-09-27-11-00"

    `order`（任务块在文件里的次序）用于**同一分钟内出两题**的情况——
    时间戳一样，锚点就会撞。实测：两题都在 15:05 时卡片 id 相同，
    HTML 非法，锚点也只会跳到第一张。
    """
    safe = re.sub(r"[^0-9A-Za-z]+", "-", str(when or "")).strip("-")
    base = f"task-{safe}" if safe else "task-unknown"
    return f"{base}-{order}" if order is not None else base


def _order_of(records, when: str) -> int:
    """同一时间戳可能有多条（同分钟出两题）；取最后那条的次序。"""
    matches = [record.order for record in records if record.when == when]
    return max(matches) if matches else 0


def task_anchors(records) -> dict[tuple[str, int], str]:
    """给一批任务块算唯一锚点：key 是 (时间戳, 文件次序)。

    只有时间戳重复时才加序号后缀，普通情况仍是干净的 task-<时间戳>。
    """
    counts: dict[str, int] = {}
    for record in records:
        counts[record.when] = counts.get(record.when, 0) + 1
    result: dict[tuple[str, int], str] = {}
    for record in records:
        order = record.order if counts.get(record.when, 0) > 1 else None
        result[(record.when, record.order)] = task_anchor(record.when, order)
    return result


ACTION_LABELS = {
    # T-025：客户两次踩坑"同步后画像不变"，所以按钮实际是「同步 + 增量提炼」
    "sync": "同步并提炼",
    # T-027：按时间戳删掉一个任务块（只动目标块）
    "delete_task": "删除任务",
    # T-028：提交作业换取点评
    "review": "提交作业",
    # T-031：把任务上下文交给 DSH 接力；T-033：顺手弹终端；T-034：面板里直接聊
    "handoff": "在 DSH 中继续（弹终端）",
    "chat": "追问",
    "distill": "提炼知识点",
    "next": "出题",
    "done": "回写（标记做过）",
    "explain": "讲解",
}
FIXED_ACTIONS = ("sync", "distill", "next", "done", "explain", "delete_task", "review", "handoff", "chat")

# T-049 入口收敛：弹终端是**次级入口**，默认收起。
# 讨论已经收敛到插件面板 + 原生会话（T-040/T-046），会弹黑框的那条路该默认关掉；
# 想用的人显式开：DSH_TERMINAL_POPUP=1。
TERMINAL_POPUP_ENV = "DSH_TERMINAL_POPUP"
TRUTHY = ("1", "on", "true")

# 任务卡上的「去 DSH 讨论」指引（单一来源，别在多处硬编码文案）
DSH_DISCUSS_HINT = (
    "💬 去 DSH 讨论：在 DSH 里打开「学习领航员」插件面板（对话输入框上方的「学习」按钮），"
    "点这道题卡片上的「讨论」，就会在原生会话里带着本题上下文继续。"
)


def terminal_popup_enabled(environ=None) -> bool:
    """弹终端按钮/动作是否启用。

    默认**关**；只有环境变量 DSH_TERMINAL_POPUP 是明确真值才开。
    =0 / 空串 / 未设置都算关（避免「设了个 0 反而打开」这种坑）。
    """
    source = os.environ if environ is None else environ
    raw = str(source.get(TERMINAL_POPUP_ENV, "") or "").strip().lower()
    return raw in TRUTHY


STATUS_ACTION = "status"
# 动作允许的入参键白名单：多给任何键一律拒绝（防止变成自由命令入口）
ACTION_PARAM_KEYS = {
    "sync": frozenset(),
    "distill": frozenset(),
    # T-029：出题可以只选部分主题（多选，默认全选）
    "next": frozenset({"topics"}),
    # T-024 M-01：done 表单补齐参数入口（知识点 + 产出路径 + 可选复述）
    "done": frozenset({"name", "path", "recite"}),
    # explain（T-022）：只需要知识点名称，不需要产出路径
    "explain": frozenset({"name"}),
    # delete_task（T-027）：只认时间戳，多给任何键一律拒绝
    "delete_task": frozenset({"when"}),
    # review（T-028）：任务时间戳 + 代码
    "review": frozenset({"task", "code"}),
    # handoff（T-031）：只要任务时间戳
    "handoff": frozenset({"task"}),
    # chat（T-034）：任务时间戳 + 这一轮的消息
    "chat": frozenset({"task", "message"}),
    # recite：费曼复述（T-019）。填了它且目标是「输出」态时，走 mark_done 以复用同一套证据规则。
    STATUS_ACTION: frozenset({"name", "level", "note", "recite", "path"}),
}


# 只需要「若干必填文本参数」的动作：(参数名, 缺失时的中文提示)，按顺序作为位置参数传给 operation。
# done / next / review 的入参规则不同（可空 / 多选 / 代码不裁空白），在 _operation_args 里单独处理。
REQUIRED_PARAMS = {
    "explain": (("name", "讲解需要一个知识点名称"),),
    "delete_task": (("when", "删除任务需要给出时间戳（when）"),),
    "handoff": (("task", "DSH 接力需要给出任务时间戳（task）"),),
    "chat": (("task", "追问需要给出任务时间戳（task）"), ("message", "追问需要给出消息内容（message）")),
}


class ActionError(RuntimeError):
    """动作不存在、参数非法或执行失败。"""


def _required(params: dict, key: str, message: str) -> str:
    value = str(params.get(key, "")).strip()
    if not value:
        raise ActionError(message)
    return value


@dataclass
class ActionResult:
    action: str
    ok: bool
    output: str = ""
    status: int = 200
    action_id: int = 0
    timestamp: str = ""


class TaskBoard:
    """交互层：固定动作集 + 手工改状态。

    安全边界（须长期保持）：
    - 动作名必须精确匹配白名单，**不接受任何"命令字符串"**；
    - 每个动作的入参键也走白名单，多给的键直接拒绝；
    - 手工改状态的 level 走 profile.set_level 的三态白名单；
    - 页面不提供任何任意命令输入框。
    """

    def __init__(
        self,
        profile_dir: Path | str,
        *,
        operations: dict | None = None,
        project_root: Path | str | None = None,
    ) -> None:
        self.profile_dir = Path(profile_dir)
        # T-037：回答里的项目内路径要能点开。project_root 是**只读文件端点的白名单根**。
        # 默认从画像目录往上找项目根（认 README.md / .git），而不是简单取 parent——
        # 否则画像放在 profile/_xxx/ 这种子目录时，"profile/knowledge.md" 会解析到
        # 项目外，端点直接 404（浏览器验收实测踩过）。
        self.project_root = Path(project_root) if project_root else _guess_project_root(self.profile_dir)
        self.knowledge_path = self.profile_dir / "knowledge.md"
        self.tasks_path = self.profile_dir / "tasks.md"
        self.syllabus_path = self.profile_dir / "syllabus.md"
        self._operations = dict(operations or {})
        # 页面只展示「最近一次」动作结果：只留这一条（以前整段会话的结果全攒在列表里只增不减）
        self._last: ActionResult | None = None
        self._counter = 0

    # --- 动作 ---

    def allowed_actions(self) -> tuple[str, ...]:
        return FIXED_ACTIONS

    def run_action(self, action: str, params: dict | None = None) -> ActionResult:
        """执行一个固定动作。任何非法输入都变成 ok=False 的结果（不抛异常）。"""
        name = str(action or "").strip()
        if name not in FIXED_ACTIONS and name != STATUS_ACTION:
            return self._record(name, f"未知动作：{action}（本看板只支持固定动作集）", status=400)

        supplied = dict(params or {})
        extra = set(supplied) - ACTION_PARAM_KEYS[name]
        if extra:
            return self._record(
                name, f"动作 {name} 不接受参数：{'、'.join(sorted(extra))}", status=400
            )

        try:
            if name == STATUS_ACTION:
                output = self._apply_status(supplied)
            else:
                output = self._run_operation(name, supplied)
        except ActionError as exc:
            return self._record(name, str(exc), status=400)
        except Exception as exc:  # 兜底：外部接口异常也不该把请求打崩
            return self._record(name, f"{type(exc).__name__}", status=500)

        return self._record(name, output, status=200)

    def _record(self, action: str, output: str, *, status: int) -> ActionResult:
        self._counter += 1
        result = ActionResult(
            action=action,
            ok=status == 200,
            output=output,
            status=status,
            action_id=self._counter,
            timestamp=f"{datetime.now():%Y-%m-%d %H:%M:%S}",
        )
        self._last = result
        return result

    @staticmethod
    def _operation_args(name: str, params: dict) -> tuple:
        """把白名单内的入参整理成 operation 的位置参数；缺必填参数抛 ActionError。"""
        if name == "done":
            # 三个都可空：缺什么由 done 命令自己报（它的提示更具体）
            return (params.get("name", ""), params.get("path", ""), params.get("recite", ""))
        if name == "next":
            # T-029：主题多选；一个都不选时明确报错，不硬出题
            from .planner import normalize_topics

            raw = params.get("topics")
            if raw is not None and not isinstance(raw, (str, list)):
                raise ActionError("topics 必须是主题名列表")
            topics = normalize_topics(raw)
            if isinstance(raw, list) and not topics:
                raise ActionError("至少要选一个主题：当前一个都没选，无法出题")
            return (topics or None,)
        if name == "review":
            task = _required(params, "task", "提交作业需要给出任务时间戳（task）")
            if "code" not in params:
                raise ActionError("提交作业需要给出代码（code）")
            return (task, str(params.get("code", "")))  # 代码原样，不裁首尾空白
        return tuple(_required(params, key, message) for key, message in REQUIRED_PARAMS.get(name, ()))

    def _run_operation(self, name: str, params: dict) -> str:
        operation = self._operations.get(name)
        if operation is None:
            raise ActionError(f"动作 {name} 未接线（请通过 serve 启动）")
        args = self._operation_args(name, params)
        try:
            return str(operation(*args))
        except Exception as exc:  # 外部接口失败不该把看板打崩
            raise ActionError(f"{ACTION_LABELS.get(name, name)} 失败：{exc}") from None

    def _apply_status(self, params: dict) -> str:
        from .profile import mark_done, set_level

        name = str(params.get("name") or "").strip()
        level = str(params.get("level") or "").strip()
        note = str(params.get("note") or "").strip()
        recite = str(params.get("recite") or "").strip()
        path = str(params.get("path") or "").strip()
        if not name:
            raise ActionError("缺少知识点名称")
        if level not in LEVELS:
            raise ActionError(f"状态不合法：{level or '（空）'}；只能是 {'/'.join(LEVELS)}")

        try:
            profile = KnowledgeProfile.load(self.knowledge_path)
            if recite:
                # T-019：复述走 mark_done，保证「输出」态的证据拼装只有一处实现；
                # 若用户同时选了别的状态，再按显式选择覆盖（手工选择优先于自动升级）。
                updated = mark_done(profile, name, path or "（见复述）", recite=recite)
                if level != "输出":
                    updated = set_level(updated, name, level, note=note)
            else:
                updated = set_level(profile, name, level, note=note)
            write_profile_atomic(self.knowledge_path, updated)
        except ProfileError as exc:
            raise ActionError(str(exc)) from None

        point = updated.find(normalize_point_name(name))
        shown = point.name if point else name
        final_level = point.level if point else level
        suffix = "（已记录复述）" if recite else ""
        return f"已把「{shown}」改为「{final_level}」{suffix}"

    # --- 展示 ---

    def last_result(self) -> ActionResult | None:
        return self._last

    def _result_banner(self, *, for_action: str | None = None) -> str:
        result = self.last_result()
        if result is None:
            return ""
        if for_action and result.action != for_action:
            return ""
        cls = "result-ok" if result.ok else "result-err"
        return f'<div class="{cls}">{html.escape(result.output)}</div>'

    def _action_forms(self) -> str:
        forms = []
        for action in FIXED_ACTIONS:
            label = ACTION_LABELS[action]
            if action in ("delete_task", "review", "handoff", "chat"):
                # T-027/028/031/034：这些都挂在任务卡片上，不在顶部动作区
                continue
            if action == "next":
                # T-029：出题前先选主题。复选框必须在这个表单**内部**才会随表单提交。
                forms.append(self._next_form(label))
                continue
            if action == "explain":
                # 讲解要看哪个知识点由页面输入决定（仍在固定动作集与入参白名单内）
                forms.append(
                    '<form method="post" action="/action/explain" class="explain-form">'
                    '<input type="text" name="name" placeholder="要讲解的知识点" size="18" required>'
                    f'<button type="submit">{html.escape(label)}</button></form>'
                )
                continue
            if action == "done":
                # T-024 M-01：裸按钮点下去必失败（done 需要 name + path），
                # 这里补上下拉（取最近任务涉及的知识点）+ 产出路径 + 可选复述。
                forms.append(self._done_form(label))
                continue
            forms.append(
                f'<form method="post" action="/action/{action}">'
                f'<button type="submit">{html.escape(label)}</button></form>'
            )
        return '<div class="actions">' + "".join(forms) + "</div>"

    def _latest_task_points(self) -> list[str]:
        """最近一次任务涉及的知识点（下拉候选）；读不到就给空列表。"""
        from .planner import read_latest_task_points

        try:
            return read_latest_task_points(self.tasks_path)
        except Exception:  # 读 tasks.md 出任何问题都不该让页面打不开
            return []

    def _weakness_block(self) -> str:
        """T-035：画像页展示当前薄弱点清单（错题本）。"""
        from .weaknesses import load_weaknesses

        try:
            items = load_weaknesses(self.profile_dir)
        except Exception:
            items = []
        if not items:
            return ""
        rows = "".join(
            f'<li>{html.escape(item.text)}'
            + (f'<span class="meta">（最近 {html.escape(item.last_seen)}）</span>' if item.last_seen else "")
            + "</li>"
            for item in items
        )
        return (
            '<div class="card weakness-card">'
            f'<h2>薄弱点清单 <span class="meta">（{len(items)} 条，做掉会自动移除）</span></h2>'
            f"<ul>{rows}</ul>"
            f'<div class="meta">出题时会把这些注入约束，优先让你练到它们。</div>'
            f"</div>"
        )

    def _topic_filter_form(self) -> str:
        """出题的主题多选（T-029）。默认全选；没有 JS 时也照常提交。"""
        from .planner import selectable_topics

        try:
            profile = KnowledgeProfile.load(self.knowledge_path)
        except Exception:
            return ""
        topics = selectable_topics(profile)
        if not topics:
            return ""

        boxes = "".join(
            f'<label class="topic-item"><input type="checkbox" name="topics" '
            f'value="{html.escape(topic)}" checked> {html.escape(topic)}</label>'
            for topic in topics
        )
        return (
            '<div class="topic-filter" id="topic-filter">'
            '<span class="meta">出题主题</span>'
            f"{boxes}"
            '<button type="button" class="chip" data-topics-all>全选</button>'
            '<button type="button" class="chip" data-topics-none>全不选</button>'
            "</div>"
        )

    def _next_form(self, label: str) -> str:
        """出题表单：主题多选 + 提交按钮（T-029）。"""
        return (
            '<form method="post" action="/action/next" class="next-form">'
            f"{self._topic_filter_form()}"
            f'<button type="submit">{html.escape(label)}</button>'
            "</form>"
        )

    def _done_form(self, label: str) -> str:
        points = self._latest_task_points()
        options = "".join(
            f'<option value="{html.escape(name)}">{html.escape(name)}</option>' for name in points
        )
        if options:
            picker = f'<select name="name" required>{options}</select>'
            hint = '<span class="meta">（取自最近一次任务）</span>'
        else:
            picker = '<input type="text" name="name" placeholder="知识点名称" size="14" required>'
            hint = '<span class="meta">（还没出过题，手工填知识点名）</span>'
        return (
            '<form method="post" action="/action/done" class="done-form">'
            + picker
            + hint
            + '<input type="text" name="path" placeholder="产出路径" size="16" required>'
            + '<input type="text" name="recite" placeholder="费曼复述（可空）" size="20">'
            + f'<button type="submit">{html.escape(label)}</button></form>'
        )

    def _status_form(self, point) -> str:
        options = "".join(
            f'<option value="{level}"{" selected" if level == point.level else ""}>{level}</option>'
            for level in LEVELS
        )
        # T-026：状态表单只管"改成哪个状态"——产出路径/复述/说明都归 M-01 的回写表单。
        # chips = 点一下即改（JS 原地更新，不刷新不滚动）；下拉 + 按钮 = **无 JS 兜底**。
        # chips 标 js-only：没 JS 时不可见也不可用，功能靠下面的表单。
        chips = "".join(
            f'<button type="button" class="chip js-only" data-level="{level}">{level}</button>'
            for level in LEVELS
        )
        return (
            '<div class="chips js-only">' + chips + "</div>"
            '<form method="post" action="/action/status" class="status-form">'
            f'<input type="hidden" name="name" value="{html.escape(point.name)}">'
            f'<select name="level" aria-label="状态">{options}</select>'
            '<button type="submit" class="status-submit">保存状态</button>'
            "</form>"
            '<div class="inline-error" hidden></div>'
        )

    # --- 页面（T-027：路由真分离）---

    def _nav(self, active: str) -> str:
        items = [
            ("/", "首页", ""),
            ("/knowledge", "知识画像", "knowledge"),
            ("/tasks", "任务中心", "tasks"),
            ("/syllabus", "知识地图", "syllabus"),
        ]
        links = "".join(
            f'<a href="{href}"{" class=\"active\"" if key == active else ""}>{label}</a>'
            for href, label, key in items
        )
        return f'<div class="topbar"><span class="brand">学习领航员</span><span class="nav">{links}</span></div>'

    def _load_profile(self):
        from .profile import parse_profile

        markdown = _read(self.knowledge_path)
        return parse_profile(markdown) if markdown else KnowledgeProfile()

    def _render(self, title: str, body: str, active: str) -> str:
        return render_page(
            title,
            body,
            nav=self._nav(active),
            meta="只支持固定动作：同步并提炼 / 提炼 / 出题 / 回写 / 讲解 / 改状态 / 删任务。本页不会执行你输入的任何命令。",
        )

    def _toolbar(self) -> str:
        return (
            '<div class="card">'
            + self._action_forms()
            + self._result_banner()
            + "</div>"
        )

    def _stats(self, counts: dict) -> str:
        return '<div class="stats">' + "".join(
            f'<span class="stat level-{level}" data-stat="{level}">{level} '
            f"<b>{counts.get(level, 0)}</b></span>"
            for level in LEVELS
        ) + "</div>"

    # --- 各页面 ---

    def _recent_block(self) -> str:
        """T-044：首页「最近 7 天」摘要卡——把周报的关键数字摆出来。"""
        try:
            from .report import collect_stats

            stats = collect_stats(self.profile_dir, days=7, repo_root=self.project_root)
        except Exception:
            return ""

        moved = stats["moved"]
        tasks = stats["tasks"]
        reviews = stats["review_tasks"]
        done = stats["completed_reviews"]
        fresh_weak = stats["fresh_weaknesses"]

        rows = [
            f"<li>知识点推进：<b>{len(moved)}</b> 个</li>",
            f"<li>新增任务：<b>{len(tasks)}</b> 道（其中复习题 {len(reviews)} 道）</li>",
            f"<li>复习完成：<b>{done}/{len(reviews)}</b></li>",
            f"<li>薄弱点新增/复现：<b>{len(fresh_weak)}</b> 条</li>",
        ]
        if not (moved or tasks or fresh_weak):
            rows.append('<li class="meta">最近 7 天没有活动。</li>')

        return (
            '<div class="card recent-card">'
            "<h2>最近 7 天</h2>"
            "<ul>" + "".join(rows) + "</ul>"
            '<div class="meta">完整版：<code>python -m src.cli report --days 7</code></div>'
            "</div>"
        )

    def _home_page(self) -> str:
        """首页只做概览：动作区 + 四态统计 + 最近 7 天 + 最近一条任务。"""
        profile = self._load_profile()
        records = self._task_records()
        sections = [self._toolbar(), self._recent_block(), self._stats(profile.counts())]
        sections.append(
            f'<p class="meta">画像 {len(profile.points)} 个知识点 ｜ 任务 {len(records)} 条 ｜ '
            f'<a href="/knowledge">看画像</a> · <a href="/tasks">看任务</a> · '
            f'<a href="/syllabus">看地图</a></p>'
        )
        if records:
            latest = max(records, key=lambda item: (item.when, item.order))
            sections.append("<h2>最近任务</h2>")
            sections.append(self._task_card(latest, task_anchors(records)[(latest.when, latest.order)]))
        else:
            sections.append('<div class="card">还没有任务：点上面的「出题」。</div>')
        return self._render("学习领航员 · 首页", "".join(sections), "")

    def _knowledge_page(self) -> str:
        profile = self._load_profile()
        by_topic: dict[str, list] = {}
        for point in profile.points:
            by_topic.setdefault(point.topic or DEFAULT_TOPIC, []).append(point)

        sections = [self._toolbar(), self._stats(profile.counts()), self._weakness_block(), "<h2>知识画像</h2>"]
        if not profile.points:
            sections.append('<div class="card">还没有知识点：先点上面的「提炼知识点」。</div>')
        for topic in sorted(by_topic):
            sections.append(
                f'<h3>{html.escape(topic)} <span class="meta">（{len(by_topic[topic])} 个知识点）</span></h3>'
            )
            sections.append('<div class="grid">')
            for point in by_topic[topic]:
                sections.append(
                    f'<div class="point card" data-point="{html.escape(point.name)}" '
                    f'data-level="{html.escape(point.level)}">'
                    f'<div><span class="level level-{html.escape(point.level)}">'
                    f"{html.escape(point.level)}</span>"
                    f'<span class="point-name">{html.escape(point.name)}</span></div>'
                    f'<div class="evidence">{html.escape(point.evidence)}</div>'
                    f"{self._status_form(point)}</div>"
                )
            sections.append("</div>")
        return self._render("学习领航员 · 知识画像", "".join(sections), "knowledge")

    def read_task_records(self):
        """读结构化任务块（卡片渲染与锚点回跳都用它）；读不到返回空列表。"""
        from .planner import read_task_records

        try:
            return read_task_records(self.tasks_path)
        except Exception:
            return []

    def _task_records(self):
        return self.read_task_records()

    def _task_card(self, record, anchor: str | None = None) -> str:
        chips = "".join(
            f'<button type="button" class="chip point-chip" data-explain="{html.escape(name)}">'
            f"{html.escape(name)}</button>"
            for name in list(record.skills) + ([record.new_skill] if record.new_skill else [])
        )
        source = (
            f'<div class="meta">题目出处：{html.escape(record.source)}</div>' if record.source else ""
        )
        steps = (
            "<ol>" + "".join(f"<li>{html.escape(step)}</li>" for step in record.steps) + "</ol>"
            if record.steps
            else ""
        )
        acceptance = (
            f'<div class="acceptance">验收方式：{html.escape(record.acceptance)}</div>'
            if record.acceptance
            else ""
        )
        reviews = "".join(self._review_block(item) for item in getattr(record, "reviews", []))
        # 与出题计数同一个判定（planner.is_review_record），角标与复习节奏不会各说各的
        is_review = is_review_record(record)
        badge = '<span class="badge-review">复习</span>' if is_review else ""
        return (
            f'<div class="task-card" id="{anchor or task_anchor(record.when)}" '
            f'data-task="{html.escape(record.when)}" data-review="{"1" if is_review else "0"}">'
            f'<div class="task-head"><span class="task-when">{html.escape(record.when)}</span>{badge}'
            f'<button type="button" class="chip danger" data-delete-task="{html.escape(record.when)}">'
            f"删除</button></div>"
            f'<div class="task-goal">{html.escape(record.goal)}</div>'
            f"{source}"
            f'<div class="chips">{chips}</div>'
            f"{steps}{acceptance}"
            f"{reviews}"
            # T-028：提交作业（无 JS 时也是普通表单，渐进增强）
            f'<form method="post" action="/action/review" class="review-form">'
            f'<input type="hidden" name="task" value="{html.escape(record.when)}">'
            f'<textarea name="code" rows="4" placeholder="把代码粘在这里（也可以填本地路径，用 CLI：review {html.escape(record.when)} <文件>）"></textarea>'
            f'<button type="submit" class="btn-primary">提交作业</button>'
            f"</form>"
            # T-049：默认收起弹终端按钮（DSH_TERMINAL_POPUP=1 才显示）
            f"{self._handoff_form(record)}"
            # T-049：无论显不显示终端按钮，都给出「去 DSH 讨论」的指引
            f'<div class="dsh-hint">{html.escape(DSH_DISCUSS_HINT)}</div>'
            # T-034：**主入口**——卡片下方面板里直接连续对话
            f"{self._chat_panel(record)}"
            f'<div class="inline-error" hidden></div>'
            "</div>"
        )

    def _handoff_form(self, record) -> str:
        """T-049：弹终端表单——默认不渲染，DSH_TERMINAL_POPUP=1 才给。"""
        if not terminal_popup_enabled():
            return ""
        return (
            '<form method="post" action="/action/handoff" class="handoff-form">'
            f'<input type="hidden" name="task" value="{html.escape(record.when)}">'
            # 文案取 ACTION_LABELS（单一来源），避免改了标签忘了按钮
            f'<button type="submit" class="btn-secondary">{html.escape(ACTION_LABELS["handoff"])}</button>'
            "</form>"
        )

    def _chat_turn(self, turn) -> str:
        """渲染一轮对话。

        T-037：**回答渲染 markdown，用户输入只转义**。
        这是有意的差别——回答是模型产出、我们想让它好看；用户输入是注入面，必须原样显示。
        """
        who = "你" if turn.role == "user" else "DSH"
        if turn.role == "user":
            body = '<div class="chat-text chat-plain">' + html.escape(turn.text) + "</div>"
        else:
            body = (
                '<div class="chat-text chat-markdown">'
                + linkify_project_paths(markdown_to_html(turn.text))
                + "</div>"
            )
        stamp = (
            f'<span class="chat-stamp">{html.escape(turn.at)}</span>'
            if getattr(turn, "at", "")
            else ""
        )
        # T-037：思考过程默认折叠（<details> 不带 open），想看再点开
        thought = str(getattr(turn, "thinking", "") or "").strip()
        folded = ""
        if thought:
            folded = (
                '<details class="chat-thinking">'
                "<summary>思考过程</summary>"
                '<div class="chat-thinking-body">'
                + html.escape(thought)
                + "</div></details>"
            )
        return (
            f'<div class="chat-turn chat-{html.escape(turn.role)}">'
            f'<span class="chat-who">{html.escape(who)}{stamp}</span>'
            f"{body}{folded}</div>"
        )

    def _chat_panel(self, record) -> str:
        """T-034：任务卡片下方的聊天面板（点开后就在页面上连续对话）。"""
        from .chat_session import load_turns

        try:
            turns = load_turns(self.profile_dir, record.when)
        except Exception:
            turns = []

        log = "".join(self._chat_turn(turn) for turn in turns)
        return (
            # 每张任务卡都有一个面板：不能用固定 id（以前是 id="chat-panel"，多张卡就重复了，HTML 非法）
            f'<div class="chat-panel" data-chat-task="{html.escape(record.when)}">'
            f'<button type="button" class="btn-chat-toggle" data-chat-toggle>'
            f"\U0001F4AC 展开聊天面板（就地连续追问）</button>"
            f'<div class="chat-body" hidden>'
            f'<div class="chat-log" data-chat-log>{log}</div>'
            f'<div class="chat-inline-error" hidden></div>'
            f'<form class="chat-form" data-chat-form>'
            f'<input type="text" class="chat-input" name="message" '
            f'placeholder="输入问题后点「发送」，例如：我的代码哪里不足？">'
            f'<button type="submit" class="btn-primary chat-send">发送</button>'
            f"</form>"
            f'<div class="meta chat-hint">'
            f"回答只渲染到本面板，不刷新页面、不跳滚动。<br>"
            f"⚠️ 点「发送」会在本机启动一个 dsh 进程（headless profile）：它<b>能读写本项目目录</b>，"
            f"请只在你愿意让它看这份代码时使用。"
            f"</div>"
            f"</div>"
            f"</div>"
        )

    def _review_block(self, review) -> str:
        parts = [
            '<div class="review">',
            f'<div class="meta">提交时间：{html.escape(review.submitted_at)}'
            + ("（代码超长，已截断后点评）" if review.truncated else "")
            + "</div>",
            f'<div class="review-feedback"><b>评价</b>：{html.escape(review.feedback)}</div>',
        ]
        if review.suggestion:
            parts.append(f'<div class="review-suggestion"><b>建议</b>：{html.escape(review.suggestion)}</div>')
        parts.append("</div>")
        return "".join(parts)

    def _tasks_page(self) -> str:
        records = self._task_records()
        sections = [self._toolbar(), self._result_banner(for_action="next"), "<h2>任务中心</h2>"]
        if not records:
            sections.append('<div class="card">还没有任务：点上面的「出题」。</div>')
        # T-030：最新在最上。用**稳定排序**而不是 reversed()——
        # 时间戳相同时 reversed 会把文件内的先后也翻过来（后写入的反而沉下去）。
        anchors = task_anchors(records)
        for record in sorted(
            records, key=lambda item: (item.when, item.order), reverse=True
        ):
            sections.append(self._task_card(record, anchors[(record.when, record.order)]))
        sections.append('<div id="explain-slot" class="card" hidden></div>')
        return self._render("学习领航员 · 任务中心", "".join(sections), "tasks")

    def _syllabus_page(self) -> str:
        markdown = _read(self.syllabus_path)
        sections = ["<h2>知识地图</h2>"]
        if markdown:
            body = re.sub(r"^#" + chr(92) + r"s+.*?$", "", markdown.strip(), count=1, flags=re.MULTILINE).lstrip()
            sections.append(f'<div class="card">{markdown_to_html(body)}</div>')
        else:
            sections.append('<div class="card">还没有知识地图：先运行 import 导入蒸馏稿。</div>')
        return self._render("学习领航员 · 知识地图", "".join(sections), "syllabus")

    def pages(self) -> dict[str, str]:
        """四个路由各自独立渲染（T-027 之前它们是同一页）。"""
        home = self._home_page()
        return {
            "": home,
            "index": home,
            "knowledge": self._knowledge_page(),
            "tasks": self._tasks_page(),
            "syllabus": self._syllabus_page(),
        }


class Dashboard:
    """把请求映射到页面；纯函数式，便于单测（不依赖真实 socket）。"""

    def __init__(self, profile_dir: Path | str, board: "TaskBoard | None" = None) -> None:
        self.profile_dir = Path(profile_dir)
        self.board = board

    def handle_request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        content_type: str = "",
    ) -> tuple[int, str, str]:
        verb = (method or "").upper()

        # T-026：POST /action/status 且 Content-Type 是 JSON → 给前端原地更新用的 JSON 响应；
        # 表单提交（application/x-www-form-urlencoded）仍然回 303（无 JS 的渐进增强路径）。
        if verb == "POST":
            _status, _headers, content_type_out, body_out = self.handle_post_request(
                path, body, content_type
            )
            return _status, content_type_out, body_out

        if verb in WRITE_METHODS:
            return 405, "text/plain; charset=utf-8", "只读看板：不接受写请求"
        if verb not in READ_METHODS:
            return 405, "text/plain; charset=utf-8", "只支持 GET/HEAD"

        route = (path or "/").split("?", 1)[0].strip("/")

        # T-037：只读文件端点（回答里的项目内路径要能点开）
        if route == "file":
            return self._serve_project_file(path or "")

        if self.board is not None:
            pages = self.board.pages()
        else:
            pages = build_pages(self.profile_dir)
        if route in pages:
            return 200, "text/html; charset=utf-8", pages[route]
        return 404, "text/html; charset=utf-8", render_page(
            "404", "<p>页面不存在。</p><p><a href=\"/\">回首页</a></p>"
        )

    def _serve_project_file(self, path: str) -> tuple[int, str, str]:
        """只读地吐一个项目内文件。

        安全边界（这是新增的读接口，必须自己守住）：
        - 只接受**相对路径**，绝对路径一律拒（否则 C:/Windows/... 能读）；
        - 归一化后必须仍在 project_root 之内（挡 ".." 穿越）；
        - 只吐文本，体积上限防止把大文件灌进响应。
        """
        from urllib.parse import parse_qs, unquote, urlparse

        query = parse_qs(urlparse(path).query)
        raw = (query.get("path") or [""])[0]
        raw = unquote(str(raw)).strip()
        if not raw:
            return 400, "text/plain; charset=utf-8", "缺少 path 参数"

        # 拒绝绝对路径与盘符（Windows 的 C:/... 与 POSIX 的 /etc/...）
        candidate = Path(raw.replace("\\", "/"))
        if candidate.is_absolute() or re.match(r"^[A-Za-z]:", raw) or raw.startswith(("/", "\\")):
            return 400, "text/plain; charset=utf-8", "只允许项目内的相对路径"

        root = (
            self.board.project_root
            if self.board is not None
            else self.profile_dir.parent
        )
        try:
            root_real = root.resolve()
            target = (root_real / candidate).resolve()
        except OSError:
            return 400, "text/plain; charset=utf-8", "路径无法解析"

        # resolve 之后再用 relative_to 判定，符号链接也会被这一步挡下
        try:
            target.relative_to(root_real)
        except ValueError:
            return 400, "text/plain; charset=utf-8", "路径越界：只允许项目目录内"

        if not target.is_file():
            return 404, "text/plain; charset=utf-8", "文件不存在"

        try:
            if target.stat().st_size > MAX_SERVED_FILE_BYTES:
                return 400, "text/plain; charset=utf-8", "文件过大，暂不支持在线查看"
            body = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return 400, "text/plain; charset=utf-8", "文件读取失败"

        return 200, "text/plain; charset=utf-8", body

    def _handle_action_json(self, action: str, body: bytes | None) -> tuple[int, str, str]:
        """JSON 动作接口：只认白名单动作与白名单键；成功回 {ok, output}（status 另带计数）。"""
        try:
            params = json.loads((body or b"").decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return self._json_response(400, {"ok": False, "message": "请求体不是合法 JSON"})
        if not isinstance(params, dict):
            return self._json_response(400, {"ok": False, "message": "请求体必须是对象"})

        if self.board is None:
            return self._json_response(405, {"ok": False, "message": "看板未接线"})

        result = self.board.run_action(action, params)
        if not result.ok:
            return self._json_response(result.status, {"ok": False, "message": result.output})

        payload: dict = {"ok": True, "output": result.output}
        if action == "chat":
            # 面板就地渲染要和刷新后看到的历史一致：同一个 markdown 渲染器（先转义再渲染）
            payload["html"] = linkify_project_paths(markdown_to_html(result.output))
        if action == STATUS_ACTION:
            payload.update(
                {
                    "point": str(params.get("name", "")).strip(),
                    "level": str(params.get("level", "")).strip(),
                    "counts": self._current_counts(),
                }
            )
        return self._json_response(200, payload)

    def _json_response(self, status: int, payload: dict) -> tuple[int, str, str]:
        return status, "application/json; charset=utf-8", json.dumps(payload, ensure_ascii=False)

    def _handle_status_json(self, body: bytes | None) -> tuple[int, str, str]:
        """兼容入口：等价于 _handle_action_json("status", body)。"""
        return self._handle_action_json(STATUS_ACTION, body)

    def _current_counts(self) -> dict[str, int]:
        from .profile import KnowledgeProfile

        try:
            return KnowledgeProfile.load(self.board.knowledge_path if self.board else self.profile_dir / "knowledge.md").counts()
        except Exception:
            return {}

    def handle_post_request(
        self, path: str, body: bytes | None, content_type: str = ""
    ) -> tuple[int, dict, str, str]:
        """POST 入口（带响应头），返回 (状态码, 响应头, Content-Type, 响应体)。

        T-030：跳转目标必须能被上层拿到——只有回 303 却把 Location 丢掉，
        浏览器就会跟着当前 URL 再发一次 GET，页面直接空掉。
        """
        route = (path or "/").split("?", 1)[0].strip("/")
        if not route.startswith("action/"):
            return 405, {}, "text/plain; charset=utf-8", "只支持固定动作按钮，不接受自由请求"
        action = route[len("action/"):]
        # T-027：JSON 路径对所有动作都可用（JS 调 explain / delete_task 也要拿 JSON，不能回 303）；
        # 表单路径照旧 303（无 JS 的渐进增强）。
        if "json" in (content_type or "").lower():
            status, ct, payload = self._handle_action_json(action, body)
            return status, {}, ct, payload
        return self._handle_form_post_full(action, body or b"")

    def _handle_form_post(self, action: str, body: bytes) -> tuple[int, str, str]:
        """兼容包装（3 元组）：表单提交走同一条固定动作路径。"""
        status, _headers, content_type, payload = self._handle_form_post_full(action, body)
        return status, content_type, payload

    def _handle_form_post_full(
        self, action: str, body: bytes
    ) -> tuple[int, dict, str, str]:
        """表单提交（无 JS 兜底路径）：解析后走同一个固定动作集。

        成功回 **303 + Dashboard 决定的 Location**（T-030 起会带任务锚点）。
        """
        params = {
            key: values[-1]
            for key, values in parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True).items()
        }
        status, headers, payload = self.handle_action(action, params)
        if status == 303:
            return 303, headers, "text/plain; charset=utf-8", ""
        return status, headers, "text/html; charset=utf-8", payload

    def handle_action(self, action: str, params: dict | None = None) -> tuple[int, dict, str]:
        """处理固定动作的 POST；返回 (状态码, 响应头, 响应体)。

        只认固定动作集；未知动作返回 400 且不执行任何东西。
        """
        if self.board is None:
            return 405, {}, "看板未接线：请通过 serve 命令启动"

        result = self.board.run_action(action, params)
        if not result.ok:
            return result.status, {}, render_page(
                "动作被拒绝",
                f"<p>{html.escape(result.output)}</p><p><a href=\"/\">回首页</a></p>",
            )
        return 303, {"Location": self._redirect_target(action, params)}, ""

    def _redirect_target(self, action: str, params: dict | None) -> str:
        """成功后跳去哪里（T-030）。

        出题/回写/提交作业之后，用户要找的是**那张任务卡片**，
        所以直接带锚点回跳 tasks 页 + 锚点，浏览器自动滚过去——
        不用让用户自己在长列表里翻。
        """
        written = ("next", "done", "review", "delete_task", "handoff")
        if action not in written:
            return "/"

        anchor: str | None = None
        records = self.board.read_task_records() if self.board else []

        if action in ("review", "handoff"):
            # 提交作业 / DSH 接力：跳到**那道题**的卡片
            stamp = str((params or {}).get("task", "")).strip()
            if stamp:
                anchor = task_anchors(records).get((stamp, _order_of(records, stamp)))
                if anchor is None:
                    anchor = task_anchor(stamp)
        elif action in ("next", "done"):
            # 出题/回写：都写「最新那条任务记录」，锚点就取它
            if records:
                newest = max(records, key=lambda item: (item.when, item.order))
                anchor = task_anchors(records)[(newest.when, newest.order)]

        return "/tasks" + (chr(35) + anchor if anchor else "")


class DashboardServer(ThreadingHTTPServer):
    """绑定 localhost 的只读 HTTP 服务。"""

    daemon_threads = True
    # T-024 M-05 实测：Windows 上 allow_reuse_address=True 会让服务**抢占**已被占用的端口
    # （测试里用一个真正 listen 着的 socket 占端口，serve 仍能绑定成功并启动）。
    # 两个服务同时跑同一个端口比"重启偶尔遇到 TIME_WAIT"危险得多，所以关掉。
    allow_reuse_address = False

    def __init__(
        self, address: tuple[str, int], profile_dir: Path | str, board: "TaskBoard | None" = None
    ) -> None:
        # 注意顺序：super().__init__ 会立刻开始处理请求，dashboard 必须先就绪
        self.dashboard = Dashboard(profile_dir, board=board)
        super().__init__(address, _make_handler())


def _make_handler() -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "StudyNavigator/1.0"

        def _rejected(self) -> bool:
            """请求来源校验（见 request_guard）；不合格就直接回 403。"""
            reason = request_guard(
                self.command,
                host=self.headers.get("Host") or "",
                origin=self.headers.get("Origin") or "",
                referer=self.headers.get("Referer") or "",
            )
            if reason is None:
                return False
            self._plain(403, reason)
            return True

        def _respond(self, with_body: bool) -> None:
            if self._rejected():
                return
            status, content_type, body = self.server.dashboard.handle_request(  # type: ignore[attr-defined]
                self.command, self.path
            )
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if with_body:
                self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            self._respond(with_body=True)

        def do_HEAD(self) -> None:  # noqa: N802
            self._respond(with_body=False)

        def _reject(self) -> None:
            self._plain(405, "只读看板：不接受该写请求")

        def do_POST(self) -> None:  # noqa: N802
            # T-026：body 与 Content-Type 交给 Dashboard 决定"JSON 原地更新"还是"表单 303 回跳"
            if self._rejected():
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self._plain(400, "Content-Length 不合法")
                return
            if length < 0:
                self._plain(400, "Content-Length 不合法")
                return
            if length > MAX_REQUEST_BYTES:
                self._plain(413, "请求体过大")
                return
            raw = self.rfile.read(length) if length else b""
            # 用 handle_post_request（带响应头）而不是 handle_request——
            # handle_request 为了兼容只回 3 元组，会把 Location 丢掉。
            status, headers, content_type, body = self.server.dashboard.handle_post_request(  # type: ignore[attr-defined]
                self.path or "/",
                raw,
                self.headers.get("Content-Type") or "",
            )
            payload = body.encode("utf-8")
            self.send_response(status)
            # T-030：跳转目标由 Dashboard 决定（会带 #task-... 锚点）。
            # 曾经这里写死 "/"，把锚点丢掉了——出题后不会滚到新卡片。
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _plain(self, status: int, message: str) -> None:
            payload = message.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if self.command != "HEAD":  # HEAD 只回头部
                self.wfile.write(payload)

        do_PUT = do_DELETE = do_PATCH = _reject  # noqa: N815

        def log_message(self, fmt: str, *args) -> None:
            # 默认实现会往 stderr 打日志；单机自用保持安静即可
            return

    return Handler


def build_server(
    profile_dir: Path | str,
    *,
    port: int = 8765,
    host: str = "127.0.0.1",
    board: "TaskBoard | None" = None,
) -> DashboardServer:
    return DashboardServer((host, port), profile_dir, board)
