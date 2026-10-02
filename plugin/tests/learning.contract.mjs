/**
 * T-039 契约测试：服务端学习面板模块（plugin/src/server/learning.ts）。
 *
 * 直接用 Node 24 的类型剥离加载**源码**（不依赖宿主、不依赖构建产物），
 * 把结果按 CHECK 行打印出来，由 pytest 断言。
 *
 * 重点在**安全不变量**：动作白名单、命令只能 spawn 数组、用户输入不被拼进命令。
 */
const src = new URL('../src/server/learning.ts', import.meta.url).href
const mod = await import(src)
const { handleLearning, resolveProjectRoot, buildCliArgs, ROUTE, checkWorkspace, serveLearning, taskFileId } = mod

import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// 本文件在 plugin/tests/ 下：再往上两级才是仓库根（plugin 的上一级）
const repo = fileURLToPath(new URL('../../', import.meta.url))
let failed = 0
function check(name, ok, detail) {
  if (!ok) failed += 1
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail ? ' :: ' + detail : ''))
}

// 按真实路径比较，不按目录名：仓库克隆成什么名字都要能过（原先写死了 /study）
const samePath = (a, b) =>
  resolve(a).replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase() ===
  resolve(b).replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase()

check('route_path', ROUTE === '/api/learning', ROUTE)

const root = resolveProjectRoot(undefined, repo)
check('resolve_root_finds_repo', samePath(root, repo), root)
check('resolve_explicit_wins', samePath(resolveProjectRoot(repo, 'C:/nope'), repo))
// plugin/ 自己也有 README.md：从插件目录往上找必须越过它，停在真正的项目根（有 profile/ + src/cli.py）
const fromPlugin = resolveProjectRoot(undefined, join(repo, 'plugin', 'src'))
check('resolve_root_skips_plugin_readme', samePath(fromPlugin, repo), fromPlugin)

const profile = await handleLearning({ action: 'profile' }, { root, python: 'python' })
check('profile_status', profile.status === 200 && profile.payload.ok === true)
check('profile_counts_four_states',
  profile.payload.data && JSON.stringify(Object.keys(profile.payload.data.counts).sort()) ===
  JSON.stringify(['存疑', '学过', '做过', '输出'].sort()),
  JSON.stringify(profile.payload.data && profile.payload.data.counts))
check('profile_has_points', profile.payload.data.total > 0, String(profile.payload.data.total))

const tasks = await handleLearning({ action: 'tasks' }, { root, python: 'python' })
check('tasks_is_array', Array.isArray(tasks.payload.data))
check('tasks_have_when_goal', tasks.payload.data.every((t) => typeof t.when === 'string' && typeof t.goal === 'string'))

const syllabus = await handleLearning({ action: 'syllabus' }, { root, python: 'python' })
check('syllabus_is_array', Array.isArray(syllabus.payload.data))
check('syllabus_books_have_counts', syllabus.payload.data.every((b) => typeof b.book === 'string' && typeof b.chapters === 'number'))

const unknown = await handleLearning({ action: 'rm -rf /' }, { root, python: 'python' })
check('unknown_action_rejected', unknown.status === 400 && unknown.payload.ok === false, unknown.payload.message)

const empty = await handleLearning({}, { root, python: 'python' })
check('empty_action_rejected', empty.status === 400)

const syncNoDoc = await handleLearning({ action: 'sync' }, { root, python: 'python' })
check('sync_needs_doc', syncNoDoc.status === 400 && /文档/.test(syncNoDoc.payload.message), syncNoDoc.payload.message)

const doneNoName = await handleLearning({ action: 'done', path: 'x.html' }, { root, python: 'python' })
check('done_needs_name', doneNoName.status === 400, doneNoName.payload.message)

const doneNoPath = await handleLearning({ action: 'done', name: '列表' }, { root, python: 'python' })
check('done_needs_path', doneNoPath.status === 400, doneNoPath.payload.message)

const missing = await handleLearning({ action: 'profile' }, { root: 'C:/Windows', python: 'python' })
check('missing_project_is_chinese_400', missing.status === 400 && /找不到项目/.test(missing.payload.message), missing.payload.message)

check('next_args_are_whtielist_only', JSON.stringify(buildCliArgs('next', {})) === '["next"]')
const injected = buildCliArgs('done', { name: '列表; rm -rf /', path: 'a && b.html' })
check('user_input_stays_whole_arg',
  injected[1] === '列表; rm -rf /' && injected[2] === 'a && b.html',
  JSON.stringify(injected))
check('no_shell_metachars_removed', injected.length === 3, JSON.stringify(injected))

const recite = buildCliArgs('done', { name: 'x', path: 'y', recite: '能讲清' })
check('recite_flag_whitelisted', JSON.stringify(recite) === '["done","x","y","--recite","能讲清"]', JSON.stringify(recite))

