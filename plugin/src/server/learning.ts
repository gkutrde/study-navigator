/**
 * 学习领航员 · 服务端（Node 半边）。
 *
 * 三件事：
 *   1. 工作区过滤（T-050）：只接受来自「学习领航员」工作区的请求——
 *      客户端带上当前工作区 id，这里到宿主的工作区注册表（ctx.workspaceRegistry）核验标题；
 *   2. 读本地 Python 核心写的文件（profile/ 下的画像、任务、地图）；
 *   3. 需要动作时，经**白名单**跑 python -m src.cli（spawn + shell:false）。
 *
 * 通道：ctx.connection 的**精确 Fetch 路由**（宿主公开接缝）。
 * 这条路由挂在认证栅栏之后（宿主先做 Host/Origin 校验与浏览器鉴权），浏览器同源 POST 即可，
 * 不需要绕过任何鉴权。
 */
import { spawn } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, isAbsolute, join, resolve } from 'node:path'

import { WORKSPACE_TITLE, errorText } from '../shared.ts'
import type { BookData, LearningPayload, ProfileData, TaskData } from '../shared.ts'

export const ROUTE = '/api/learning'

/** 一次请求的处理结果：HTTP 状态码 + JSON 回包。 */
export type Reply = { status: number; payload: LearningPayload }

function ok(fields: Omit<LearningPayload, 'ok'> = {}): Reply {
  return { status: 200, payload: { ok: true, ...fields } }
}

function fail(status: number, message: string): Reply {
  return { status, payload: { ok: false, message } }
}

/** Python 解释器：允许环境变量或插件配置覆盖（不同机器路径不同）。 */
export function pythonExecutable(configured?: string): string {
  const value = String(configured ?? process.env.LEARNING_PYTHON ?? '').trim()
  if (value) return value
  return process.platform === 'win32' ? 'python' : 'python3'
}

function jsonResponse(status: number, payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8' },
  })
}

// ---------------------------------------------------------------- 工作区过滤（T-050）

/** 宿主工作区注册表（ctx.workspaceRegistry）里本插件用到的那一小片：按 id 取工作区。 */
type WorkspaceRegistryLike = {
  get(id: string): { path: string; title: string } | undefined
}

export type WorkspaceCheck =
  | { ok: true; workspaceId: string; path: string }
  | { ok: false; status: number; message: string }

/**
 * 核验请求是否来自「学习领航员」工作区。
 *
 * 客户端只报**工作区 id**；标题与目录以宿主注册表为准（不信客户端自报的标题）。
 * 拿不到注册表接缝就**拒绝**（失败即关闭）：宁可面板不可用，也不在别的工作区里放行。
 */
export function checkWorkspace(registry: unknown, workspaceId: unknown): WorkspaceCheck {
  const source = registry as Partial<WorkspaceRegistryLike> | null | undefined
  if (!source || typeof source.get !== 'function') {
    return {
      ok: false,
      status: 503,
      message: '宿主没有工作区注册表接缝（workspaceRegistry），无法确认请求来自「' + WORKSPACE_TITLE + '」工作区，面板不可用',
    }
  }
  const id = String(workspaceId ?? '').trim()
  if (!id) {
    return { ok: false, status: 403, message: '学习面板只在「' + WORKSPACE_TITLE + '」工作区启用：请求没有带工作区' }
  }
  let workspace: { path: string; title: string } | undefined
  try {
    workspace = source.get(id)
  } catch {
    workspace = undefined
  }
  if (!workspace) {
    return { ok: false, status: 403, message: '学习面板只在「' + WORKSPACE_TITLE + '」工作区启用：找不到工作区 ' + id }
  }
  const title = String(workspace.title ?? '')
  if (title !== WORKSPACE_TITLE) {
    return {
      ok: false,
      status: 403,
      message: '学习面板只在「' + WORKSPACE_TITLE + '」工作区启用（当前工作区：' + (title || id) + '）',
    }
  }
  return { ok: true, workspaceId: id, path: String(workspace.path ?? '') }
}

/**
 * 一次面板请求的完整处理：工作区过滤 → 定项目根 → 分派动作。
 *
 * 与宿主无关（注册表从参数传入），契约测试直接调它。
 */
export async function serveLearning(
  body: Record<string, unknown>,
  deps: { registry: unknown; config?: Record<string, unknown>; cwd?: string },
): Promise<Reply> {
  const gate = checkWorkspace(deps.registry, body.workspaceId)
  if (!gate.ok) return fail(gate.status, gate.message)

  // 没手填项目路径时，项目根就是「学习领航员」工作区的目录（T-046 正是把项目目录登记成了这个工作区）
  const configured = String(body.projectRoot ?? deps.config?.projectRoot ?? '').trim()
  const root = resolveProjectRoot(configured || gate.path || undefined, deps.cwd ?? process.cwd())
  const result = await handleLearning(body, {
    root,
    python: pythonExecutable(deps.config?.python as string | undefined),
  })
  return { status: result.status, payload: { ...result.payload, projectRoot: root } }
}

