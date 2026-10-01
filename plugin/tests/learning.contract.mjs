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
const { handleLearning, resolveProjectRoot, buildCliArgs, ROUTE } = mod

import { fileURLToPath } from 'node:url'

// 本文件在 plugin/tests/ 下：再往上两级才是仓库根（plugin 的上一级）
const repo = fileURLToPath(new URL('../../', import.meta.url))
let failed = 0
function check(name, ok, detail) {
  if (!ok) failed += 1
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail ? ' :: ' + detail : ''))
}

check('route_path', ROUTE === '/api/learning', ROUTE)

const root = resolveProjectRoot(undefined, repo)
check('resolve_root_finds_repo', root.replace(/\\/g, '/').endsWith('/study'), root)
check('resolve_explicit_wins', resolveProjectRoot(repo, 'C:/nope').replace(/\\/g, '/').endsWith('/study'))

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

console.log(failed === 0 ? 'ALL CHECKS PASSED' : failed + ' CHECK(S) FAILED')
process.exit(failed === 0 ? 0 : 1)