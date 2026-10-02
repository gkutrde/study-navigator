/**
 * 学习领航员 · 界面半边（浏览器 bundle）。
 *
 * 只用宿主的公开接缝：ctx.slots（挂面板）、ctx.workspaces（工作区过滤 / 登记）、
 * ctx.sessions + ctx.uiWorkspace（讨论用的原生会话）。
 * 数据来自本插件自己的服务端路由 /api/learning（同源 POST，认证栅栏之后）。
 * 所有用户可见文本都是**中文**；失败在面板内原地显示。
 *
 * T-050：插件**只在「学习领航员」工作区启用**——面板只在当前会话属于该工作区时渲染，
 * 每个请求都带上工作区 id，服务端再按宿主工作区注册表核验一遍。
 */
import * as React from 'react'

import { WORKSPACE_TITLE, errorText } from '../shared.ts'
import type { BookData, LearningPayload, ProfileData, TaskData } from '../shared.ts'

export { WORKSPACE_TITLE }

const { useCallback, useEffect, useState, useSyncExternalStore } = React
const h = React.createElement

/**
 * 面板挂在这个 slot 上：输入框上沿（会话作用域，组件拿得到当前会话的 sessionId）。
 *
 * 以前还注册了 conversation.session.header.actions 当"升级备选"——宿主 0.2.0 起那个 slot
 * 真的会渲染（会话标题栏右侧，放模型预设/后台任务这种紧凑按钮），整块面板会被塞进标题栏，
 * 一个会话里出现两份面板。所以只挂这一处。
 */
export const SLOT = 'conversation.input.dock'
export const SLOTS = [SLOT] as const

/**
 * 必须声明 inject（少了宿主会拒绝访问对应服务）。
 * - slots：挂面板；workspaces：工作区过滤与登记（T-046/T-050）；
 * - sessions + uiWorkspace：T-040 讨论要开原生会话并切过去（uiWorkspace 是宿主的导航服务）。
 * 取用时仍然 try 兜住并降级：接缝形状随宿主版本变，不能因为一个接缝让面板整个崩掉。
 */
export const inject = ['slots', 'sessions', 'workspaces', 'uiWorkspace']

const ROUTE = '/api/learning'

/** 引用会话时报给宿主的来源标签（宿主按来源统计谁还持有会话，便于排查泄漏）。 */
const SESSION_SOURCE = 'learningNavigator'

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
const LIST: React.CSSProperties = { margin: '4px 0 0 1.1rem', padding: 0 }

const sleep = (ms: number) => new Promise((done) => setTimeout(done, ms))

// ---------------------------------------------------------------- 工作区（T-046 / T-050）

/** 宿主工作区快照里一行（ctx.workspaces.list.getSnapshot().items 的元素）。 */
export type WorkspaceItem = { workspaceId: string; title: string; path: string; sessionIds: readonly string[] }

/**
 * 当前会话所在的「学习领航员」工作区；不在该工作区（或数据不全）就返回 null。
 *
 * 会话归属以宿主的 sessionIds 为准（宿主按会话目录核过），不靠路径字符串比对。
 */
export function learningWorkspaceOf(items: unknown, sessionId: unknown): WorkspaceItem | null {
  const id = String(sessionId ?? '')
  if (!id || !Array.isArray(items)) return null
  const hit = items.find(
    (item: any) =>
      String(item?.title ?? '') === WORKSPACE_TITLE &&
      Array.isArray(item?.sessionIds) &&
      item.sessionIds.some((sid: unknown) => String(sid) === id),
  )
  return hit ? (hit as WorkspaceItem) : null
}

/** 这个标题是否已被**别的**工作区占用。 */
function workspaceTaken(items: readonly any[], selfId: string): boolean {
  return items.some(
    (item: any) => String(item?.workspaceId) !== String(selfId) && String(item?.title || '') === WORKSPACE_TITLE,
  )
}

function workspaceItems(workspaces: any): any[] {
  try {
    return workspaces?.list?.getSnapshot?.()?.items || []
  } catch {
    return []
  }
}

const NO_WORKSPACES = { items: [] as any[] }

/** 订阅宿主工作区快照（快照对象身份稳定，可直接给 useSyncExternalStore）。 */
function useWorkspaceSnapshot(ctx: any): { items: readonly any[] } {
  const subscribe = useCallback(
    (listener: () => void) => {
      try {
        const unsubscribe = ctx?.workspaces?.list?.subscribe?.(listener)
        return typeof unsubscribe === 'function' ? unsubscribe : () => {}
      } catch {
        return () => {}
      }
    },
    [ctx],
  )
  const getSnapshot = useCallback(() => {
    try {
      return ctx?.workspaces?.list?.getSnapshot?.() ?? NO_WORKSPACES
    } catch {
      return NO_WORKSPACES
    }
  }, [ctx])
  return useSyncExternalStore(subscribe, getSnapshot)
}

