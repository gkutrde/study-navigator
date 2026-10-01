import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";

//#region src/server/learning.ts
const ROUTE = "/api/learning";
/** Python 解释器：允许环境变量或插件配置覆盖（不同机器路径不同）。 */
function pythonExecutable(configured) {
	const value = String(configured ?? process.env.LEARNING_PYTHON ?? "").trim();
	if (value) return value;
	return process.platform === "win32" ? "python" : "python3";
}
function jsonResponse(status, payload) {
	return new Response(JSON.stringify(payload), {
		status,
		headers: { "content-type": "application/json; charset=utf-8" }
	});
}
/**
* 在宿主上注册面板路由。
*
* 用**公开接缝** ctx.connection.fetch.register：精确 Fetch 路由，挂在 /api 的
* 认证栅栏之后。拿不到这个接缝就明确告警并退出——**绝不绕过鉴权**。
*/
function registerLearningRoute(ctx, config = {}) {
	const register = ctx?.connection?.fetch?.register;
	if (typeof register !== "function") {
		if (typeof ctx?.logger?.warn === "function") ctx.logger.warn("[学习领航员] 宿主没有 connection.fetch 接缝，面板功能不可用（不降级绕过鉴权）");
		return null;
	}
	return register({
		path: ROUTE,
		methods: ["GET", "POST"],
		requestBody: "buffered",
		fetch: async (request) => {
			let body = {};
			if (String(request.method).toUpperCase() === "POST") try {
				body = await request.json();
			} catch {
				return jsonResponse(400, {
					ok: false,
					message: "请求体不是合法 JSON"
				});
			}
			if (body === null || typeof body !== "object" || Array.isArray(body)) return jsonResponse(400, {
				ok: false,
				message: "请求体必须是对象"
			});
			const root = resolveProjectRoot(String(body.projectRoot ?? config.projectRoot ?? "").trim() || void 0, process.cwd());
			const result = await handleLearning(body, {
				root,
				python: pythonExecutable(config.python)
			});
			return jsonResponse(result.status, {
				...result.payload,
				projectRoot: root
			});
		}
	});
}
/** 允许的动作。**白名单**：客户端只能报这些名字，服务端不接受任何命令字符串。 */
const ACTIONS = {
	capabilities: { cli: null },
	profile: { cli: null },
	tasks: { cli: null },
	syllabus: { cli: null },
	sync: { cli: ["sync"] },
	next: { cli: ["next"] },
	done: { cli: ["done"] },
	discuss: { cli: null },
	chat: { cli: ["chat"] }
};
/** CLI 子命令白名单（第二道闸：即使 ACTIONS 被改了，也只放行这些）。 */
const CLI_SUBCOMMANDS = [
	"sync",
	"distill",
	"next",
	"done",
	"chat"
];
/** 单次 CLI 调用的墙钟上限（出题要真调模型，给足）。 */
const CLI_TIMEOUT_MS = 600 * 1e3;
/**
* 解析项目根目录。
* 优先用配置里的值；否则从 profile/ 往上找 README.md 认根（和看板同一个策略）。
*/
function resolveProjectRoot(configured, fallback) {
	if (configured && String(configured).trim()) {
		const value = String(configured).trim();
		return isAbsolute(value) ? resolve(value) : resolve(fallback || process.cwd(), value);
	}
	let current = resolve(fallback || process.cwd());
	for (let i = 0; i < 6; i += 1) {
		if (existsSync(join(current, "README.md"))) return current;
		const parent = dirname(current);
		if (parent === current) break;
		current = parent;
	}
	return resolve(fallback || process.cwd());
}
function readText(path) {
	try {
		return readFileSync(path, "utf8");
	} catch {
		return "";
	}
}
/** 画像概要：按四态统计 + 按主题分组的知识点。 */
function readProfile(root) {
	const text = readText(join(root, "profile", "knowledge.md"));
	const counts = {
		学过: 0,
		做过: 0,
		输出: 0,
		存疑: 0
	};
	const points = [];
	let topic = "";
	for (const line of text.split(/\r?\n/)) {
		const head = /^##\s+(.+)$/.exec(line);
		if (head) {
			topic = head[1].trim() === "统计" ? "" : head[1].trim();
			continue;
		}
		const hit = /^\s*-\s*\[([^\]]+)\]\s*(.+?)\s*$/.exec(line);
		if (!hit) continue;
		const level = hit[1].trim();
		if (!(level in counts)) continue;
		counts[level] += 1;
		const name$1 = hit[2].split("—")[0].replace(/（[^（）]*）\s*$/, "").trim();
		if (name$1) points.push({
			name: name$1,
			level,
			topic
		});
	}
	return {
		counts,
		points,
		total: points.length
	};
}
/** 任务列表：时间戳 + 目标 + 是否复习题 + 最近一次点评。 */
function readTasks(root) {
	return readText(join(root, "profile", "tasks.md")).split(/^##\s+(?=\d{4}-\d{2}-\d{2})/m).slice(1).map((block) => {
		const when = (block.split(/\r?\n/)[0] || "").trim();
		const goal = (/(?:^|\n)\*\*目标\*\*：(.+)/.exec(block)?.[1] || "").trim();
		return {
			when,
			goal,
			acceptance: (/(?:^|\n)\*\*验收方式\*\*：(.+)/.exec(block)?.[1] || "").trim(),
			isReview: block.includes("**复习**") || goal.startsWith("复习")
		};
	});
}
/**
* 读某道任务的接力上下文（handoff），给「讨论」按钮预填用。
*
* 服务端**不创建会话**：那要由客户端用宿主的公开会话接缝做（T-040）。
* 这里只负责把本地文件如实交付出去。
*/
function readHandoff(root, when) {
	const stamp = String(when ?? "").trim();
	if (!stamp) return null;
	const id = stamp.replace(/[^0-9]/g, "").slice(0, 12);
	if (!id) return null;
	const direct = join(root, "profile", "handoff", stamp.slice(0, 10) + "-" + id.slice(8, 12) + ".md");
	const text = readText(direct);
	if (text) return {
		path: direct,
		text
	};
	return null;
}
/** 这条面板链路的**能力自述**：客户端据此决定走原生还是降级。 */
function capabilities() {
	return {
		handoff: true,
		cli: true,
		session: "client"
	};
}
/** 知识地图概要：书 → 章节数 + 点位数。 */
function readSyllabus(root) {
	const text = readText(join(root, "profile", "syllabus.md"));
	const books = [];
	let current = null;
	for (const line of text.split(/\r?\n/)) {
		const head = /^##\s+(.+)$/.exec(line);
		if (head) {
			current = {
				book: head[1].trim(),
				chapters: 0,
				points: 0
			};
			books.push(current);
			continue;
		}
		if (!current) continue;
		if (/^###\s+/.test(line)) current.chapters += 1;
		else if (/^\s*-\s+\S/.test(line)) current.points += 1;
	}
	return books;
}
/**
* 跑一次 CLI。
*
* 安全：spawn + 参数数组 + **shell: false**。用户给的值只作为数组元素传入，
* 永远不会被拼进命令字符串，所以分号/反引号/管道都只是普通字符。
*/
function runCli(root, args, python) {
	const command = [
		python,
		"-m",
		"src.cli",
		...args
	];
	return new Promise((done) => {
		let child;
		try {
			child = spawn(command[0], command.slice(1), {
				cwd: root,
				shell: false,
				windowsHide: true,
				env: {
					...process.env,
					PYTHONIOENCODING: "utf-8",
					PYTHONUTF8: "1"
				}
			});
		} catch (cause) {
			done({
				ok: false,
				output: "启动 CLI 失败：" + String(cause)
			});
			return;
		}
		let out = "";
		let err = "";
		const timer = setTimeout(() => {
			try {
				child.kill();
			} catch {}
			done({
				ok: false,
				output: "CLI 超时（超过 " + Math.round(CLI_TIMEOUT_MS / 6e4) + " 分钟）：出题要真调模型，可以稍后重试。"
			});
		}, CLI_TIMEOUT_MS);
		child.stdout?.on("data", (chunk) => {
			out += String(chunk);
		});
		child.stderr?.on("data", (chunk) => {
			err += String(chunk);
		});
		child.on("error", (cause) => {
			clearTimeout(timer);
			done({
				ok: false,
				output: "没找到 Python：" + String(cause.message || cause)
			});
		});
		child.on("close", (code) => {
			clearTimeout(timer);
			const text = (out + (err ? "\n" + err : "")).trim();
			if (code === 0) done({
				ok: true,
				output: text
			});
			else done({
				ok: false,
				output: "CLI 执行失败（退出码 " + code + "）：" + (text || "没有更多信息")
			});
		});
	});
}
/** 把动作 × 参数翻译成 CLI 参数数组（白名单之外一律拒绝）。 */
function buildCliArgs(action, params) {
	const spec = ACTIONS[action];
	if (!spec) throw new Error("未知动作：" + action);
	if (!spec.cli) throw new Error("动作 " + action + " 不需要跑 CLI");
	const [sub] = spec.cli;
	if (!CLI_SUBCOMMANDS.includes(sub)) throw new Error("子命令不在白名单：" + sub);
	const args = [sub];
	const doc = String(params.doc ?? "").trim();
	const name$1 = String(params.name ?? "").trim();
	const path = String(params.path ?? "").trim();
	const recite = String(params.recite ?? "").trim();
	if (action === "sync") {
		if (!doc) throw new Error("同步需要文档 ID 或 wiki 链接");
		args.push(doc);
		return args;
	}
	if (action === "next") return args;
	if (action === "chat") {
		const when = String(params.when ?? "").trim();
		const message = String(params.message ?? "").trim();
		if (!when) throw new Error("讨论需要任务时间戳");
		if (!message) throw new Error("讨论需要内容");
		args.push(when);
		args.push(message.slice(0, 4e3));
		return args;
	}
	if (action === "done") {
		if (!name$1) throw new Error("回写需要知识点名称");
		if (!path) throw new Error("回写需要产出路径");
		args.push(name$1, path);
		if (recite) args.push("--recite", recite);
		return args;
	}
	return args;
}
/** 处理一次面板请求（纯函数，便于单测；不依赖宿主）。 */
async function handleLearning(body, options) {
	const action = String(body.action ?? "").trim();
	if (!(action in ACTIONS)) return {
		status: 400,
		payload: {
			ok: false,
			message: "未知动作：" + (action || "(空)")
		}
	};
	const root = options.root;
	if (!existsSync(join(root, "profile"))) return {
		status: 400,
		payload: {
			ok: false,
			message: "找不到项目：" + root + " 下没有 profile/ 目录（可在面板里改项目路径）"
		}
	};
	if (action === "capabilities") return {
		status: 200,
		payload: {
			ok: true,
			data: capabilities()
		}
	};
	if (action === "profile") return {
		status: 200,
		payload: {
			ok: true,
			data: readProfile(root),
			capabilities: capabilities()
		}
	};
	if (action === "discuss") {
		const handoff = readHandoff(root, String(body.when ?? ""));
		if (!handoff) return {
			status: 400,
			payload: {
				ok: false,
				message: "读不到这道题的接力上下文：请先点「在 DSH 中继续」生成 handoff"
			}
		};
		return {
			status: 200,
			payload: {
				ok: true,
				data: handoff,
				capabilities: capabilities()
			}
		};
	}
	if (action === "tasks") return {
		status: 200,
		payload: {
			ok: true,
			data: readTasks(root)
		}
	};
	if (action === "syllabus") return {
		status: 200,
		payload: {
			ok: true,
			data: readSyllabus(root)
		}
	};
	let args;
	try {
		args = buildCliArgs(action, body);
	} catch (cause) {
		return {
			status: 400,
			payload: {
				ok: false,
				message: String(cause.message || cause)
			}
		};
	}
	const result = await runCli(root, args, options.python);
	if (!result.ok) return {
		status: 200,
		payload: {
			ok: false,
			message: result.output
		}
	};
	const after = {
		profile: readProfile(root),
		tasks: readTasks(root)
	};
	return {
		status: 200,
		payload: {
			ok: true,
			output: result.output,
			data: after
		}
	};
}

//#endregion
//#region src/index.ts
const name = "dsh-learning-navigator";
/** 只声明确定存在的公开接缝（客户端那半边是 ['slots']）。 */
const inject = ["connection"];
function apply(ctx, rowConfig = {}) {
	if (registerLearningRoute(ctx, rowConfig ?? {}) && typeof ctx.logger?.info === "function") ctx.logger.info("[学习领航员] 已注册 " + ROUTE + "（面板通道就绪）");
}

//#endregion
export { apply, inject, name };
//# sourceMappingURL=index.js.map