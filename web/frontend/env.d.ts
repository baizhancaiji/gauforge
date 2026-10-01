/// <reference types="vite/client" />

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>;
  export default component;
}
// 3Dmol.js vendored 副本（src/vendor/3dmol.es6.js）无类型声明：官方自带
// .d.ts 内部引用损坏；vendored 文件来源与剥离清单见该文件头注释（C1/C4
// 实证官方预构建产物含 autoload 在线抓取分支且无法摇树，故手术剥离后
// 入库），调用面收敛在 OrbitalsPanel 一处并经 context7 核对 API
// （AGENTS §8.3）。
declare module "@/vendor/3dmol.es6.js";