/**
 * 拿到（必要时登记）**专用工作区**，返回它的 id（T-046）。
 *
 * 宿主限制（实测 0.1.5-rc.3，0.2.0-rc.1 源码核对未变，已写进 README）：
 *   "workspaces.create" **只接受目录路径**，工作区标题由目录派生；
 *   改名是**全局**的（"rename" 没有 per-caller 作用域）。
 * 所以这里给的是**最接近的做法**：登记（幂等）该目录的工作区，并在没人占用时改成专用标题。
 *
 * @returns { workspaceId, note } —— note 是给用户看的中文说明（成功时为空）
 */
export async function ensureDedicatedWorkspace(
  ctx: any,
  directory: string,
): Promise<{ workspaceId?: string; note: string }> {
  const workspaces = ctx?.workspaces
  if (!workspaces || typeof workspaces.create !== 'function') {
    return { note: '当前宿主没有工作区接缝，无法登记「' + WORKSPACE_TITLE + '」工作区' }
  }
  const path = String(directory || '').trim()
  if (!path) return { note: '不知道该登记哪个目录（当前会话没有工作区目录）' }

  try {
    // create 是幂等的：同一目录只会有一个工作区
    const view = await workspaces.create({ path })
    const workspaceId = view?.workspaceId
    if (!workspaceId) return { note: '工作区登记成功但没拿到 id' }

    // 只在标题确实不对时才改名——不能无条件 rename（那会改掉用户已有的名字）；
    // 已经存在同名工作区时也不抢名字（宿主会报 workspace/name-conflict）
    if (String(view.title || '') !== WORKSPACE_TITLE) {
      if (workspaceTaken(workspaceItems(workspaces), workspaceId)) {
        return { workspaceId, note: '已有别的工作区叫「' + WORKSPACE_TITLE + '」，没有改名' }
      }
      await workspaces.rename(workspaceId, WORKSPACE_TITLE)
    }
    return { workspaceId, note: '' }
  } catch (cause) {
    return { note: '登记「' + WORKSPACE_TITLE + '」工作区失败：' + errorText(cause) }
  }
}

// ---------------------------------------------------------------- 讨论：原生会话（T-040 / T-046）

/** 会话标题：任务时间戳 + 任务目标前 20 字（T-046）。 */
export function sessionTitle(when: string, goal: string): string {
  const stamp = String(when || '').trim()
  const text = String(goal || '').replace(/\s+/g, ' ').trim()
  const head = text.length > 20 ? text.slice(0, 20) + '…' : text
  if (stamp && head) return stamp + ' ' + head
  return stamp || head || '任务讨论'
}

/** 把会话切成当前会话：0.2 起由宿主导航服务负责（uiWorkspace.openSession），老宿主用 sessions.open。 */
function focusSession(ctx: any, id: string): void {
  try {
    if (typeof ctx?.uiWorkspace?.openSession === 'function') {
      ctx.uiWorkspace.openSession(id)
      return
    }
  } catch {
    // 落回老接缝
  }
  try {
    if (typeof ctx?.sessions?.open === 'function') ctx.sessions.open(id)
  } catch {
    // 切不过去不影响预填：会话已经建好，用户点侧栏也能进
  }
}

/**
 * 给会话起标题并预填上下文。成功返回 null，失败返回中文原因。
 *
 * 刚建好的会话偶尔"还没就绪"：prompt 返回 ok:false 且原因像 not ready 时等一下重试（最多 3 次），
 * 别直接把用户丢去降级。
 */
async function promptFace(face: any, context: string, title?: string): Promise<string | null> {
  if (!face || typeof face.prompt !== 'function') return '会话已创建，但拿不到它的输入面'

  // T-046：会话标题 = 任务时间戳 + 任务目标前 20 字；改名失败不影响预填
  if (title && typeof face.rename === 'function') {
    try {
      await face.rename(title)
    } catch {
      // 标题只是方便找，失败就保留宿主默认标题
    }
  }

  for (let attempt = 0; attempt < 3; attempt += 1) {
    const result = await face.prompt([{ type: 'text', text: context }], 'queue')
    if (!result || result.ok !== false) return null
    const detail = String(result.error?.message || result.error || '未知原因')
    if (attempt < 2 && /not|ready|pending|未|不能/i.test(detail)) {
      await sleep(800)
      continue
    }
    return '会话已创建，但预填失败：' + detail
  }
  return '会话已创建，但预填没被接受（重试 3 次）'
}

