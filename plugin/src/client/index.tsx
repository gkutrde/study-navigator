/**
 * 学习领航员 · 界面半边（浏览器 bundle）。
 *
 * 只用宿主的公开接缝：ctx.slots.inject / ctx.slots.register。
 * 数据来自本插件自己的服务端路由 /api/learning（同源 POST，认证栅栏之后）。
 * 所有用户可见文本都是**中文**；失败在面板内原地显示。
 */
import * as React from 'react'

const { useCallback, useEffect, useState } = React

/** 面板挂在这个 slot 上（实测有效；备选见 README 接缝清单）。 */
export const SLOT = 'conversation.input.dock'
export const SLOTS = ['conversation.input.dock', 'conversation.session.header.actions'] as const

/**
 * 必须声明 inject（少了宿主会拒绝访问对应服务）。
 * - slots：挂面板；sessions：T-040 讨论要开原生会话。
 * 注意 sessions 若在当前宿主不存在，宿主会拒绝——所以取用时要 try 兜住并降级。
 */
export const inject = ['slots', 'sessions', 'workspaces']

const ROUTE = '/api/learning'

type ProfileData = {
  counts: Record<string, number>
  points: Array<{ name: string; level: string; topic: string }>
  total: number
}

type TaskData = { when: string; goal: string; acceptance: string; isReview: boolean }

type BookData = { book: string; chapters: number; points: number }

const PANEL: React.CSSProperties = {
  width: '100%',
  border: '1px solid var(--dsh-border, rgba(128,128,128,0.28))',
  borderRadius: '10px',
  padding: '10px 12px',
  font: 'inherit',
  fontSize: '12px',
  lineHeight: '1.55',
  textAlign: 'left',
}

const ROW: React.CSSProperties = { display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }
const BTN: React.CSSProperties = {
  padding: '3px 10px',
  borderRadius: '6px',
  border: '1px solid rgba(128,128,128,0.35)',
  background: 'transparent',
  color: 'inherit',
  font: 'inherit',
  cursor: 'pointer',
}
const INPUT: React.CSSProperties = { ...BTN, cursor: 'text', minWidth: '180px' }
const H: React.CSSProperties = { fontWeight: 600, marginTop: '8px' }
const MUTED: React.CSSProperties = { opacity: 0.7 }
const ERR: React.CSSProperties = { color: '#d64545', marginTop: '6px', whiteSpace: 'pre-wrap' }
const OUT: React.CSSProperties = { ...MUTED, marginTop: '6px', whiteSpace: 'pre-wrap', maxHeight: '8rem', overflow: 'auto' }

/** 专用工作区的名字（T-046）。 */
export const WORKSPACE_TITLE = '学习领航员'

/**
 * 会话标题：任务时间戳 + 任务目标前 20 字（T-046）。
 */
