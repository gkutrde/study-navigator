/**
 * T-050 客户端契约测试：加载**构建产物** lib/client.js（宿主真正加载的就是它），校验
 * 工作区过滤、讨论会话的建法（两代宿主接缝）、slot 注册。
 *
 * 不依赖宿主、不依赖 node_modules：用假的 __ModuleLoader__ 握手接住 factory，
 * react 只给一个够模块初始化用的桩（这里只测纯逻辑，不渲染组件）。
 *
 * 宿主对象的形状按 DSH 源码核对（0.1.5-rc.3 的 npm 类型声明、0.2.0-rc.1 的源码）。
 */
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'

let failed = 0
function check(name, ok, detail) {
  if (!ok) failed += 1
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail ? ' :: ' + detail : ''))
}

const bundle = readFileSync(new URL('../lib/client.js', import.meta.url), 'utf8')
const reactStub = {
  createElement: (type, props, ...children) => ({ type, props, children }),
  useCallback: (fn) => fn,
  useEffect: () => {},
  useState: (value) => [value, () => {}],
  useSyncExternalStore: (_subscribe, getSnapshot) => getSnapshot(),
}
let loaded = null
runInNewContext(bundle, {
  window: {
    __ModuleLoader__: {
      load({ id, factory }) {
        loaded = { id, exports: factory((name) => (name === 'react' ? reactStub : {})) }
      },
    },
  },
  setTimeout,
  clearTimeout,
  console,
})

check('bundle_loads_via_module_loader', loaded && loaded.id === 'dsh-learning-navigator', loaded && loaded.id)
const client = loaded.exports

// ---------- 接缝声明 ----------
check('inject_declares_needed_seams',
  JSON.stringify(client.inject) === JSON.stringify(['slots', 'sessions', 'workspaces', 'uiWorkspace']),
  JSON.stringify(client.inject))
check('only_dock_slot', JSON.stringify(Array.from(client.SLOTS)) === JSON.stringify(['conversation.input.dock']),
  JSON.stringify(client.SLOTS))

const registered = []
client.apply({
  slots: {
    inject: (slot, callback) => callback(),
    register: (options, component) => registered.push({ options, component }),
  },
})
check('apply_registers_once_into_dock', registered.length === 1 && registered[0].options.name === 'conversation.input.dock',
  JSON.stringify(registered.map((item) => item.options)))

// ---------- 工作区过滤 ----------
const items = [
  { workspaceId: 'ws-1', title: '学习领航员', path: 'D:/study', sessionIds: ['s-1', 's-2'] },
  { workspaceId: 'ws-2', title: 'other', path: 'D:/other', sessionIds: ['s-3'] },
]
check('session_in_learning_workspace', client.learningWorkspaceOf(items, 's-2')?.workspaceId === 'ws-1')
check('session_in_other_workspace_is_filtered', client.learningWorkspaceOf(items, 's-3') === null)
check('missing_session_is_filtered', client.learningWorkspaceOf(items, undefined) === null)
check('broken_snapshot_is_filtered', client.learningWorkspaceOf(null, 's-1') === null)

// slot 组件：同一个组件，按会话所属工作区决定渲染什么
const slotProps = (sessionId, list) => ({ ctx: { workspaces: { list: { getSnapshot: () => ({ items: list }), subscribe: () => () => {} } } }, sessionId })
const inLearning = client.LearningSlot(slotProps('s-1', items))
check('slot_renders_panel_in_learning_workspace', inLearning && inLearning.type === client.LearningPanel)
check('slot_renders_nothing_elsewhere', client.LearningSlot(slotProps('s-3', items)) === null)
const fresh = [{ workspaceId: 'ws-9', title: 'study-navigator', path: 'D:/study', sessionIds: ['s-9'] }]
const onboarding = client.LearningSlot(slotProps('s-9', fresh))
check('slot_offers_onboarding_before_workspace_exists', onboarding && onboarding.type !== client.LearningPanel,
  onboarding && String(onboarding.type && onboarding.type.name))
check('slot_without_workspaces_seam_renders_nothing', client.LearningSlot({ ctx: {}, sessionId: 's-1' }) === null)

// ---------- 会话标题 ----------
check('session_title_truncates_goal', client.sessionTitle('2026-09-27 10:00', '一二三四五六七八九十一二三四五六七八九十多出来') ===
  '2026-09-27 10:00 一二三四五六七八九十一二三四五六七八九十…')
check('session_title_fallback', client.sessionTitle('', '') === '任务讨论')

// ---------- 讨论：宿主 0.2.x 形状 ----------
function host02() {
  const calls = { create: [], open: [], using: [], prompt: [], rename: [] }
  const face = {
    rename: async (title) => { calls.rename.push(title); return { ok: true } },
    prompt: async (content, mode) => { calls.prompt.push({ content, mode }); return { ok: true } },
  }
  const ctx = {
    sessions: {
      create: async (opts) => { calls.create.push(opts); return 'session-new' },
      using: async (id, options, operation) => { calls.using.push({ id, options }); return operation({ binding: { session: face } }) },
    },
    uiWorkspace: { openSession: (id) => calls.open.push(id) },
  }
  return { ctx, calls }
}

