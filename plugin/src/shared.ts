/**
 * 插件两半共用的常量与数据形状：浏览器面板（src/client/）与 Node 服务端路由（src/server/）。
 *
 * 两半分别打包成 lib/client.js 与 lib/index.js，本文件会被各自内联进去；
 * 以前同样的东西两边各写一份（工作区名、画像/任务/地图的数据形状），改一边忘一边。
 */

/**
 * 插件只在这个工作区启用（T-050）：
 * - 客户端：面板只在「当前会话属于该工作区」时渲染；
 * - 服务端：/api/learning 只接受来自该工作区的请求（按宿主工作区注册表核验，不信客户端自报的标题）。
 * 工作区本身由 T-046 引入：项目目录登记成工作区并改名为它。
 */
export const WORKSPACE_TITLE = '学习领航员'

/** 画像概要：四态计数 + 知识点列表（服务端 readProfile 产出，面板直接渲染）。 */
export type ProfileData = {
  counts: Record<string, number>
  points: Array<{ name: string; level: string; topic: string }>
  total: number
}

/** 一条任务记录（服务端 readTasks 产出）。 */
export type TaskData = { when: string; goal: string; acceptance: string; isReview: boolean }

/** 知识地图里的一本书（服务端 readSyllabus 产出）。 */
export type BookData = { book: string; chapters: number; points: number }

/** 面板接口的统一回包：成功带 data / output，失败带中文 message。 */
export type LearningPayload = {
  ok: boolean
  message?: string
  output?: string
  data?: any
  projectRoot?: string
  [key: string]: unknown
}

/** 把任意异常变成给人看的一句话（面板与服务端共用，避免到处写 String(cause.message || cause)）。 */
export function errorText(cause: unknown): string {
  if (cause && typeof cause === 'object' && 'message' in cause) {
    const message = String((cause as { message?: unknown }).message ?? '')
    if (message) return message
  }
  return String(cause)
}
