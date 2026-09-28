/**
 * useSortPref — 列表排序规则持久化组合式（视图偏好域 GET/PUT /ui-preferences）。
 *
 * 初始回落默认值；挂载后拉取已持久化值（值域内才采纳）。用户变更即时 PUT
 * 写回（合并 upsert，单键），服务重启/更新/断联后不回默认值。读取或保存
 * 失败一律静默降级（console.warn，不弹提示），下次进入页面重拉校对。
 *
 * key 支持动态（Ref）：历史页与归档页同组件复用实例（RouterView 无 key），
 * 路由切换时键切换并重拉对应值；回填触发的变更不写回（hydrating 屏蔽，
 * nextTick 后解除）。
 */
import { isRef, nextTick, onMounted, ref, toValue, watch, type Ref } from "vue";

import { client } from "@/api/client";

export function useSortPref<K extends string>(
  key: Ref<string> | string,
  fallback: K,
  allowed: readonly K[],
): Ref<K> {
  const value = ref(fallback) as Ref<K>;
  let hydrating = true; // 远端回填触发的变更不写回

  async function load(k: string) {
    try {
      const { data } = await client.GET("/ui-preferences");
      const saved = data?.prefs?.[k];
      if (typeof saved === "string"
          && (allowed as readonly string[]).includes(saved)) {
        value.value = saved as K;
      }
    } catch (e) {
      console.warn("ui-preferences 读取失败，沿用当前排序", e);
    } finally {
      await nextTick();
      hydrating = false;
    }
  }

  onMounted(() => load(toValue(key)));
  if (isRef(key)) {
    watch(key, (k) => {
      hydrating = true; // 键切换回填期间不写回
      void load(k);
    });
  }

  watch(value, (v) => {
    if (hydrating) return;
    const k = toValue(key);
    client
      .PUT("/ui-preferences", { body: { prefs: { [k]: v } } })
      .catch((e) => console.warn("ui-preferences 保存失败", e));
  });

  return value;
}