/** 宿主注入了 workspaceRegistry 才读得到；没声明 / 没有时 cordis 会抛错，这里统一当"没有"。 */
function workspaceRegistryOf(ctx: any): unknown {
  try {
    return ctx?.workspaceRegistry
  } catch {
    return undefined
  }
}

/**
 * 在宿主上注册面板路由。
 *
 * 用**公开接缝** ctx.connection.fetch.register：精确 Fetch 路由，挂在 /api 的
 * 认证栅栏之后。拿不到这个接缝就明确告警并退出——**绝不绕过鉴权**。
 */
export function registerLearningRoute(ctx: any, config: Record<string, unknown> = {}): (() => Promise<void>) | null {
  const register = ctx?.connection?.fetch?.register
  if (typeof register !== 'function') {
    if (typeof ctx?.logger?.warn === 'function') {
      ctx.logger.warn('[学习领航员] 宿主没有 connection.fetch 接缝，面板功能不可用（不降级绕过鉴权）')
    }
    return null
  }
  return register({
    path: ROUTE,
    methods: ['GET', 'POST'],
    requestBody: 'buffered',
    fetch: async (request: Request): Promise<Response> => {
      let body: unknown = {}
      if (String(request.method).toUpperCase() === 'POST') {
        try {
          body = await request.json()
        } catch {
          return jsonResponse(400, { ok: false, message: '请求体不是合法 JSON' })
        }
      }
      if (body === null || typeof body !== 'object' || Array.isArray(body)) {
        return jsonResponse(400, { ok: false, message: '请求体必须是对象' })
      }
      const result = await serveLearning(body as Record<string, unknown>, {
        registry: workspaceRegistryOf(ctx),
        config,
      })
      return jsonResponse(result.status, result.payload)
    },
  })
}

// ---------------------------------------------------------------- 动作白名单

/** 允许的动作。**白名单**：客户端只能报这些名字，服务端不接受任何命令字符串。 */
export const ACTIONS = {
  // capabilities 是只读自述，不进按钮白名单
  capabilities: { cli: null },
  profile: { cli: null },
  tasks: { cli: null },
  syllabus: { cli: null },
  sync: { cli: ['sync'] },
  next: { cli: ['next'] },
  done: { cli: ['done'] },
  // T-040：讨论——只交付 handoff 上下文，会话由**客户端用宿主接缝**原生创建
  discuss: { cli: null },
  // T-040 降级：拿不到会话接缝时，用 headless 单次问答顶上（走 chat 子命令）
  chat: { cli: ['chat'] },
}

/** CLI 子命令白名单（第二道闸：即使 ACTIONS 被改了，也只放行这些）。 */
const CLI_SUBCOMMANDS = ['sync', 'distill', 'next', 'done', 'chat']

/** 单次 CLI 调用的墙钟上限（出题要真调模型，给足）。 */
const CLI_TIMEOUT_MS = 10 * 60 * 1000

/** 降级讨论时送进 chat 的内容上限（与 Python 侧 prompt 上限同一数量级，防止超长参数）。 */
const MAX_CHAT_MESSAGE_CHARS = 4000

// ---------------------------------------------------------------- 项目根

/**
 * 项目根的标志：既有 profile/（面板要读的数据），又有 src/cli.py（动作要跑的 CLI）。
 * 以前只认 README.md——plugin/ 自己也有 README.md，从插件目录往上找会停在插件目录。
 */
function isProjectRoot(directory: string): boolean {
  return existsSync(join(directory, 'profile')) && existsSync(join(directory, 'src', 'cli.py'))
}

/**
 * 解析项目根目录。
 * 优先用配置里的值（相对路径相对 fallback）；否则从 fallback 往上找项目根标志。
 */
export function resolveProjectRoot(configured?: string, fallback?: string): string {
  const base = resolve(fallback || process.cwd())
  const value = String(configured ?? '').trim()
  if (value) return isAbsolute(value) ? resolve(value) : resolve(base, value)
  let current = base
  for (let i = 0; i < 6; i += 1) {
    if (isProjectRoot(current)) return current
    const parent = dirname(current)
    if (parent === current) break
    current = parent
  }
  return base
}

function readText(path: string): string {
  try {
    return readFileSync(path, 'utf8')
  } catch {
    return ''
  }
}

// ---------------------------------------------------------------- 只读数据

