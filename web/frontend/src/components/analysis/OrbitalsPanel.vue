<script setup lang="ts">
/**
 * 轨道与静电势面板（m3-plan §4.12 C4 / §2.4 交互规格）：3Dmol vendored
 * 副本渲染——轨道清单选择（HOMO/LUMO 预置 + 序号直选，开壳层 α/β 分组）
 * → POST cube（幂等）→ GET cube 文件流 → 等值面正负双色（isoval 档位
 * ±0.02 默认 / ±0.05 / ±0.08）；静电势（Potential=SCF）走 VDW 表面 +
 * RWB 色彩映射。失败态按契约区分：503 cubegen 不可用 / 502 生成失败
 * （details.stderr 尾部）/ 422 参数越界。
 * workspace-out 模式（cubeAvailable=false，§2.4）：仅展示轨道能量清单，
 * cube/等值面入口置灰并注明「工作区文件无 fchk」。
 *
 * viewer 生命周期（§4.12 ④）：实例惰性创建单个 viewer，切换轨道/类型
 * clear() 重画（GLViewer 无顶层 dispose）；组件卸载 clear + 显式释放
 * WebGL 上下文（WEBGL_lose_context）后清容器，防连续切换累积上下文。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { client } from "@/api/client";
import type { components } from "@/api/contract";
import { useVizTheme } from "@/composables/useVizTheme";

// vendored 副本（来源与剥离清单见 src/vendor/3dmol.es6.js 文件头）
import {
  createViewer as create3DmolViewer,
  Gradient,
  VolumeData,
} from "@/vendor/3dmol.es6.js";

type OrbitalsResponse = components["schemas"]["OrbitalsResponse"];

const props = withDefaults(
  defineProps<{ executionId: number; data: OrbitalsResponse; cubeAvailable?: boolean }>(),
  { cubeAvailable: true },
);

const tokens = useVizTheme();
const el = ref<HTMLElement | null>(null);
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- vendored 产物无类型（见 env.d.ts 声明）
let viewer: any = null;

// ---------- 选择状态 ----------
type Kind = "MO" | "Potential";
const kind = ref<Kind>("MO");
const orbital = ref<number>(0); // 0 = 未选
const isoval = ref(0.02);
const ISOVALS = [0.02, 0.05, 0.08];

/** HOMO/LUMO 预置（闭壳层 homos 单值；LUMO = HOMO+1，越 nmo 上界不预置）。 */
const presets = computed(() => {
  const h = props.data.homos[0];
  const out: { label: string; n: number }[] = [];
  if (h != null && h >= 1) {
    out.push({ label: "HOMO", n: Math.floor(h) + 1 });
    if (Math.floor(h) + 2 <= props.data.nmo)
      out.push({ label: "LUMO", n: Math.floor(h) + 2 });
  }
  return out;
});

/** 自旋分组清单（闭壳层单组 spin=null；开壳层 α/β 两组）。 */
const spinGroups = computed(() => {
  const groups: { label: string; items: OrbitalsResponse["orbitals"] }[] = [];
  for (const [spin, label] of [
    [null, "轨道"],
    ["alpha", "α 自旋"],
    ["beta", "β 自旋"],
  ] as const) {
    const items = props.data.orbitals.filter((o) => o.spin === spin);
    if (items.length) groups.push({ label, items });
  }
  return groups;
});

const nmoUpper = computed(() => props.data.nmo);

// ---------- 渲染 ----------
const rendering = ref(false);
const error = ref<{ msg: string; detail?: string } | null>(null);
const loaded = ref<string | null>(null);

function ensureViewer() {
  if (viewer || !el.value) return viewer;
  // backgroundColor 须为实色（3dmol 不认 transparent，非法色名连锁
  // WebGL 初始化失败——冒烟实证）；取设计令牌 --bg-inset
  viewer = create3DmolViewer(el.value, {
    backgroundColor: tokens.value.bgInset,
  });
  return viewer;
}