export function sessionTitle(when: string, goal: string): string {
  const stamp = String(when || '').trim()
  const text = String(goal || '').replace(/\s+/g, ' ').trim()
  const head = text.length > 20 ? text.slice(0, 20) + '…' : text
  if (stamp && head) return stamp + ' ' + head
  return stamp || head || '任务讨论'
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
async function ensureDedicatedWorkspace(
  ctx: any,
  cwd: string,
): Promise<{ workspaceId?: string; note: string }> {
  const workspaces = ctx?.workspaces
  if (!workspaces || typeof workspaces.create !== 'function') {
    return { note: '当前宿主没有工作区接缝，讨论会话会落在默认工作区' }
  }
  const path = String(cwd || '').trim()
  if (!path) {
    return { note: '还没配项目路径，讨论会话会落在默认工作区' }
  }

  try {
    // create 是幂等的：同一目录只会有一个工作区
    const view = await workspaces.create({ path })
    const workspaceId = view?.workspaceId
    if (!workspaceId) return { note: '工作区创建成功但没拿到 id，讨论会话会落在默认工作区' }

    // 只在标题确实不对时才改名——不能无条件 rename（那会改掉用户已有的名字）
    if (String(view.title || '') !== WORKSPACE_TITLE) {
      // 已经存在同名工作区时不抢名字（宿主会报 workspace/name-conflict）
      const taken = workspaceTaken(workspaces, workspaceId)
      if (!taken) {
        try {
          await workspaces.rename(workspaceId, WORKSPACE_TITLE)
        } catch {
          // 改名失败不影响归属：会话仍然建在这个工作区里
        }
      }
    }
    return { workspaceId, note: '' }
  } catch (cause) {
    return {
      note: '登记专用工作区失败（' + String((cause as Error).message || cause) + '），讨论会话会落在默认工作区',
    }
  }
}

/** 这个标题是否已被**别的**工作区占用。 */
function workspaceTaken(workspaces: any, selfId: string): boolean {
  try {
    const items = workspaces?.list?.getSnapshot?.()?.items || []
    return items.some(
      (item: any) =>
        String(item?.workspaceId) !== String(selfId) && String(item?.title || '') === WORKSPACE_TITLE,
    )
  } catch {
    return false
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
async function openNativeDiscussion(
  ctx: any,
  context: string,
  cwd: string,
  options: { workspaceId?: string; title?: string } = {},
): Promise<string | null> {
  const sessions = ctx?.sessions
  if (!sessions || typeof sessions.create !== 'function') return '当前宿主没有公开的会话接缝'
  try {
    // T-046：把会话建在**专用工作区**里（拿不到 workspaceId 时退回老行为）
    const payload: Record<string, unknown> = {}
    if (cwd) payload.cwd = cwd
    if (options.workspaceId) payload.workspaceId = options.workspaceId
    const id = await sessions.create(Object.keys(payload).length ? payload : undefined)
    if (typeof sessions.open === 'function') sessions.open(id)

    // T-046 实测（决定性的坑）：宿主**没有** sessions.get / sessions.session，
    // 所以老的 faceOf() 永远返回 null → 讨论直接降级。
    // 正确的链是：resolveAgentScope(id) 拿到 AgentContext，再 sessionOf(agentCtx) 拿到 Session 面
    // （契约见 dsh-api-session-controller/lib/types/client/sessions/service.d.ts）。
    const faceOf = () => {
      try {
        if (typeof sessions.resolveAgentScope === 'function' && typeof sessions.sessionOf === 'function') {
          const agentCtx = sessions.resolveAgentScope(id)
          const face = agentCtx ? sessions.sessionOf(agentCtx) : null
          if (face && typeof face.prompt === 'function') return face
        }
      } catch {
        // 落回下面的老路径
      }
      if (typeof sessions.get === 'function') return sessions.get(id)
      if (typeof sessions.session === 'function') return sessions.session(id)
      return null
    }

    // 关键：会话要**上线成当前会话**它的 scope 才会被 mint 出来。
    // open() 本身是同步调用，但 scope 是惰性 mint 的——所以要轮询等输入面就绪。
    // 实测踩过：立刻 prompt 会返回"看起来成功"但消息根本没进日志
    // （会话文件里只有 header，侧栏标题却拿到了那句话）。
    let face = faceOf()
    for (let i = 0; i < 40 && (!face || typeof face.prompt !== 'function'); i += 1) {
      await new Promise((done) => setTimeout(done, 250))
      face = faceOf()
    }
    if (!face || typeof face.prompt !== 'function') return '会话已创建，但拿不到它的输入面'

    // T-046：会话标题 = 任务时间戳 + 任务目标前 20 字
    if (options.title && typeof face.rename === 'function') {
      try {
        await face.rename(options.title)
        step('renamed ok')
      } catch (cause) {
        step('rename failed: ' + String((cause as Error).message || cause))
      }
    } else {
      step('rename skipped: title=' + Boolean(options.title) + ' fn=' + typeof face.rename)
    }

    for (let attempt = 0; attempt < 3; attempt += 1) {
      const result = await face.prompt([{ type: 'text', text: context }], 'queue')
      step('prompt#' + attempt + ' -> ' + (result && result.ok === true ? 'ok' : JSON.stringify(result).slice(0, 160)))
      if (result && result.ok === true) return null
      if (result && result.ok === false) {
        const detail = String(result.error?.message || result.error || '未知原因')
        // 刚切过去时偶发"还没就绪"，等一下再试，别直接把用户丢去降级
        if (attempt < 2 && /not|ready|pending|未|不能/i.test(detail)) {
          await new Promise((done) => setTimeout(done, 800))
          face = faceOf() || face
          continue
        }
        return '会话已创建，但预填失败：' + detail
      }
      return null
    }
    return '会话已创建，但预填没被接受（重试 3 次）'
  } catch (cause) {
    step('threw: ' + String((cause as Error).message || cause))
    return '开原生会话失败：' + String((cause as Error).message || cause)
  }
}

async function call(body: Record<string, unknown>): Promise<any> {
  const response = await fetch(ROUTE, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
  const payload = await response.json().catch(() => ({}))
  if (!payload || typeof payload !== 'object') return { ok: false, message: '面板接口返回了无法解析的内容' }
  return payload
}

/** 学习面板：画像 / 任务 / 知识地图 + 三个动作按钮 + 项目路径配置。 */
export function LearningPanel(props: { ctx?: any } = {}): React.ReactElement {
  const hostCtx = props?.ctx
  const [open, setOpen] = useState(false)
  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [tasks, setTasks] = useState<TaskData[]>([])
  const [books, setBooks] = useState<BookData[]>([])
  const [root, setRoot] = useState('')
  const [pathInput, setPathInput] = useState('')
  const [error, setError] = useState('')
  const [output, setOutput] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [doc, setDoc] = useState('')
  const [doneName, setDoneName] = useState('')
  const [donePath, setDonePath] = useState('')

  const load = useCallback(async (override?: string) => {
    setError('')
    try {
      const base = override ? { projectRoot: override } : {}
      const p = await call({ action: 'profile', ...base })
      if (!p.ok) { setError(String(p.message || '读画像失败')); return }
      setProfile(p.data.profile ?? p.data)
      if (p.projectRoot) { setRoot(p.projectRoot); setPathInput(p.projectRoot) }
      const t = await call({ action: 'tasks', ...base })
      if (t.ok) setTasks(Array.isArray(t.data) ? t.data : [])
      const s = await call({ action: 'syllabus', ...base })
      if (s.ok) setBooks(Array.isArray(s.data) ? s.data : [])
    } catch (cause) {
      setError('读项目失败：' + String((cause as Error).message || cause))
    }
  }, [])

  // 首次展开时读一次；之后靠「重新读取」按钮刷新（避免每次折叠都打三次请求）
  const [loadedOnce, setLoadedOnce] = useState(false)
  useEffect(() => {
    if (!open || loadedOnce) return
    setLoadedOnce(true)
    void load(pathInput || undefined)
  }, [open, loadedOnce, load, pathInput])

  const run = useCallback(
    async (action: string, extra: Record<string, unknown> = {}) => {
      setBusy(true)
      setError('')
      setOutput('')
      try {
        const payload = await call({ action, projectRoot: pathInput, ...extra })
        if (!payload.ok) setError(String(payload.message || '执行失败'))
        else {
          setOutput(String(payload.output || '完成'))
          if (payload.data) {
            if (payload.data.profile) setProfile(payload.data.profile)
            if (Array.isArray(payload.data.tasks)) setTasks(payload.data.tasks)
          }
        }
      } catch (cause) {
        setError('执行失败：' + String((cause as Error).message || cause))
      } finally {
        setBusy(false)
      }
    },
    [pathInput],
  )

  /**
   * 讨论：先试**原生会话**（把 handoff 预填进去，用户在原生会话里继续追问）；
   * 拿不到接缝就**降级**到面板内自渲染（调 headless），并明确告诉用户。
   */
  const discuss = useCallback(
    async (when: string, goal: string = '') => {
      setBusy(true)
      setError('')
      setOutput('')
      setNotice('')
      try {
        const payload = await call({ action: 'discuss', projectRoot: pathInput, when })
        if (!payload.ok) {
          setError(String(payload.message || '拿不到讨论上下文'))
          return
        }
        const context = String(payload.data?.text || '')

        // T-046：先把专用工作区准备好，再把会话建进去
        const placed = await ensureDedicatedWorkspace(hostCtx, pathInput)
        const failure = await openNativeDiscussion(hostCtx, context, pathInput, {
          workspaceId: placed.workspaceId,
          title: sessionTitle(when, goal),
        })
        if (!failure) {
          setNotice(
            placed.note
              ? '已在原生会话里打开讨论（' + placed.note + '）。'
              : '已在「' + WORKSPACE_TITLE + '」工作区打开讨论，并把这道题的上下文预填好了。',
          )
          return
        }
        setNotice('原生会话不可用（' + failure + '），已降级到面板内讨论。')
        const answer = await call({ action: 'chat', projectRoot: pathInput, when, message: context })
        if (!answer.ok) setError(String(answer.message || '降级讨论也失败了'))
        else setOutput(String(answer.output || ''))
      } catch (cause) {
        setError('讨论失败：' + String((cause as Error).message || cause))
      } finally {
        setBusy(false)
      }
    },
    [hostCtx, pathInput],
  )

  const summary = profile
    ? Object.entries(profile.counts).map(([k, v]) => k + ' ' + v).join(' ｜ ')
    : ''

  return React.createElement(
    'div',
    { style: PANEL, className: 'dsh-learning-panel' },
    React.createElement(
      'div',
      { style: ROW },
      // 必须是真正的 button：实测挂 onClick 的 span 在这个宿主里点不动
      // （没有原生点击语义，合成事件也捞不到）。附带好处是键盘可达。
      React.createElement(
        'button',
        {
          type: 'button',
          style: { ...BTN, cursor: 'pointer' },
          'aria-expanded': open,
          onClick: () => setOpen((value) => !value),
        },
        '学习' + (open ? ' ▾' : ' ▸'),
      ),
      profile ? React.createElement('span', { style: MUTED }, summary) : null,
      busy ? React.createElement('span', { style: MUTED }, '执行中…') : null,
    ),

    open
      ? React.createElement(
          'div',
          null,
          React.createElement('div', { style: H }, '项目路径'),
          React.createElement(
            'div',
            { style: ROW },
            React.createElement('input', {
              style: INPUT,
              value: pathInput,
              placeholder: '留空则自动探测（往上有 README.md 的目录）',
              onChange: (event: any) => setPathInput(event.target.value),
            }),
            React.createElement('button', { style: BTN, onClick: () => void load(pathInput) }, '重新读取'),
          ),
          root ? React.createElement('div', { style: MUTED }, '当前项目：' + root) : null,

          React.createElement('div', { style: H }, '知识画像'),
          profile && profile.total
            ? React.createElement(
                'ul',
                { style: { margin: '4px 0 0 1.1rem', padding: 0 } },
                profile.points.slice(0, 12).map((point, index) =>
                  React.createElement('li', { key: point.name + index }, '[' + point.level + '] ' + point.name),
                ),
              )
            : React.createElement('div', { style: MUTED }, '还没有画像数据'),

          React.createElement('div', { style: H }, '任务'),
          tasks.length
            ? React.createElement(
                'ul',
                { style: { margin: '4px 0 0 1.1rem', padding: 0 } },
                tasks.slice(-5).reverse().map((task) =>
                  React.createElement(
                    'li',
                    { key: task.when },
                    (task.isReview ? '【复习】' : '') + task.when + '　' + task.goal,
                    ' ',
                    React.createElement(
                      'button',
                      {
                        type: 'button',
                        style: { ...BTN, marginLeft: '6px' },
                        disabled: busy,
                        onClick: () => void discuss(task.when, task.goal),
                      },
                      '讨论',
                    ),
                  ),
                ),
              )
            : React.createElement('div', { style: MUTED }, '还没有任务记录'),

          React.createElement('div', { style: H }, '知识地图'),
          books.length
            ? React.createElement(
                'ul',
                { style: { margin: '4px 0 0 1.1rem', padding: 0 } },
                books.slice(0, 8).map(( book) =>
                  React.createElement('li', { key: book.book }, book.book + '（' + book.chapters + ' 章 / ' + book.points + ' 点）'),
                ),
              )
            : React.createElement('div', { style: MUTED }, '还没有知识地图'),

          React.createElement('div', { style: H }, '操作'),
          React.createElement(
            'div',
            { style: ROW },
            React.createElement(
              'input',
              {
                style: INPUT,
                value: doc,
                placeholder: '飞书文档 ID 或 wiki 链接',
                onChange: (event: any) => setDoc(event.target.value),
              },
            ),
            React.createElement('button', { style: BTN, disabled: busy, onClick: () => void run('sync', { doc }) }, '同步并提炼'),
            React.createElement('button', { style: BTN, disabled: busy, onClick: () => void run('next') }, '出题'),
          ),
          React.createElement(
            'div',
            { style: { ...ROW, marginTop: '6px' } },
            React.createElement(
              'input',
              {
                style: INPUT,
                value: doneName,
                placeholder: '知识点名称',
                onChange: (event: any) => setDoneName(event.target.value),
              },
            ),
            React.createElement(
              'input',
              {
                style: INPUT,
                value: donePath,
                placeholder: '产出路径',
                onChange: (event: any) => setDonePath(event.target.value),
              },
            ),
            React.createElement(
              'button',
              { style: BTN, disabled: busy, onClick: () => void run('done', { name: doneName, path: donePath }) },
              '回写',
            ),
          ),

          notice ? React.createElement('div', { style: OUT }, notice) : null,
          error ? React.createElement('div', { style: ERR }, error) : null,
          output ? React.createElement('div', { style: OUT }, output) : null,
        )
      : null,
  )
}

export function apply(ctx: any): void {
  for (const slot of SLOTS) {
    ctx.slots.inject(slot, () =>
      ctx.slots.register({ name: slot, id: 'learning-navigator', order: 60 }, () =>
        React.createElement(LearningPanel, { ctx }),
      ),
    )
  }
}
