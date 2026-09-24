#!/usr/bin/env bash
# HQ 内嵌 HTTP API 冒烟脚本（m1-plan §4.2 H2）。
#
# 用法：scripts/smoke_hq_http.sh [hq路径] [HTTP端口]
# 流程：临时 server-dir 启动 server（--http-port）+ 1 个 worker，
#       逐端点 curl 断言，并做「同一 job CLI 与 HTTP 查询结果一致」抽查。
set -euo pipefail

HQ_BIN="${1:-./target/release/hq}"
HTTP_PORT="${2:-17931}"
SD="$(mktemp -d /tmp/hq-http-smoke.XXXXXX)"
LOG="$SD/server.log"

cleanup() {
    "$HQ_BIN" --server-dir "$SD" server stop >/dev/null 2>&1 || true
    wait 2>/dev/null || true
    rm -rf "$SD"
}
trap cleanup EXIT

echo "== 启动 server（http://127.0.0.1:$HTTP_PORT）与 worker =="
"$HQ_BIN" --server-dir "$SD" server start --http-port "$HTTP_PORT" >"$LOG" 2>&1 &
for _ in $(seq 1 50); do
    curl -sf "http://127.0.0.1:$HTTP_PORT/info" >/dev/null 2>&1 && break
    sleep 0.2
done
"$HQ_BIN" --server-dir "$SD" worker start >/dev/null 2>&1 &
for _ in $(seq 1 50); do
    n=$(curl -sf "http://127.0.0.1:$HTTP_PORT/info" | python3 -c 'import json,sys; print(json.load(sys.stdin)["workers"]["running"])') && [ "$n" -ge 1 ] && break
    sleep 0.2
done

BASE="http://127.0.0.1:$HTTP_PORT"

echo "== GET /info =="
curl -sf "$BASE/info" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["version"] and d["workers"]["running"] >= 1, d; print("  ✓ version=%s workers=%d" % (d["version"], d["workers"]["running"]))'

echo "== POST /jobs（sleep 2）=="
JOB=$(curl -sf -X POST "$BASE/jobs" -H 'content-type: application/json' \
    -d '{"args":["/bin/sleep","2"],"cwd":"/tmp","resources":{"cpus":1,"mem_mib":64},"time_limit_s":60}')
JID=$(echo "$JOB" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "  ✓ 提交成功 id=$JID name=$(echo "$JOB" | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')"

echo "== 双路一致：GET /jobs/$JID vs hq job info --output-mode json =="
sleep 1
HTTP_JOB=$(curl -sf "$BASE/jobs/$JID")
CLI_JOB=$("$HQ_BIN" --server-dir "$SD" --output-mode json job info "$JID" 2>/dev/null)
python3 - "$HTTP_JOB" "$CLI_JOB" <<'PYEOF'
import json, sys
http_job = json.loads(sys.argv[1])
cli_jobs = json.loads(sys.argv[2])
same = [j for j in cli_jobs if str(j["info"]["id"]) == str(http_job["info"]["id"])]
assert same, f"CLI 结果无对应 job: {cli_jobs}"
assert http_job == same[0], "HTTP 详情与 CLI 详情不一致"
print("  ✓ 详情逐字段一致（含 info/submits/tasks 全量）")
PYEOF

echo "== GET /jobs?ids=（批量）=="
curl -sf "$BASE/jobs?ids=$JID" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert isinstance(d, list) and len(d) == 1, d; print("  ✓ 批量返回 1 条")'

echo "== GET /workers =="
curl -sf "$BASE/workers" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert isinstance(d, list) and len(d) >= 1, d; assert d[0]["configuration"]["hostname"], d[0]; print("  ✓ worker", d[0]["id"], d[0]["configuration"]["hostname"])'

echo "== POST /jobs/$JID/cancel =="
curl -sf -X POST "$BASE/jobs/$JID/cancel" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["id"], d; print("  ✓ 取消请求受理 id=%s" % d["id"])'

echo "== GET /jobs/$JID（取消后 canceled 计数）=="
sleep 1
curl -sf "$BASE/jobs/$JID" | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["info"]["task_stats"]; assert s["canceled"] >= 1 or s["finished"] >= 1, d; print("  ✓ 终态确认:", s)'

echo "== 错误路径：GET /jobs/999999 → 404 =="
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/jobs/999999")
[ "$code" = "404" ] || { echo "  ✗ 期望 404 实际 $code"; exit 1; }
echo "  ✓ 404"

echo "== 错误路径：POST /jobs 空 args → 422 =="
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/jobs" -H 'content-type: application/json' -d '{"args":[]}')
[ "$code" = "422" ] || { echo "  ✗ 期望 422 实际 $code"; exit 1; }
echo "  ✓ 422"

echo "全部冒烟通过 ✓"
