#!/usr/bin/env bash
# HQ journal 恢复行为实测（m1-plan §4.2 H4②）。
#
# 用法：scripts/probe_hq_journal.sh [hq路径] [记录输出文件]
# 场景：
#   P1 带 journal 重启 × Running 任务 —— job id 是否延续、是否真的重跑
#   P2 带 journal 重启 × Waiting 任务 —— 恢复后是否只跑一次
#   P3 worker 崩溃 × crash_limit 重试 —— 事件流可观测特征（默认 MaxCrashes(5)）
#   P4 无 journal 重启 × Running 任务 —— 任务与 id 计数是否归零
# 观测手段：副作用文件（任务执行时写入 start 标记行 + 心跳时间戳）+
# REST /jobs、/jobs/{id}、/events（--http-port）。
# 护栏约定：单次 API 失败只记录不中止（无 set -e）；场景内基础设施失败
# 记录「未得出任务结论」后跳到下一场景；结果为一次性实验记录，
# 重跑请换输出文件或先删除旧记录。
set -uo pipefail

HQ_BIN="${1:-./target/release/hq}"
OUT="${2:-/tmp/hq-journal-probe-record.txt}"
WORKDIR="$(dirname "$OUT")"
BASE="http://127.0.0.1:17961"
SD="$WORKDIR/hq-probe-server-dir"
RUNS="$WORKDIR/hq-probe-runs.txt"
SERVER_LOG="$WORKDIR/hq-probe-server.log"
WORKER_LOG="$WORKDIR/hq-probe-worker.log"
API_STATUS=000

mkdir -p "$WORKDIR"
: > "$OUT"

cleanup() { pkill -9 -f "hq --server-dir $SD" 2>/dev/null || true; }
trap cleanup EXIT

log() { echo "$*" | tee -a "$OUT"; }

# ---------------- REST 访问助手（带状态码捕获，失败不中止） ----------------

# api METHOD PATH [JSON_BODY]：成功（HTTP 200）时 body 走 stdout 并返回 0，
# 否则返回非零，API_STATUS 记录 HTTP 状态码（000 = 连接失败）。
api() {
    local method="$1" path="$2" body="${3:-}" out args
    args=(-s --max-time 5 -w $'\n%{http_code}' -X "$method" "$BASE$path")
    [ -n "$body" ] && args+=(-H 'content-type: application/json' -d "$body")
    out=$(curl "${args[@]}" 2>/dev/null) || { API_STATUS=000; return 1; }
    API_STATUS="${out##*$'\n'}"
    printf '%s' "${out%$'\n'*}"
    [ "$API_STATUS" = "200" ]
}

# api_retry TRIES METHOD PATH [BODY]：带重试的 api。
api_retry() {
    local tries="$1"; shift
    local out
    for _ in $(seq 1 "$tries"); do
        if out=$(api "$@"); then printf '%s' "$out"; return 0; fi
        sleep 0.3
    done
    return 1
}

# ---------------- 任务副作用与状态观测 ----------------

start_task_marker() { : > "$RUNS"; }
runs_count() { wc -l < "$RUNS" | tr -d ' '; }
# start 标记行数 = 任务被执行的次数（重跑可直接观测）
starts_count() { grep -c '^start$' "$RUNS" 2>/dev/null || echo 0; }

reset_env() {
    rm -rf "$SD"
    : > "$SERVER_LOG"; : > "$WORKER_LOG"
}

# 摘录 server 日志中恢复/journal 相关行（flush 结论证据）
log_server_restore() {
    grep -iE "state restoration|journal" "$SERVER_LOG" 2>/dev/null | tail -n 8 \
        | sed 's/^/    server: /' | tee -a "$OUT" || true
}

start_server() { # $1 = journal 路径或空（无 journal）
    local args=(--server-dir "$SD" server start --http-port 17961)
    [ -n "${1:-}" ] && args+=(--journal "$1")
    "$HQ_BIN" "${args[@]}" >> "$SERVER_LOG" 2>&1 &
    for _ in $(seq 1 60); do
        api GET /info >/dev/null && return 0
        sleep 0.2
    done
    log "!! server 启动失败（60 次探测未就绪），日志尾部："
    tail -n 5 "$SERVER_LOG" | sed 's/^/    server: /' | tee -a "$OUT"
    return 1
}

