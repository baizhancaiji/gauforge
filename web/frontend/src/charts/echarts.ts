/**
 * ECharts 按需注册（m3-plan §2.4 A3 定稿：LineChart/BarChart/Grid/
 * Tooltip/DataZoom 控制包体；判据参考线另需 MarkLine，渲染器必选）。
 * 图表组件一律从此处导入，禁止直接 import "echarts" 全量包。
 */
import { BarChart, LineChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  LineChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkLineComponent,
  CanvasRenderer,
]);

export default echarts;