{
  const { ctx, calls } = host02()
  const failure = await client.openNativeDiscussion(ctx, '接力上下文全文', { workspaceId: 'ws-1', cwd: 'D:/study', title: '标题' })
  check('v02_discussion_succeeds', failure === null, String(failure))
  // 宿主 session.create 只接受 workspaceId 或 cwd 之一：两个都给会 gateway/bad-request（以前就是这么失败的）
  check('v02_create_gets_workspace_only', JSON.stringify(calls.create) === JSON.stringify([{ workspaceId: 'ws-1' }]),
    JSON.stringify(calls.create))
  check('v02_focuses_via_ui_workspace', JSON.stringify(calls.open) === JSON.stringify(['session-new']))
  check('v02_retains_with_source_label', calls.using.length === 1 && calls.using[0].options.source === 'learningNavigator',
    JSON.stringify(calls.using))
  check('v02_prefills_context', calls.prompt.length === 1 && calls.prompt[0].content[0].text === '接力上下文全文' &&
    calls.prompt[0].mode === 'queue')
  check('v02_sets_title', JSON.stringify(calls.rename) === JSON.stringify(['标题']))
}

{
  const { ctx, calls } = host02()
  await client.openNativeDiscussion(ctx, 'x', { cwd: 'D:/study' })
  check('create_uses_cwd_without_workspace', JSON.stringify(calls.create) === JSON.stringify([{ cwd: 'D:/study' }]),
    JSON.stringify(calls.create))
}

{
  const { ctx } = host02()
  ctx.sessions.using = async (_id, _options, operation) =>
    operation({ binding: { session: { prompt: async () => ({ ok: false, error: { message: 'quota exhausted' } }) } } })
  const failure = await client.openNativeDiscussion(ctx, 'x', { workspaceId: 'ws-1' })
  check('prompt_failure_is_reported_in_chinese', /预填失败/.test(String(failure)), String(failure))
}

{
  const failure = await client.openNativeDiscussion({ sessions: { create: async () => { throw new Error('bad-request') } } }, 'x', {})
  check('create_failure_is_reported_not_thrown', /开原生会话失败/.test(String(failure)) && /bad-request/.test(String(failure)),
    String(failure))
}

check('no_session_seam_degrades', (await client.openNativeDiscussion({}, 'x', {})) === '当前宿主没有公开的会话接缝')

// ---------- 讨论：宿主 0.1.5 形状（open + resolveAgentScope → sessionOf） ----------
{
  const calls = { open: [], prompt: [] }
  const face = { prompt: async (content) => { calls.prompt.push(content); return { ok: true } } }
  const ctx = {
    sessions: {
      create: async () => 'session-old',
      open: (id) => calls.open.push(id),
      resolveAgentScope: (id) => ({ id }),
      sessionOf: (agentCtx) => (agentCtx.id === 'session-old' ? face : undefined),
    },
  }
  const failure = await client.openNativeDiscussion(ctx, '老宿主', { workspaceId: 'ws-1' })
  check('v015_discussion_succeeds', failure === null, String(failure))
  check('v015_focuses_via_sessions_open', JSON.stringify(calls.open) === JSON.stringify(['session-old']))
  check('v015_prefills_context', calls.prompt.length === 1 && calls.prompt[0][0].text === '老宿主')
}

// ---------- 专用工作区登记（首次引导） ----------
{
  const renamed = []
  const workspaces = {
    create: async ({ path }) => ({ workspaceId: 'ws-9', title: 'study-navigator', path }),
    rename: async (id, title) => renamed.push([id, title]),
    list: { getSnapshot: () => ({ items: [] }) },
  }
  const placed = await client.ensureDedicatedWorkspace({ workspaces }, 'D:/study')
  check('onboarding_renames_when_title_free', placed.workspaceId === 'ws-9' && placed.note === '' &&
    JSON.stringify(renamed) === JSON.stringify([['ws-9', '学习领航员']]), JSON.stringify(placed))
}

{
  const renamed = []
  const workspaces = {
    create: async () => ({ workspaceId: 'ws-9', title: 'study-navigator' }),
    rename: async (id, title) => renamed.push([id, title]),
    list: { getSnapshot: () => ({ items: [{ workspaceId: 'ws-1', title: '学习领航员' }] }) },
  }
  const placed = await client.ensureDedicatedWorkspace({ workspaces }, 'D:/study')
  check('onboarding_never_steals_title', renamed.length === 0 && /没有改名/.test(placed.note), placed.note)
}

{
  const renamed = []
  const workspaces = {
    create: async () => ({ workspaceId: 'ws-1', title: '学习领航员' }),
    rename: async (id, title) => renamed.push([id, title]),
  }
  await client.ensureDedicatedWorkspace({ workspaces }, 'D:/study')
  check('onboarding_does_not_rename_when_already_right', renamed.length === 0)
}

check('onboarding_without_seam_explains', /工作区接缝/.test((await client.ensureDedicatedWorkspace({}, 'D:/x')).note))

console.log(failed === 0 ? 'ALL CHECKS PASSED' : failed + ' CHECK(S) FAILED')
process.exit(failed === 0 ? 0 : 1)