/** cube 文本 → viewer 场景（模型 + 等值面/静电势表面）。 */
function renderCube(cubeText: string, kind: Kind) {
  const v = ensureViewer();
  if (!v) return;
  v.clear();
  v.addModel(cubeText, "cube");
  v.setStyle({}, { stick: { radius: 0.15 } });
  const vol = new VolumeData(cubeText, "cube");
  if (kind === "MO") {
    // 正负相双色等值面（§2.4：正相 viz[0] / 负相 danger）
    v.addIsosurface(vol, {
      isoval: isoval.value,
      color: tokens.value.viz[0],
      opacity: 0.85,
    });
    v.addIsosurface(vol, {
      isoval: -isoval.value,
      color: tokens.value.danger,
      opacity: 0.85,
    });
  } else {
    // 静电势色彩映射：VDW 表面 + RWB 发散映射（±0.05 e/Bohr 档，D1 走查校准）
    v.addSurface("VDW", { opacity: 0.9, voldata: vol, volscheme: new Gradient.RWB(-0.05, 0.05) }, {});
  }
  v.zoomTo();
  v.render();
}

async function generate() {
  if (rendering.value || !props.cubeAvailable) return;
  error.value = null;
  if (kind.value === "MO" && (orbital.value < 1 || orbital.value > nmoUpper.value)) {
    error.value = { msg: `请先选择轨道（1–${nmoUpper.value}）` };
    return;
  }
  rendering.value = true;
  const body: components["schemas"]["CubeRequest"] =
    kind.value === "MO"
      ? { kind: "MO", orbital: orbital.value }
      : { kind: "Potential" };
  const { data: created, error: genErr, response: genRes } = await client.POST(
    "/history/{id}/analysis/cube",
    { params: { path: { id: props.executionId } }, body },
  );
  if (genErr || !created) {
    rendering.value = false;
    const e = genErr as unknown as {
      error?: { code?: string; message?: string; details?: { stderr_tail?: string } };
    };
    const code = e?.error?.code;
    if (code === "CUBE_EXECUTABLE_MISSING") {
      error.value = { msg: "cubegen 不可用 — 请检查 g16_root 设置（503）" };
    } else if (code === "CUBE_GENERATION_FAILED") {
      error.value = {
        msg: "cube 生成失败（502）",
        detail: e?.error?.details?.stderr_tail ?? e?.error?.message,
      };
    } else {
      error.value = { msg: e?.error?.message ?? "请求失败" };
    }
    return;
  }
  const { data: blob, error: dlErr } = await client.GET(
    "/history/{id}/analysis/cube/{cube_id}",
    {
      params: {
        path: { id: props.executionId, cube_id: created.cube_id },
      },
      parseAs: "blob",
    },
  );
  rendering.value = false;
  if (dlErr || !blob) {
    error.value = { msg: "cube 下载失败" };
    return;
  }
  const text = await (blob as unknown as Blob).text();
  const label =
    kind.value === "MO"
      ? `MO ${orbital.value} / isoval ±${isoval.value}`
      : "静电势 Potential=SCF";
  try {
    renderCube(text, kind.value);
    loaded.value = label;
  } catch {
    // viewer 已建但场景初始化抛错：区分「环境无 WebGL」（canvas 上下文
    // 取不到）与「数据损坏」——D1 走查在真机显示环境复核渲染成功态
    viewer?.clear();
    viewer = null;
    if (el.value) el.value.innerHTML = "";
    const probe = document.createElement("canvas");
    const hasGL = probe.getContext("webgl2") || probe.getContext("webgl");
    error.value = hasGL
      ? { msg: "cube 渲染失败（数据可能损坏）" }
      : { msg: "当前浏览器/环境不支持 WebGL — 轨道等值面无法渲染" };
  }
}

function clearScene() {
  viewer?.clear();
  loaded.value = null;
}

onBeforeUnmount(() => {
  viewer?.clear();
  viewer = null;
  if (el.value) {
    // 显式释放 WebGL 上下文（GLViewer 无 dispose；不释放则连续切换执行
    // 累积上下文，触浏览器上限后 viewer 静默失渲染）
    const canvas = el.value.querySelector("canvas");
    const gl =
      canvas?.getContext("webgl2") ?? canvas?.getContext("webgl");
    (gl as WebGLRenderingContext | null)
      ?.getExtension("WEBGL_lose_context")
      ?.loseContext();
    el.value.innerHTML = "";
  }
});
</script>