/**
 * 老宿主（0.1.5-rc.3）取输入面的链：resolveAgentScope(id) → sessionOf(agentCtx)。
 * 那一版**没有** sessions.get / sessions.session（T-046 实测），它们只留作更老版本的兜底。
 */
function legacyFaceOf(sessions: any, id: string): any {
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

/**
 * 把讨论上下文预填进一个**原生会话**（T-040 主路径）。
 *
 * 全程只用宿主公开接缝：ctx.sessions.create → 切过去 → 拿输入面 prompt。
 * 插件在宿主进程内，所以不受 T-031 那套 CORS/cookie 限制——但也**绝不绕过鉴权**：
 * 拿不到接缝就直接降级，不伪造任何凭证。
 *
 * 两代宿主接缝（都按源码核对过）：
 * - 0.2.x：sessions.using(id, {source}, ref => ref.binding.session.prompt(...))——引用计数，用完即还；
 * - 0.1.5：open() 之后 scope 惰性 mint，要轮询 resolveAgentScope → sessionOf 等输入面就绪。
 *
 * @returns 失败原因（null 表示成功）
 */
export async function openNativeDiscussion(
  ctx: any,
  context: string,
  options: { workspaceId?: string; cwd?: string; title?: string } = {},
): Promise<string | null> {
  const sessions = ctx?.sessions
  if (!sessions || typeof sessions.create !== 'function') return '当前宿主没有公开的会话接缝'
  try {
    // 宿主 session.create **只接受 workspaceId 或 cwd 之一**——两个都给直接 gateway/bad-request
    // （以前两个一起传，T-046 的专用工作区路径因此永远建不出会话）。有工作区就只给 workspaceId。
    const target = options.workspaceId
      ? { workspaceId: options.workspaceId }
      : options.cwd
        ? { cwd: options.cwd }
        : undefined
    const id = await sessions.create(target)
    focusSession(ctx, id)

    if (typeof sessions.using === 'function') {
      return await sessions.using(id, { source: SESSION_SOURCE }, (reference: any) =>
        promptFace(reference?.binding?.session, context, options.title),
      )
    }

    // 0.1.5：会话要**上线成当前会话**它的 scope 才会被 mint 出来——open() 是同步调用，
    // 但 scope 惰性生成，所以要轮询等输入面就绪。实测踩过：立刻 prompt 会返回
    // "看起来成功"但消息根本没进日志（会话文件里只有 header）。
    let face = legacyFaceOf(sessions, id)
    for (let i = 0; i < 40 && (!face || typeof face.prompt !== 'function'); i += 1) {
      await sleep(250)
      face = legacyFaceOf(sessions, id)
    }
    return await promptFace(face, context, options.title)
  } catch (cause) {
    return '开原生会话失败：' + errorText(cause)
  }
}

// ---------------------------------------------------------------- 面板

/** 调本插件的服务端路由。HTTP 失败 / 回包不是 JSON 都变成 {ok:false, message}，不抛给界面。 */
async function call(body: Record<string, unknown>): Promise<LearningPayload> {
  const response = await fetch(ROUTE, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
  const payload = await response.json().catch(() => null)
  if (!payload || typeof payload !== 'object') {
    return { ok: false, message: '面板接口返回了无法解析的内容（HTTP ' + response.status + '）' }
  }
  return payload as LearningPayload
}

function bulletList<T>(items: T[], render: (item: T, index: number) => React.ReactNode, empty: string) {
  return items.length ? h('ul', { style: LIST }, items.map(render)) : h('div', { style: MUTED }, empty)
}

/** 学习面板：画像 / 任务 / 知识地图 + 三个动作按钮 + 项目路径配置。只在「学习领航员」工作区里渲染。 */
export function LearningPanel(props: { ctx?: any; workspace?: WorkspaceItem | null }): React.ReactElement {
  const hostCtx = props?.ctx
  const workspaceId = props?.workspace?.workspaceId
  const workspacePath = props?.workspace?.path || ''
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

  /** 每个请求都带上工作区（服务端据此过滤）与可选的项目路径。 */
  const request = useCallback(
    (body: Record<string, unknown>) => {
      const projectRoot = pathInput.trim()
      return call({ ...body, workspaceId, ...(projectRoot ? { projectRoot } : {}) })
    },
    [pathInput, workspaceId],
  )

  const load = useCallback(async () => {
    setError('')
    try {
      // 三份数据互不依赖：并发取，展开面板少等两个来回
      const [p, t, s] = await Promise.all([
        request({ action: 'profile' }),
        request({ action: 'tasks' }),
        request({ action: 'syllabus' }),
      ])
      if (!p.ok) {
        setError(String(p.message || '读画像失败'))
        return
      }
      setProfile(p.data?.profile ?? p.data)
      if (p.projectRoot) setRoot(String(p.projectRoot))
      if (t.ok) setTasks(Array.isArray(t.data) ? t.data : [])
      if (s.ok) setBooks(Array.isArray(s.data) ? s.data : [])
    } catch (cause) {
      setError('读项目失败：' + errorText(cause))
    }
  }, [request])

  // 首次展开时读一次；之后靠「重新读取」按钮刷新（避免每次折叠都打三次请求）
  const [loadedOnce, setLoadedOnce] = useState(false)
  useEffect(() => {
    if (!open || loadedOnce) return
    setLoadedOnce(true)
    void load()
  }, [open, loadedOnce, load])

  const run = useCallback(
    async (action: string, extra: Record<string, unknown> = {}) => {
      setBusy(true)
      setError('')
      setOutput('')
      try {
        const payload = await request({ action, ...extra })
        if (!payload.ok) {
          setError(String(payload.message || '执行失败'))
          return
        }
        setOutput(String(payload.output || '完成'))
        if (payload.data?.profile) setProfile(payload.data.profile)
        if (Array.isArray(payload.data?.tasks)) setTasks(payload.data.tasks)
      } catch (cause) {
        setError('执行失败：' + errorText(cause))
      } finally {
        setBusy(false)
      }
    },
    [request],
  )

  /**
   * 讨论：先试**原生会话**（建在当前「学习领航员」工作区里，把 handoff 预填进去）；
   * 拿不到接缝就**降级**到面板内自渲染（调 headless），并明确告诉用户。
   */
  const discuss = useCallback(
    async (when: string, goal: string = '') => {
      setBusy(true)
      setError('')
      setOutput('')
      setNotice('')
      try {
        const payload = await request({ action: 'discuss', when })
        if (!payload.ok) {
          setError(String(payload.message || '拿不到讨论上下文'))
          return
        }
        const context = String(payload.data?.text || '')
        const failure = await openNativeDiscussion(hostCtx, context, {
          workspaceId,
          cwd: root || workspacePath,
          title: sessionTitle(when, goal),
        })
        if (!failure) {
          setNotice('已在「' + WORKSPACE_TITLE + '」工作区打开讨论，并把这道题的上下文预填好了。')
          return
        }
        setNotice('原生会话不可用（' + failure + '），已降级到面板内讨论。')
        const answer = await request({ action: 'chat', when, message: context })
        if (!answer.ok) setError(String(answer.message || '降级讨论也失败了'))
        else setOutput(String(answer.output || ''))
      } catch (cause) {
        setError('讨论失败：' + errorText(cause))
      } finally {
        setBusy(false)
      }
    },
    [hostCtx, request, root, workspaceId, workspacePath],
  )

  const summary = profile ? Object.entries(profile.counts).map(([k, v]) => k + ' ' + v).join(' ｜ ') : ''
  const input = (value: string, placeholder: string, onChange: (value: string) => void) =>
    h('input', { style: INPUT, value, placeholder, onChange: (event: any) => onChange(event.target.value) })
  const button = (label: string, onClick: () => void, extraStyle: React.CSSProperties = {}) =>
    h('button', { type: 'button', style: { ...BTN, ...extraStyle }, disabled: busy, onClick }, label)

  const body = open
    ? h(
        'div',
        null,
        h('div', { style: H }, '项目路径'),
        h(
          'div',
          { style: ROW },
          input(pathInput, '留空则用工作区目录' + (workspacePath ? '：' + workspacePath : ''), setPathInput),
          h('button', { type: 'button', style: BTN, onClick: () => void load() }, '重新读取'),
        ),
        root ? h('div', { style: MUTED }, '当前项目：' + root) : null,

        h('div', { style: H }, '知识画像'),
        profile && profile.total
          ? bulletList(
              profile.points.slice(0, 12),
              (point, index) => h('li', { key: point.name + index }, '[' + point.level + '] ' + point.name),
              '',
            )
          : h('div', { style: MUTED }, '还没有画像数据'),

        h('div', { style: H }, '任务'),
        bulletList(
          tasks.slice(-5).reverse(),
          (task) =>
            h(
              'li',
              { key: task.when },
              (task.isReview ? '【复习】' : '') + task.when + '　' + task.goal,
              ' ',
              button('讨论', () => void discuss(task.when, task.goal), { marginLeft: '6px' }),
            ),
          '还没有任务记录',
        ),

        h('div', { style: H }, '知识地图'),
        bulletList(
          books.slice(0, 8),
          (book) => h('li', { key: book.book }, book.book + '（' + book.chapters + ' 章 / ' + book.points + ' 点）'),
          '还没有知识地图',
        ),

        h('div', { style: H }, '操作'),
        h(
          'div',
          { style: ROW },
          input(doc, '飞书文档 ID 或 wiki 链接', setDoc),
          button('同步并提炼', () => void run('sync', { doc })),
          button('出题', () => void run('next')),
        ),
        h(
          'div',
          { style: { ...ROW, marginTop: '6px' } },
          input(doneName, '知识点名称', setDoneName),
          input(donePath, '产出路径', setDonePath),
          button('回写', () => void run('done', { name: doneName, path: donePath })),
        ),

        notice ? h('div', { style: OUT }, notice) : null,
        error ? h('div', { style: ERR }, error) : null,
        output ? h('div', { style: OUT }, output) : null,
      )
    : null

  return h(
    'div',
    { style: PANEL, className: 'dsh-learning-panel' },
    h(
      'div',
      { style: ROW },
      // 必须是真正的 button：实测挂 onClick 的 span 在这个宿主里点不动
      // （没有原生点击语义，合成事件也捞不到）。附带好处是键盘可达。
      h(
        'button',
        { type: 'button', style: BTN, 'aria-expanded': open, onClick: () => setOpen((value) => !value) },
        '学习' + (open ? ' ▾' : ' ▸'),
      ),
      profile ? h('span', { style: MUTED }, summary) : null,
      busy ? h('span', { style: MUTED }, '执行中…') : null,
    ),
    body,
  )
}

/**
 * 首次使用的引导：宿主里**还没有任何**「学习领航员」工作区时，提供一键把当前工作区登记/改名过去。
 *
 * 面板本身只在该工作区里出现；没有这一步，新用户根本找不到面板。
 * 一旦有了这个工作区，别的工作区里就什么都不渲染。
 */
function WorkspaceOnboarding(props: { ctx: any; current: any }): React.ReactElement {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const setup = async () => {
    setBusy(true)
    const placed = await ensureDedicatedWorkspace(props.ctx, String(props.current?.path || ''))
    setNote(placed.note)
    setBusy(false)
  }
  return h(
    'div',
    { style: { ...PANEL, ...ROW }, className: 'dsh-learning-onboarding' },
    h('span', { style: MUTED }, '学习面板只在「' + WORKSPACE_TITLE + '」工作区启用。'),
    h(
      'button',
      { type: 'button', style: BTN, disabled: busy, onClick: () => void setup() },
      '把当前工作区设为「' + WORKSPACE_TITLE + '」',
    ),
    note ? h('span', { style: ERR }, note) : null,
  )
}

/** slot 组件：按当前会话所属工作区决定渲染面板、首次引导，还是什么都不渲染。 */
export function LearningSlot(props: { ctx: any; sessionId?: string }): React.ReactElement | null {
  const snapshot = useWorkspaceSnapshot(props.ctx)
  const items = Array.isArray(snapshot?.items) ? snapshot.items : []
  const workspace = learningWorkspaceOf(items, props.sessionId)
  if (workspace) return h(LearningPanel, { ctx: props.ctx, workspace })
  if (workspaceTaken(items, '')) return null
  const current = items.find((item: any) =>
    Array.isArray(item?.sessionIds) && item.sessionIds.some((sid: unknown) => String(sid) === String(props.sessionId)),
  )
  return current ? h(WorkspaceOnboarding, { ctx: props.ctx, current }) : null
}

export function apply(ctx: any): void {
  for (const slot of SLOTS) {
    // 会话作用域的 slot：宿主把当前会话的 sessionId 作为标准 prop 传进来
    ctx.slots.inject(slot, () =>
      ctx.slots.register({ name: slot, id: 'learning-navigator', order: 60 }, (slotProps: any) =>
        h(LearningSlot, { ctx, sessionId: slotProps?.sessionId }),
      ),
    )
  }
}