/** 画像概要：按四态统计 + 按主题分组的知识点。 */
export function readProfile(root: string): ProfileData {
  const text = readText(join(root, 'profile', 'knowledge.md'))
  const counts: Record<string, number> = { 学过: 0, 做过: 0, 输出: 0, 存疑: 0 }
  const points: ProfileData['points'] = []
  let topic = ''
  for (const line of text.split(/\r?\n/)) {
    const head = /^##\s+(.+)$/.exec(line)
    if (head) {
      topic = head[1].trim() === '统计' ? '' : head[1].trim()
      continue
    }
    const hit = /^\s*-\s*\[([^\]]+)\]\s*(.+?)\s*$/.exec(line)
    if (!hit) continue
    const level = hit[1].trim()
    if (!(level in counts)) continue
    counts[level] += 1
    const name = hit[2].split('—')[0].replace(/（[^（）]*）\s*$/, '').trim()
    if (name) points.push({ name, level, topic })
  }
  return { counts, points, total: points.length }
}

/** 任务列表：时间戳 + 目标 + 是否复习题。 */
export function readTasks(root: string): TaskData[] {
  const text = readText(join(root, 'profile', 'tasks.md'))
  const blocks = text.split(/^##\s+(?=\d{4}-\d{2}-\d{2})/m).slice(1)
  return blocks.map((block) => {
    const when = (block.split(/\r?\n/)[0] || '').trim()
    const goal = (/(?:^|\n)\*\*目标\*\*：(.+)/.exec(block)?.[1] || '').trim()
    const acceptance = (/(?:^|\n)\*\*验收方式\*\*：(.+)/.exec(block)?.[1] || '').trim()
    return {
      when,
      goal,
      acceptance,
      isReview: block.includes('**复习**') || goal.startsWith('复习'),
    }
  })
}

/**
 * 任务时间戳 → handoff 文件名里的任务 id。
 *
 * 与 Python 的 handoff.task_file_id 同一规则（那边是唯一权威）：去掉冒号，其余不安全字符压成 "-"，
 * 首尾的 - . _ 去掉。"2026-09-27 10:30" → "2026-09-27-1030"。
 * 路径分隔符、.. 都会被压掉，拼不出 handoff 目录以外的路径。
 */
export function taskFileId(when: string): string {
  return String(when ?? '')
    .trim()
    .replace(/[:：]/g, '')
    .replace(/[^\w\u4e00-\u9fff.-]+/g, '-')
    .replace(/^[-._]+|[-._]+$/g, '')
}

/**
 * 读某道任务的接力上下文（handoff），给「讨论」按钮预填用。
 *
 * 服务端**不创建会话**：那要由客户端用宿主的公开会话接缝做（T-040）。
 * 这里只负责把本地文件如实交付出去。
 */
export function readHandoff(root: string, when: string) {
  const id = taskFileId(when)
  if (!id) return null
  const path = join(root, 'profile', 'handoff', id + '.md')
  const text = readText(path)
  return text ? { path, text } : null
}

/** 这条面板链路的**能力自述**：客户端据此决定走原生还是降级。 */
export function capabilities() {
  return {
    // 会话由客户端接缝创建，服务端无从得知；这里只说本服务端能做什么
    handoff: true,
    cli: true,
    session: 'client',
  }
}

/** 知识地图概要：书 → 章节数 + 点位数。 */
export function readSyllabus(root: string): BookData[] {
  const text = readText(join(root, 'profile', 'syllabus.md'))
  const books: BookData[] = []
  let current: BookData | null = null
  for (const line of text.split(/\r?\n/)) {
    const head = /^##\s+(.+)$/.exec(line)
    if (head) {
      current = { book: head[1].trim(), chapters: 0, points: 0 }
      books.push(current)
      continue
    }
    if (!current) continue
    if (/^###\s+/.test(line)) current.chapters += 1
    else if (/^\s*-\s+\S/.test(line)) current.points += 1
  }
  return books
}

// ---------------------------------------------------------------- 跑 CLI

/**
 * 跑一次 CLI。
 *
 * 安全：spawn + 参数数组 + **shell: false**。用户给的值只作为数组元素传入，
 * 永远不会被拼进命令字符串，所以分号/反引号/管道都只是普通字符。
 * 失败一律变成中文说明（非零退出带上 stderr 摘要），不把堆栈抛给面板。
 */
export function runCli(root: string, args: string[], python: string): Promise<{ ok: boolean; output: string }> {
  return new Promise((done) => {
    let settled = false
    const finish = (result: { ok: boolean; output: string }) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      done(result)
    }
    let child: ReturnType<typeof spawn>
    try {
      child = spawn(python, ['-m', 'src.cli', ...args], {
        cwd: root,
        shell: false,
        windowsHide: true,
        env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
      })
    } catch (cause) {
      done({ ok: false, output: '启动 CLI 失败：' + errorText(cause) })
      return
    }
    let out = ''
    let err = ''
    const timer = setTimeout(() => {
      try {
        child.kill()
      } catch {
        /* 进程可能已经退出 */
      }
      finish({
        ok: false,
        output: 'CLI 超时（超过 ' + Math.round(CLI_TIMEOUT_MS / 60000) + ' 分钟）：出题要真调模型，可以稍后重试。',
      })
    }, CLI_TIMEOUT_MS)
    child.stdout?.on('data', (chunk) => {
      out += String(chunk)
    })
    child.stderr?.on('data', (chunk) => {
      err += String(chunk)
    })
    child.on('error', (cause) => finish({ ok: false, output: '没找到 Python：' + errorText(cause) }))
    child.on('close', (code) => {
      const text = (out + (err ? '\n' + err : '')).trim()
      if (code === 0) finish({ ok: true, output: text })
      else finish({ ok: false, output: 'CLI 执行失败（退出码 ' + code + '）：' + (text || '没有更多信息') })
    })
  })
}

/** 取一个必填参数（去首尾空白）；缺了抛中文错误。 */
function requireParam(params: Record<string, unknown>, key: string, message: string): string {
  const value = String(params[key] ?? '').trim()
  if (!value) throw new Error(message)
  return value
}

/** 把动作 × 参数翻译成 CLI 参数数组（白名单之外一律拒绝）。 */
export function buildCliArgs(action: string, params: Record<string, unknown>): string[] {
  const spec = (ACTIONS as Record<string, { cli: string[] | null }>)[action]
  if (!spec) throw new Error('未知动作：' + action)
  if (!spec.cli) throw new Error('动作 ' + action + ' 不需要跑 CLI')
  const [sub] = spec.cli
  if (!CLI_SUBCOMMANDS.includes(sub)) throw new Error('子命令不在白名单：' + sub)

  if (action === 'sync') return [sub, requireParam(params, 'doc', '同步需要文档 ID 或 wiki 链接')]
  if (action === 'chat') {
    // 降级讨论：chat <时间戳> "<问题>"；两段都作为独立参数，不拼字符串
    const when = requireParam(params, 'when', '讨论需要任务时间戳')
    const message = requireParam(params, 'message', '讨论需要内容')
    return [sub, when, message.slice(0, MAX_CHAT_MESSAGE_CHARS)]
  }
  if (action === 'done') {
    const name = requireParam(params, 'name', '回写需要知识点名称')
    const path = requireParam(params, 'path', '回写需要产出路径')
    const recite = String(params.recite ?? '').trim()
    return recite ? [sub, name, path, '--recite', recite] : [sub, name, path]
  }
  return [sub]
}

// ---------------------------------------------------------------- 分派

/** 只读动作：不跑 CLI，直接读 profile/ 下的文件。 */
const READERS: Record<string, (root: string, body: Record<string, unknown>) => Reply> = {
  capabilities: () => ok({ data: capabilities() }),
  profile: (root) => ok({ data: readProfile(root), capabilities: capabilities() }),
  tasks: (root) => ok({ data: readTasks(root) }),
  syllabus: (root) => ok({ data: readSyllabus(root) }),
  discuss: (root, body) => {
    const handoff = readHandoff(root, String(body.when ?? ''))
    if (!handoff) return fail(400, '读不到这道题的接力上下文：请先点「在 DSH 中继续」生成 handoff')
    return ok({ data: handoff, capabilities: capabilities() })
  },
}

/** 处理一次面板请求（纯函数，便于单测；不依赖宿主，也不做工作区过滤——那在 serveLearning）。 */
export async function handleLearning(
  body: Record<string, unknown>,
  options: { root: string; python: string },
): Promise<Reply> {
  const action = String(body.action ?? '').trim()
  if (!(action in ACTIONS)) return fail(400, '未知动作：' + (action || '(空)'))

  const root = options.root
  if (!existsSync(join(root, 'profile'))) {
    return fail(400, '找不到项目：' + root + ' 下没有 profile/ 目录（可在面板里改项目路径）')
  }

  const reader = READERS[action]
  if (reader) return reader(root, body)

  let args: string[]
  try {
    args = buildCliArgs(action, body)
  } catch (cause) {
    return fail(400, errorText(cause))
  }
  const result = await runCli(root, args, options.python)
  // CLI 失败也回 200：这是"动作执行了但没成功"，面板原地显示中文原因
  if (!result.ok) return fail(200, result.output)
  return ok({ output: result.output, data: { profile: readProfile(root), tasks: readTasks(root) } })
}