let threw = ''
try { buildCliArgs('profile', {}) } catch (cause) { threw = String(cause.message || cause) }
check('readonly_action_has_no_cli', /不需要跑 CLI/.test(threw), threw)

// ---------- T-040：讨论 ----------
const caps = await handleLearning({ action: 'capabilities' }, { root, python: 'python' })
check('capabilities_reported', caps.status === 200 && caps.payload.data && caps.payload.data.handoff === true,
  JSON.stringify(caps.payload.data))

const noHandoff = await handleLearning({ action: 'discuss' }, { root, python: 'python' })
check('discuss_needs_when', noHandoff.status === 400 && /接力上下文/.test(noHandoff.payload.message),
  noHandoff.payload.message)

const badWhen = await handleLearning({ action: 'discuss', when: '不存在的时间' }, { root, python: 'python' })
check('discuss_bad_when_is_chinese', badWhen.status === 400 && /接力上下文/.test(badWhen.payload.message),
  badWhen.payload.message)

const chatNoWhen = await handleLearning({ action: 'chat', message: 'x' }, { root, python: 'python' })
check('chat_needs_when', chatNoWhen.status === 400, chatNoWhen.payload.message)

const chatArgs = buildCliArgs('chat', { when: '2026-09-27 00:32', message: '缺什么？; rm -rf /' })
check('chat_args_not_shell_interpolated',
  chatArgs.length === 3 && chatArgs[1] === '2026-09-27 00:32' && chatArgs[2] === '缺什么？; rm -rf /',
  JSON.stringify(chatArgs))

// ---------- T-050：只在「学习领航员」工作区启用（服务端过滤） ----------
// 假的宿主工作区注册表：形状与 ctx.workspaceRegistry.get(id) 一致（0.1.5-rc.3 / 0.2.0-rc.1 源码核对）
const registry = {
  get(id) {
    if (id === 'ws-learning') return { path: repo, title: '学习领航员' }
    if (id === 'ws-other') return { path: repo, title: 'study-navigator' }
    return undefined
  },
}

check('gate_accepts_learning_workspace', checkWorkspace(registry, 'ws-learning').ok === true)
const otherGate = checkWorkspace(registry, 'ws-other')
check('gate_rejects_other_workspace', otherGate.ok === false && otherGate.status === 403 && /学习领航员/.test(otherGate.message),
  otherGate.message)
const missingGate = checkWorkspace(registry, '')
check('gate_rejects_missing_workspace', missingGate.ok === false && missingGate.status === 403, missingGate.message)
const unknownGate = checkWorkspace(registry, 'ws-ghost')
check('gate_rejects_unknown_workspace', unknownGate.ok === false && unknownGate.status === 403, unknownGate.message)
const noRegistry = checkWorkspace(undefined, 'ws-learning')
check('gate_fails_closed_without_registry', noRegistry.ok === false && noRegistry.status === 503, noRegistry.message)
const throwing = checkWorkspace({ get() { throw new Error('boom') } }, 'ws-learning')
check('gate_survives_registry_errors', throwing.ok === false && throwing.status === 403, throwing.message)

// 客户端自报的标题不算数：只认注册表
const forged = await serveLearning({ action: 'profile', workspaceId: 'ws-other', workspaceTitle: '学习领航员' }, { registry })
check('serve_ignores_forged_title', forged.status === 403 && forged.payload.ok === false, forged.payload.message)

const served = await serveLearning({ action: 'profile', workspaceId: 'ws-learning' }, { registry, cwd: 'C:/' })
check('serve_defaults_root_to_workspace_path',
  served.status === 200 && served.payload.ok === true && samePath(served.payload.projectRoot, repo),
  String(served.payload.projectRoot))

const servedOverride = await serveLearning(
  { action: 'tasks', workspaceId: 'ws-learning', projectRoot: 'C:/Windows' }, { registry })
check('serve_project_root_override_still_checked', servedOverride.status === 400 && /找不到项目/.test(servedOverride.payload.message),
  servedOverride.payload.message)

const rejectedCli = await serveLearning({ action: 'next', workspaceId: 'ws-other' }, { registry })
check('serve_rejects_cli_outside_workspace', rejectedCli.status === 403, rejectedCli.payload.message)

// handoff 文件名与 Python 的 handoff.task_file_id 同一规则（逐条对照值由 pytest 侧核对）
check('task_file_id_basic', taskFileId('2026-09-27 10:30') === '2026-09-27-1030', taskFileId('2026-09-27 10:30'))
check('task_file_id_no_traversal', !/[\\/]/.test(taskFileId('../../etc/passwd 10:30')), taskFileId('../../etc/passwd 10:30'))

console.log(failed === 0 ? 'ALL CHECKS PASSED' : failed + ' CHECK(S) FAILED')
process.exit(failed === 0 ? 0 : 1)