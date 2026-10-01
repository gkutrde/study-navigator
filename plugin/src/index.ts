/**
 * 学习领航员 · 服务端入口（Node 半边）。
 *
 * 架构边界（见仓库 02-系统架构 与 F-16）：
 *   - 插件**只做界面与宿主集成**；
 *   - 数据与逻辑仍在本地 Python 核心（profile/ 下的文件 + python -m src.cli）。
 *
 * 具体逻辑都在 src/server/learning.ts；这里只做接线（便于单测）。
 */
import { registerLearningRoute, ROUTE } from './server/learning.js'

export const name = 'dsh-learning-navigator'

/** 只声明确定存在的公开接缝（客户端那半边是 ['slots']）。 */
export const inject = ['connection']

export function apply(ctx: any, rowConfig: Record<string, unknown> = {}): void {
  const disposer = registerLearningRoute(ctx, rowConfig ?? {})
  if (disposer && typeof ctx.logger?.info === 'function') {
    ctx.logger.info('[学习领航员] 已注册 ' + ROUTE + '（面板通道就绪）')
  }
}
