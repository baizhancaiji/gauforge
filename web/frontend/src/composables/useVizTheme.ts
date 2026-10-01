/**
 * 图表主题令牌（m3-plan §4.11 C3：图表颜色只引用设计令牌，禁止硬编码
 * 色值）。从 :root 读取 --viz-* 序列色与功能色，随 html[data-theme] 切换
 * 重读（MutationObserver），图表组件 watch 令牌重建 option。
 */
import { onBeforeUnmount, onMounted, ref } from "vue";

export interface VizTokens {
  viz: string[];
  textFaint: string;
  gridLine: string;
  warn: string;
  danger: string;
  /** 根级 textStyle 用：canvas 不继承 DOM 字体栈，须显式给 Web 字体
   *  （WSL2 最小环境无系统 CJK 字体时，默认 sans-serif 渲染豆腐块）。 */
  fontSans: string;
}

const VIZ_VARS = ["--viz-1", "--viz-2", "--viz-3", "--viz-4", "--viz-5"];

function readTokens(): VizTokens {
  const s = getComputedStyle(document.documentElement);
  const v = (name: string) => s.getPropertyValue(name).trim();
  return {
    viz: VIZ_VARS.map(v),
    textFaint: v("--text-faint"),
    gridLine: v("--grid-line"),
    warn: v("--warn"),
    danger: v("--danger"),
    fontSans: v("--font-sans"),
  };
}

export function useVizTheme() {
  const tokens = ref<VizTokens>(readTokens());
  const ob = new MutationObserver(() => {
    tokens.value = readTokens();
  });
  onMounted(() =>
    ob.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    }),
  );
  onBeforeUnmount(() => ob.disconnect());
  return tokens;
}