start_worker() {
    "$HQ_BIN" --server-dir "$SD" worker start >> "$WORKER_LOG" 2>&1 &
    local out
    for _ in $(seq 1 60); do
        if out=$(api GET /info); then
            if [ "$(WORKER_N="$out" python3 -c 'import json,os;print(json.loads(os.environ["WORKER_N"])["workers"]["running"])')" -ge 1 ]; then
                return 0
            fi
        fi
        sleep 0.3
    done
    log "!! worker 启动失败（60 次探测未就绪），日志尾部："
    tail -n 5 "$WORKER_LOG" | sed 's/^/    worker: /' | tee -a "$OUT"
    return 1
}

kill_process() { # $1 = 匹配子串（server start / worker start）
    pkill -9 -f "hq --server-dir $SD.*$1" 2>/dev/null || true
    sleep 0.5
}

submit_append_task() { # 提交常驻任务：先写一行 start 标记，再每秒心跳；stdout = job id
    local args="${1:-}" body out
    body="{\"args\":[\"bash\",\"-c\",\"date +%s.%N >> $RUNS; echo start >> $RUNS; while true; do date +%s.%N >> $RUNS; sleep 1; done\"],\"cwd\":\"/tmp\"$args}"
    if out=$(api_retry 5 POST /jobs "$body"); then
        SUBMIT_ID=$(SUBMIT_R="$out" python3 -c 'import json,os;print(json.loads(os.environ["SUBMIT_R"])["id"])') && return 0
    fi
    log "!! POST /jobs 失败（status=$API_STATUS）"
    return 1
}

submit_oneshot_task() { # 提交一次性任务；stdout = job id
    local body out
    body="{\"args\":[\"bash\",\"-c\",\"date +%s.%N >> $RUNS; echo start >> $RUNS\"],\"cwd\":\"/tmp\"}"
    if out=$(api_retry 5 POST /jobs "$body"); then
        SUBMIT_ID=$(SUBMIT_R="$out" python3 -c 'import json,os;print(json.loads(os.environ["SUBMIT_R"])["id"])') && return 0
    fi
    log "!! POST /jobs 失败（status=$API_STATUS）"
    return 1
}

job_state() { # $1 = job id；stdout = running/waiting/finished/failed/canceled/missing/error:<code>
    local out
    if ! out=$(api GET "/jobs/$1"); then
        case "$API_STATUS" in
            404) echo "missing" ;;
            *) echo "error:$API_STATUS" ;;
        esac
        return 0
    fi
    TASK_STATS="$out" python3 -c '
import json, os
d = json.loads(os.environ["TASK_STATS"])["info"]["task_stats"]
print("running" if d["running"] else "finished" if d["finished"] else "failed" if d["failed"] else "canceled" if d["canceled"] else "waiting")' 2>/dev/null || echo "parse_error"
}

wait_state() { # $1 = job id, $2 = 期望状态, $3 = 最大轮询次数（默认 60）
    local id="$1" want="$2" tries="${3:-60}" s=""
    for _ in $(seq 1 "$tries"); do
        s=$(job_state "$id")
        [ "$s" = "$want" ] && return 0
        sleep 0.3
    done
    log "!! job $id 未在超时内进入 $want（当前：$s）"
    return 1
}

cancel_job() { # 尽力取消，失败只记录
    if ! api POST "/jobs/$1/cancel" >/dev/null; then
        log "    （取消 job $1 失败：status=$API_STATUS）"
    fi
}

# ---------------- P1：带 journal 重启 × Running ----------------

