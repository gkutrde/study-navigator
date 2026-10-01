/**
 * 客户端半边构建：src/client/index.tsx → lib/client.js。
 *
 * 产物必须被宿主 shell 的 window.__ModuleLoader__.load({ id, factory }) 握手包起来，
 * 模块 id 用包名。React 交给平台模块表（neverBundle），否则会出现两份 React。
 */
import { defineConfig } from 'tsdown'

const PLATFORM_MODULES = ['react', 'react/jsx-runtime']

export default defineConfig([
  /** 服务端半边：src/index.ts → lib/index.js（宿主按 main 字段加载）。 */
  {
    entry: ['src/index.ts'],
    outDir: 'lib',
    format: 'esm',
    platform: 'node',
    target: 'es2022',
    dts: false,
    sourcemap: true,
    clean: false,
  },
  {
    entry: ['src/client/index.tsx'],
    outDir: 'lib',
    format: 'cjs',
    platform: 'browser',
    target: 'es2022',
    external: PLATFORM_MODULES,
    deps: { neverBundle: PLATFORM_MODULES },
    outputOptions: {
      entryFileNames: 'client.js',
      banner: [
        'window.__ModuleLoader__.load({',
        '  id: "dsh-learning-navigator",',
        '  factory: (require) => {',
        '    var module = { exports: {} };',
        '    var exports = module.exports;',
      ].join('\n'),
      footer: '\n    return module.exports;\n  }\n});',
    },
    dts: false,
    sourcemap: true,
    clean: false,
  },
])