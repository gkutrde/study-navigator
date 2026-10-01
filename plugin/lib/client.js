window.__ModuleLoader__.load({
  id: "dsh-learning-navigator",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
//#region rolldown:runtime
var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __copyProps = (to, from, except, desc) => {
	if (from && typeof from === "object" || typeof from === "function") for (var keys = __getOwnPropNames(from), i = 0, n = keys.length, key; i < n; i++) {
		key = keys[i];
		if (!__hasOwnProp.call(to, key) && key !== except) __defProp(to, key, {
			get: ((k) => from[k]).bind(null, key),
			enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable
		});
	}
	return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", {
	value: mod,
	enumerable: true
}) : target, mod));

//#endregion
let react = require("react");
react = __toESM(react);

//#region src/client/index.tsx
const { useCallback, useEffect, useState } = react;
/** 面板挂在这个 slot 上（实测有效；备选见 README 接缝清单）。 */
const SLOT = "conversation.input.dock";
const SLOTS = ["conversation.input.dock", "conversation.session.header.actions"];
/**
* 必须声明 inject（少了宿主会拒绝访问对应服务）。
* - slots：挂面板；sessions：T-040 讨论要开原生会话。
* 注意 sessions 若在当前宿主不存在，宿主会拒绝——所以取用时要 try 兜住并降级。
*/
const inject = [
	"slots",
	"sessions",
	"workspaces"
];
const ROUTE = "/api/learning";
const PANEL = {
	width: "100%",
	border: "1px solid var(--dsh-border, rgba(128,128,128,0.28))",
	borderRadius: "10px",
	padding: "10px 12px",
	font: "inherit",
	fontSize: "12px",
	lineHeight: "1.55",
	textAlign: "left"
};
const ROW = {
	display: "flex",
	gap: "8px",
	flexWrap: "wrap",
	alignItems: "center"
};
const BTN = {
	padding: "3px 10px",
	borderRadius: "6px",
	border: "1px solid rgba(128,128,128,0.35)",
	background: "transparent",
	color: "inherit",
	font: "inherit",
	cursor: "pointer"
};
const INPUT = {
	...BTN,
	cursor: "text",
	minWidth: "180px"
};
const H = {
	fontWeight: 600,
	marginTop: "8px"
};
const MUTED = { opacity: .7 };
const ERR = {
	color: "#d64545",
	marginTop: "6px",
	whiteSpace: "pre-wrap"
};
const OUT = {
	...MUTED,
	marginTop: "6px",
	whiteSpace: "pre-wrap",
	maxHeight: "8rem",
	overflow: "auto"
};
/** 专用工作区的名字（T-046）。 */
const WORKSPACE_TITLE = "学习领航员";
/**
* 会话标题：任务时间戳 + 任务目标前 20 字（T-046）。
*/
function sessionTitle(when, goal) {
	const stamp = String(when || "").trim();
	const text = String(goal || "").replace(/\s+/g, " ").trim();
	const head = text.length > 20 ? text.slice(0, 20) + "…" : text;
	if (stamp && head) return stamp + " " + head;
	return stamp || head || "任务讨论";
}
/**
* 拿到（必要时创建）**专用工作区**，返回它的 id（T-046）。
*
* 宿主限制（实测 0.1.5-rc.3，已写进 README）：
*   "workspaces.create" **只接受目录路径**，工作区标题由目录派生；
*   改名是**全局**的（"rename" 没有 per-caller 作用域）。
* 所以"名为「学习领航员」的独立工作区"必须有自己的目录；
* 这里给的是**最接近的降级**：复用/登记项目目录那个工作区，并把它改成专用标题。
*
* @returns { workspaceId, note } —— note 是给用户看的中文说明（成功时为空）
*/
async function ensureDedicatedWorkspace(ctx, cwd) {
	const workspaces = ctx?.workspaces;
	if (!workspaces || typeof workspaces.create !== "function") return { note: "当前宿主没有工作区接缝，讨论会话会落在默认工作区" };
	const path = String(cwd || "").trim();
	if (!path) return { note: "还没配项目路径，讨论会话会落在默认工作区" };
	try {
		const view = await workspaces.create({ path });
		const workspaceId = view?.workspaceId;
		if (!workspaceId) return { note: "工作区创建成功但没拿到 id，讨论会话会落在默认工作区" };
		if (String(view.title || "") !== WORKSPACE_TITLE) {
			if (!workspaceTaken(workspaces, workspaceId)) try {
				await workspaces.rename(workspaceId, WORKSPACE_TITLE);
			} catch {}
		}
		return {
			workspaceId,
			note: ""
		};
	} catch (cause) {
		return { note: "登记专用工作区失败（" + String(cause.message || cause) + "），讨论会话会落在默认工作区" };
	}
}
/** 这个标题是否已被**别的**工作区占用。 */
function workspaceTaken(workspaces, selfId) {
	try {
		return (workspaces?.list?.getSnapshot?.()?.items || []).some((item) => String(item?.workspaceId) !== String(selfId) && String(item?.title || "") === WORKSPACE_TITLE);
	} catch {
		return false;
	}
}
/**
* 把讨论上下文预填进一个**原生会话**（T-040 主路径）。
*
* 全程只用宿主公开接缝：ctx.sessions.create → open → ctx.sessions.get(id).prompt。
* 插件在宿主进程内，所以不受 T-031 那套 CORS/cookie 限制——但也**绝不绕过鉴权**：
* 拿不到接缝就直接降级，不伪造任何凭证。
*
* @returns 失败原因（null 表示成功）
*/
async function openNativeDiscussion(ctx, context, cwd, options = {}) {
	const sessions = ctx?.sessions;
	if (!sessions || typeof sessions.create !== "function") return "当前宿主没有公开的会话接缝";
	try {
		const payload = {};
		if (cwd) payload.cwd = cwd;
		if (options.workspaceId) payload.workspaceId = options.workspaceId;
		const id = await sessions.create(Object.keys(payload).length ? payload : void 0);
		if (typeof sessions.open === "function") sessions.open(id);
		const faceOf = () => {
			try {
				if (typeof sessions.resolveAgentScope === "function" && typeof sessions.sessionOf === "function") {
					const agentCtx = sessions.resolveAgentScope(id);
					const face$1 = agentCtx ? sessions.sessionOf(agentCtx) : null;
					if (face$1 && typeof face$1.prompt === "function") return face$1;
				}
			} catch {}
			if (typeof sessions.get === "function") return sessions.get(id);
			if (typeof sessions.session === "function") return sessions.session(id);
			return null;
		};
		let face = faceOf();
		for (let i = 0; i < 40 && (!face || typeof face.prompt !== "function"); i += 1) {
			await new Promise((done) => setTimeout(done, 250));
			face = faceOf();
		}
		if (!face || typeof face.prompt !== "function") return "会话已创建，但拿不到它的输入面";
		if (options.title && typeof face.rename === "function") try {
			await face.rename(options.title);
			step("renamed ok");
		} catch (cause) {
			step("rename failed: " + String(cause.message || cause));
		}
		else step("rename skipped: title=" + Boolean(options.title) + " fn=" + typeof face.rename);
		for (let attempt = 0; attempt < 3; attempt += 1) {
			const result = await face.prompt([{
				type: "text",
				text: context
			}], "queue");
			step("prompt#" + attempt + " -> " + (result && result.ok === true ? "ok" : JSON.stringify(result).slice(0, 160)));
			if (result && result.ok === true) return null;
			if (result && result.ok === false) {
				const detail = String(result.error?.message || result.error || "未知原因");
				if (attempt < 2 && /not|ready|pending|未|不能/i.test(detail)) {
					await new Promise((done) => setTimeout(done, 800));
					face = faceOf() || face;
					continue;
				}
				return "会话已创建，但预填失败：" + detail;
			}
			return null;
		}
		return "会话已创建，但预填没被接受（重试 3 次）";
	} catch (cause) {
		step("threw: " + String(cause.message || cause));
		return "开原生会话失败：" + String(cause.message || cause);
	}
}
async function call(body) {
	const payload = await (await fetch(ROUTE, {
		method: "POST",
		headers: { "content-type": "application/json" },
		body: JSON.stringify(body)
	})).json().catch(() => ({}));
	if (!payload || typeof payload !== "object") return {
		ok: false,
		message: "面板接口返回了无法解析的内容"
	};
	return payload;
}
/** 学习面板：画像 / 任务 / 知识地图 + 三个动作按钮 + 项目路径配置。 */
function LearningPanel(props = {}) {
	const hostCtx = props?.ctx;
	const [open, setOpen] = useState(false);
	const [profile, setProfile] = useState(null);
	const [tasks, setTasks] = useState([]);
	const [books, setBooks] = useState([]);
	const [root, setRoot] = useState("");
	const [pathInput, setPathInput] = useState("");
	const [error, setError] = useState("");
	const [output, setOutput] = useState("");
	const [busy, setBusy] = useState(false);
	const [notice, setNotice] = useState("");
	const [doc, setDoc] = useState("");
	const [doneName, setDoneName] = useState("");
	const [donePath, setDonePath] = useState("");
	const load = useCallback(async (override) => {
		setError("");
		try {
			const base = override ? { projectRoot: override } : {};
			const p = await call({
				action: "profile",
				...base
			});
			if (!p.ok) {
				setError(String(p.message || "读画像失败"));
				return;
			}
			setProfile(p.data.profile ?? p.data);
			if (p.projectRoot) {
				setRoot(p.projectRoot);
				setPathInput(p.projectRoot);
			}
			const t = await call({
				action: "tasks",
				...base
			});
			if (t.ok) setTasks(Array.isArray(t.data) ? t.data : []);
			const s = await call({
				action: "syllabus",
				...base
			});
			if (s.ok) setBooks(Array.isArray(s.data) ? s.data : []);
		} catch (cause) {
			setError("读项目失败：" + String(cause.message || cause));
		}
	}, []);
	const [loadedOnce, setLoadedOnce] = useState(false);
	useEffect(() => {
		if (!open || loadedOnce) return;
		setLoadedOnce(true);
		load(pathInput || void 0);
	}, [
		open,
		loadedOnce,
		load,
		pathInput
	]);
	const run = useCallback(async (action, extra = {}) => {
		setBusy(true);
		setError("");
		setOutput("");
		try {
			const payload = await call({
				action,
				projectRoot: pathInput,
				...extra
			});
			if (!payload.ok) setError(String(payload.message || "执行失败"));
			else {
				setOutput(String(payload.output || "完成"));
				if (payload.data) {
					if (payload.data.profile) setProfile(payload.data.profile);
					if (Array.isArray(payload.data.tasks)) setTasks(payload.data.tasks);
				}
			}
		} catch (cause) {
			setError("执行失败：" + String(cause.message || cause));
		} finally {
			setBusy(false);
		}
	}, [pathInput]);
	/**
	* 讨论：先试**原生会话**（把 handoff 预填进去，用户在原生会话里继续追问）；
	* 拿不到接缝就**降级**到面板内自渲染（调 headless），并明确告诉用户。
	*/
	const discuss = useCallback(async (when, goal = "") => {
		setBusy(true);
		setError("");
		setOutput("");
		setNotice("");
		try {
			const payload = await call({
				action: "discuss",
				projectRoot: pathInput,
				when
			});
			if (!payload.ok) {
				setError(String(payload.message || "拿不到讨论上下文"));
				return;
			}
			const context = String(payload.data?.text || "");
			const placed = await ensureDedicatedWorkspace(hostCtx, pathInput);
			const failure = await openNativeDiscussion(hostCtx, context, pathInput, {
				workspaceId: placed.workspaceId,
				title: sessionTitle(when, goal)
			});
			if (!failure) {
				setNotice(placed.note ? "已在原生会话里打开讨论（" + placed.note + "）。" : "已在「" + WORKSPACE_TITLE + "」工作区打开讨论，并把这道题的上下文预填好了。");
				return;
			}
			setNotice("原生会话不可用（" + failure + "），已降级到面板内讨论。");
			const answer = await call({
				action: "chat",
				projectRoot: pathInput,
				when,
				message: context
			});
			if (!answer.ok) setError(String(answer.message || "降级讨论也失败了"));
			else setOutput(String(answer.output || ""));
		} catch (cause) {
			setError("讨论失败：" + String(cause.message || cause));
		} finally {
			setBusy(false);
		}
	}, [hostCtx, pathInput]);
	const summary = profile ? Object.entries(profile.counts).map(([k, v]) => k + " " + v).join(" ｜ ") : "";
	return react.createElement("div", {
		style: PANEL,
		className: "dsh-learning-panel"
	}, react.createElement("div", { style: ROW }, react.createElement("button", {
		type: "button",
		style: {
			...BTN,
			cursor: "pointer"
		},
		"aria-expanded": open,
		onClick: () => setOpen((value) => !value)
	}, "学习" + (open ? " ▾" : " ▸")), profile ? react.createElement("span", { style: MUTED }, summary) : null, busy ? react.createElement("span", { style: MUTED }, "执行中…") : null), open ? react.createElement("div", null, react.createElement("div", { style: H }, "项目路径"), react.createElement("div", { style: ROW }, react.createElement("input", {
		style: INPUT,
		value: pathInput,
		placeholder: "留空则自动探测（往上有 README.md 的目录）",
		onChange: (event) => setPathInput(event.target.value)
	}), react.createElement("button", {
		style: BTN,
		onClick: () => void load(pathInput)
	}, "重新读取")), root ? react.createElement("div", { style: MUTED }, "当前项目：" + root) : null, react.createElement("div", { style: H }, "知识画像"), profile && profile.total ? react.createElement("ul", { style: {
		margin: "4px 0 0 1.1rem",
		padding: 0
	} }, profile.points.slice(0, 12).map((point, index) => react.createElement("li", { key: point.name + index }, "[" + point.level + "] " + point.name))) : react.createElement("div", { style: MUTED }, "还没有画像数据"), react.createElement("div", { style: H }, "任务"), tasks.length ? react.createElement("ul", { style: {
		margin: "4px 0 0 1.1rem",
		padding: 0
	} }, tasks.slice(-5).reverse().map((task) => react.createElement("li", { key: task.when }, (task.isReview ? "【复习】" : "") + task.when + "　" + task.goal, " ", react.createElement("button", {
		type: "button",
		style: {
			...BTN,
			marginLeft: "6px"
		},
		disabled: busy,
		onClick: () => void discuss(task.when, task.goal)
	}, "讨论")))) : react.createElement("div", { style: MUTED }, "还没有任务记录"), react.createElement("div", { style: H }, "知识地图"), books.length ? react.createElement("ul", { style: {
		margin: "4px 0 0 1.1rem",
		padding: 0
	} }, books.slice(0, 8).map((book) => react.createElement("li", { key: book.book }, book.book + "（" + book.chapters + " 章 / " + book.points + " 点）"))) : react.createElement("div", { style: MUTED }, "还没有知识地图"), react.createElement("div", { style: H }, "操作"), react.createElement("div", { style: ROW }, react.createElement("input", {
		style: INPUT,
		value: doc,
		placeholder: "飞书文档 ID 或 wiki 链接",
		onChange: (event) => setDoc(event.target.value)
	}), react.createElement("button", {
		style: BTN,
		disabled: busy,
		onClick: () => void run("sync", { doc })
	}, "同步并提炼"), react.createElement("button", {
		style: BTN,
		disabled: busy,
		onClick: () => void run("next")
	}, "出题")), react.createElement("div", { style: {
		...ROW,
		marginTop: "6px"
	} }, react.createElement("input", {
		style: INPUT,
		value: doneName,
		placeholder: "知识点名称",
		onChange: (event) => setDoneName(event.target.value)
	}), react.createElement("input", {
		style: INPUT,
		value: donePath,
		placeholder: "产出路径",
		onChange: (event) => setDonePath(event.target.value)
	}), react.createElement("button", {
		style: BTN,
		disabled: busy,
		onClick: () => void run("done", {
			name: doneName,
			path: donePath
		})
	}, "回写")), notice ? react.createElement("div", { style: OUT }, notice) : null, error ? react.createElement("div", { style: ERR }, error) : null, output ? react.createElement("div", { style: OUT }, output) : null) : null);
}
function apply(ctx) {
	for (const slot of SLOTS) ctx.slots.inject(slot, () => ctx.slots.register({
		name: slot,
		id: "learning-navigator",
		order: 60
	}, () => react.createElement(LearningPanel, { ctx })));
}

//#endregion
exports.LearningPanel = LearningPanel;
exports.SLOT = SLOT;
exports.SLOTS = SLOTS;
exports.WORKSPACE_TITLE = WORKSPACE_TITLE;
exports.apply = apply;
exports.inject = inject;
exports.sessionTitle = sessionTitle;

    return module.exports;
  }
});
//# sourceMappingURL=client.js.map