phase_p1() {
    local JOURNAL="$WORKDIR/hq-probe.journal"
    log ""
    log "## P1 带 journal 重启 × Running 任务"
    reset_env; start_task_marker
    start_server "$JOURNAL" || { log "P1 结论：环境失败（server 未就绪），未得出任务结论"; return 1; }
    start_worker || { log "P1 结论：环境失败（worker 未就绪），未得出任务结论"; return 1; }

    submit_append_task || { log "P1 结论：环境失败（提交失败），未得出任务结论"; return 1; }
    local J1="$SUBMIT_ID"
    wait_state "$J1" running || { log "P1 结论：环境失败（任务未运行），未得出任务结论"; return 1; }
    sleep 3
    local BEFORE="$(runs_count)" BEFORE_STARTS="$(starts_count)"
    log "重启前：job=$J1 running，副作用文件 $BEFORE 行（start 标记 $BEFORE_STARTS 次）"

    kill_process "server start"
    log "server 已 kill -9（等待 journal_flush_period 周期之外：提交路径已带 flush，见实测）"

    start_server "$JOURNAL" || { log "P1 结论：环境失败（重启后 server 未就绪），未得出任务结论"; return 1; }
    log_server_restore

    # 关键观测 1：恢复后 GET /jobs 是否还有该任务（flush 缺失 → 列表为空）
    local jobs_out="" jobs_n
    if ! jobs_out=$(api GET /jobs); then
        log "P1 结论：重启后 GET /jobs 请求失败（status=$API_STATUS），未得出任务结论"
        return 1
    fi
    jobs_n=$(JOBS_R="$jobs_out" python3 -c 'import json,os;print(len(json.loads(os.environ["JOBS_R"])))')
    if [ "$jobs_n" -eq 0 ]; then
        log "P1 结论：重启后 GET /jobs 为空 —— Submit 事件未落盘（journal flush 缺口），任务在恢复中丢失"
        return 1
    fi
    local S1="$(job_state "$J1")"
    log "重启后（worker 未连）：job=$J1 状态 $S1（id 延续自 journal）"

    start_worker || { log "P1 结论：环境失败（重启后 worker 未就绪）"; return 1; }
    wait_state "$J1" running 100 || true
    sleep 3
    local AFTER="$(runs_count)" AFTER_STARTS="$(starts_count)"
    if [ "$AFTER_STARTS" -gt "$BEFORE_STARTS" ]; then
        log "P1 结论：job=$J1 同 id 恢复且 start 标记 $BEFORE_STARTS → $AFTER_STARTS 次 —— 任务被重新执行（重跑，非续跑）"
    else
        log "P1 结论：job=$J1 同 id 恢复，start 标记无新增（$AFTER_STARTS 次）—— 未观测到重跑"
    fi

    submit_append_task || true
    local NEWJOB="${SUBMIT_ID:-none}"
    log "重启后新提交 job id=$NEWJOB（> $J1 即 id 计数延续）"
    cancel_job "$J1"; cancel_job "$NEWJOB"
    sleep 1
    kill_process "worker start"; kill_process "server start"
    return 0
}

# ---------------- P2：带 journal 重启 × Waiting ----------------

phase_p2() {
    local JOURNAL="$WORKDIR/hq-probe.journal"
    log ""
    log "## P2 带 journal 重启 × Waiting 任务"
    reset_env; start_task_marker
    start_server "$JOURNAL" || { log "P2 结论：环境失败（server 未就绪），未得出任务结论"; return 1; }

    submit_oneshot_task || { log "P2 结论：环境失败（提交失败），未得出任务结论"; return 1; }
    local WJ="$SUBMIT_ID"
    sleep 1
    log "无 worker 提交 job=$WJ（状态 $(job_state "$WJ")），副作用文件 $(runs_count) 行"
    kill_process "server start"
    start_server "$JOURNAL" || { log "P2 结论：环境失败（重启后 server 未就绪），未得出任务结论"; return 1; }
    log_server_restore
    log "重启后（worker 未连）：job=$WJ 状态 $(job_state "$WJ")，GET /jobs 条目数 $(api GET /jobs >/dev/null && echo ok || echo fail)"
    start_worker || { log "P2 结论：环境失败（重启后 worker 未就绪）"; return 1; }
    if wait_state "$WJ" finished 100; then
        sleep 1
        log "P2 结论：恢复后 job=$WJ 状态 finished，start 标记 $(starts_count) 次（=1 则恰好只执行一次）"
    else
        log "P2 结论：恢复后 job=$WJ 未能到达 finished（当前 $(job_state "$WJ")）"
    fi
    kill_process "worker start"; kill_process "server start"
    return 0
}

# ---------------- P3：worker 崩溃 × crash_limit 重试 ----------------