<template>
  <div class="orb">
    <div class="orb-controls">
      <label class="ctl mono">
        <span>类型</span>
        <select v-model="kind" :disabled="!cubeAvailable">
          <option value="MO">分子轨道</option>
          <option value="Potential">静电势</option>
        </select>
      </label>
      <template v-if="kind === 'MO'">
        <div class="ctl mono presets">
          <button
            v-for="p in presets"
            :key="p.label"
            class="preset"
            type="button"
            :disabled="!cubeAvailable"
            :class="{ 'preset--on': orbital === p.n }"
            @click="orbital = p.n"
          >
            {{ p.label }}
          </button>
        </div>
        <label class="ctl mono">
          <span>轨道</span>
          <select v-model.number="orbital">
            <option :value="0" disabled>选择（1–{{ nmoUpper }}）</option>
            <optgroup v-for="g in spinGroups" :key="g.label" :label="g.label">
              <option v-for="o in g.items" :key="`${o.spin}-${o.index}`" :value="o.index">
                {{ o.index }}（{{ o.energy_eV.toFixed(2) }} eV{{ o.symmetry ? ` / ${o.symmetry}` : "" }}）
              </option>
            </optgroup>
          </select>
        </label>
        <div class="ctl mono">
          <span>isoval</span>
          <button
            v-for="v in ISOVALS"
            :key="v"
            class="preset"
            type="button"
            :disabled="!cubeAvailable"
            :class="{ 'preset--on': isoval === v }"
            @click="isoval = v"
          >
            ±{{ v }}
          </button>
        </div>
      </template>
      <button
        class="btn btn--secondary"
        type="button"
        :disabled="!cubeAvailable || rendering || (kind === 'MO' && !orbital)"
        @click="generate"
      >
        {{ rendering ? "生成中 …" : "生成并渲染" }}
      </button>
      <button v-if="loaded" class="btn btn--ghost" type="button" @click="clearScene">
        清除
      </button>
    </div>

    <p v-if="error" class="orb-note mono note--bad" role="alert">
      {{ error.msg }}
      <span v-if="error.detail" class="orb-detail">{{ error.detail }}</span>
    </p>
    <p v-else-if="loaded" class="orb-note mono note--ok">已渲染：{{ loaded }}</p>

    <div v-if="cubeAvailable" ref="el" class="orb-viewer"></div>
    <p v-else class="orb-off mono">
      工作区文件无 fchk — 等值面不可生成，仅轨道能量清单
    </p>
    <p class="orb-hint mono">
      等值面以本地 cubegen 生成（{{ nmoUpper > 0 ? `MO 1–${nmoUpper}` : "—" }}）；
      连续切换无残留
    </p>
  </div>
</template>

<style scoped>
.orb {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.orb-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.ctl {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  color: var(--text-faint);
}
.ctl select {
  height: var(--control-height-sm);
  max-width: 220px;
  font-size: var(--text-xs);
  color: var(--text-primary);
  background: var(--bg-inset);
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
}
.presets {
  gap: var(--space-1);
}
.preset {
  appearance: none;
  background: none;
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  padding: 1px var(--space-2);
  font-size: var(--text-xs);
  color: var(--text-faint);
  cursor: pointer;
}
.preset--on {
  color: var(--accent);
  border-color: var(--accent-dim);
}
.preset:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
.ctl select:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
.orb-off {
  margin: 0;
  border: 1px dashed var(--border-hair);
  border-radius: var(--r-md);
  padding: var(--space-3);
  background: var(--bg-inset);
  font-size: var(--text-sm);
  color: var(--text-faint);
}
.orb-note {
  margin: 0;
  font-size: var(--text-sm);
}
.note--bad {
  color: var(--danger);
}
.note--ok {
  color: var(--state-succeeded);
}
.orb-detail {
  display: block;
  font-size: var(--text-xs);
  color: var(--text-faint);
  white-space: pre-wrap;
  word-break: break-all;
}
.orb-viewer {
  /* vendored 3dmol canvas 为 absolute 定位，容器须自建定位上下文，
     否则画布锚到最近定位祖先（全屏 scrim）落视口左上 */
  position: relative;
  height: 260px;
  width: 100%;
  border: 1px solid var(--border-hair);
  border-radius: var(--r-md);
  background: var(--bg-inset);
  overflow: hidden;
}
.orb-hint {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--text-faint);
}
</style>
