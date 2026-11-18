import createClient from "openapi-fetch";

import type { components, paths } from "./contract";

/** 同源 API client（openapi-fetch）——类型由 docs/api/openapi.yaml 生成，杜绝手写漂移。 */
export const client = createClient<paths>({ baseUrl: "/api/v1" });

/**
 * text/plain 端点统一按文本读取（openapi-fetch 默认按 JSON 解析，对
 * "#p ..." 纯文本会抛 SyntaxError——走查两笔缺陷同源，读取模式收口于此）。
 * 路径限定契约中 content 为 text/plain 的三个 {id} 端点，类型仍由生成物推导。
 */
export function getText(
  path: "/candidates/{id}/input" | "/history/{id}/input" | "/history/{id}/output",
  id: number,
) {
  return client.GET(path, { params: { path: { id } }, parseAs: "text" });
}

/**
 * 历史批量导出（application/zip 二进制）：按 parseAs blob 取包，
 * 下载落盘与文件名生成由视图层处理（契约 schema 为 binary string，
 * 运行时 Blob 由调用方自断言）。scope 三范围透传（out 输出日志 /
 * chk 资产 / all 全部；缺省 out 向后兼容）。
 */
export function exportOutputs(
  ids: number[],
  scope: "out" | "chk" | "all" = "out",
) {
  return client.POST("/history/export", { body: { ids, scope }, parseAs: "blob" });
}

/**
 * 批量 fchk 导出作业四方法（3.8.0 工具箱 C10）：创建（202 轮询承载，
 * 不设同步快速路径）/ 状态轮询（1s 间隔普通 GET）/ ZIP 下载（blob，
 * 落盘命名由视图层处理）/ 取消。作业 id 为服务端 uuid4 hex。
 */
export function createFchkExportJob(ids: number[]) {
  return client.POST("/history/export/fchk", { body: { ids } });
}

/**
 * cube 批量导出（3.8.0 修订批 C11）：多类型一次请求收单个 ZIP（blob，
 * 落盘命名由面板层与服务端同公式计算）。恰选 1 类走单 kind 端点直下
 * .cube，不入此方法（契约对长度 1 的受理性由后端测试钉死）。
 */
export function generateCubeBatch(
  id: number,
  body: components["schemas"]["CubeBatchRequest"],
) {
  return client.POST("/history/{id}/analysis/cube/batch", {
    params: { path: { id } },
    body,
    parseAs: "blob",
  });
}

export function getFchkExportJob(jobId: string) {
  return client.GET("/history/export/fchk/{job_id}", {
    params: { path: { job_id: jobId } },
  });
}

export function downloadFchkExportJob(jobId: string) {
  return client.GET("/history/export/fchk/{job_id}/download", {
    params: { path: { job_id: jobId } },
    parseAs: "blob",
  });
}

export function cancelFchkExportJob(jobId: string) {
  return client.POST("/history/export/fchk/{job_id}/cancel", {
    params: { path: { job_id: jobId } },
  });
}