phase_p3() {
    local JOURNAL="$WORKDIR/hq-probe.journal"
    log ""
    log "## P3 worker 崩溃 × crash_limit 重试（事件流可观测特征）"
    reset_env; start_task_marker
    start_server "$JOURNAL" || { log "P3 结论：环境失败（server 未就绪），未得出任务结论"; return 1; }
    start_worker || { log "P3 结论：环境失败（worker 未就绪），未得出任务结论"; return 1; }

    local EV="$WORKDIR/hq-probe-events.txt"
    : > "$EV"
    curl -sN --max-time 120 "$BASE/events" > "$EV" &
    local EVPID=$!
    sleep 1

    submit_append_task || { kill "$EVPID" 2>/dev/null; log "P3 结论：环境失败（提交失败），未得出任务结论"; return 1; }
    local CJ="$SUBMIT_ID"
    wait_state "$CJ" running || { kill "$EVPID" 2>/dev/null; log "P3 结论：环境失败（任务未运行）"; return 1; }
    sleep 1.5
    local i
    for i in 1 2 3 4 5; do
        kill_process "worker start"   # 杀 worker → 在跑任务按 crash_limit 自动重新入队
        start_worker && wait_state "$CJ" running 100
        sleep 1.5
    done
    kill_process "worker start"      # 第 6 次失联 → 超出 MaxCrashes(5) → 任务最终失败
    local s="" ok=0
    for _ in $(seq 1 60); do
        s=$(job_state "$CJ")
        [ "$s" = "failed" ] && ok=1 && break
        sleep 0.5
    done
    kill "$EVPID" 2>/dev/null || true; wait "$EVPID" 2>/dev/null || true
    if [ "$ok" -eq 1 ]; then
        log "P3 结论：第 6 次失联后 job=$CJ 进入 failed（超出 MaxCrashes），start 标记 $(starts_count) 次（≥6 即每次重试都真执行）"
    else
        log "P3 结论：job=$CJ 未能到达 failed（当前：$s）——重试语义待人工核查"
    fi
    log "事件流中出现的关键帧："
    grep -E "^event: (worker_lost|tasks_aborted|task_started|task_failed)" "$EV" 2>/dev/null \
        | sort | uniq -c | sed 's/^/  /' | tee -a "$OUT" || log "  （事件流无匹配帧）"
    kill_process "server start"
    return 0
}

# ---------------- P4：无 journal 重启 × Running ----------------

phase_p4() {
    log ""
    log "## P4 无 journal 重启 × Running 任务"
    reset_env; start_task_marker
    start_server "" || { log "P4 结论：环境失败（server 未就绪），未得出任务结论"; return 1; }
    start_worker || { log "P4 结论：环境失败（worker 未就绪），未得出任务结论"; return 1; }

    submit_append_task || { log "P4 结论：环境失败（提交失败），未得出任务结论"; return 1; }
    local NJ="$SUBMIT_ID"
    wait_state "$NJ" running || { log "P4 结论：环境失败（任务未运行）"; return 1; }
    kill_process "server start"
    start_server "" || { log "P4 结论：环境失败（重启后 server 未就绪），未得出任务结论"; return 1; }
    start_worker || true
    sleep 1.5
    local jobs_out="" jobs_n
    if jobs_out=$(api GET /jobs); then
        jobs_n=$(JOBS_R="$jobs_out" python3 -c 'import json,os;print(len(json.loads(os.environ["JOBS_R"])))')
    else
        jobs_n="请求失败($API_STATUS)"
    fi
    log "重启后 job 列表条目数：$jobs_n"
    submit_append_task || true
    local NJ2="${SUBMIT_ID:-none}"
    log "重启后首个新 job id=$NJ2（无 journal → id 从头计数，≤ $NJ 即归零）"
    cancel_job "$NJ2"
    sleep 1
    kill_process "worker start"; kill_process "server start"
    return 0
}

log "# HQ journal 恢复实测记录（$(date -Is)，hq=$(readlink -f "$HQ_BIN")）"
phase_p1 || true
phase_p2 || true
phase_p3 || true
phase_p4 || true
log ""
log "# 实测结束"
echo "记录已写入 $OUT"
