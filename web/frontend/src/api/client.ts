import createClient from "openapi-fetch";

import type { paths } from "./contract";

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
 * 运行时 Blob 由调用方自断言）。
 */
export function exportOutputs(ids: number[]) {
  return client.POST("/history/export", { body: { ids }, parseAs: "blob" });
}