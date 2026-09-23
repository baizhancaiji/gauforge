import createClient from "openapi-fetch";

import type { paths } from "./contract";

/** 同源 API client（openapi-fetch）——类型由 docs/api/openapi.yaml 生成，杜绝手写漂移。 */
export const client = createClient<paths>({ baseUrl: "/api/v1" });