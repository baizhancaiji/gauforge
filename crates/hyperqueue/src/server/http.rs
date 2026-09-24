//! HQ server 内嵌 HTTP/SSE 层（m1-plan §2.1、§4.2 H1–H3）。
//!
//! 仅在 `hq server start --http-port <P>` 时启动（默认关，HQ 行为零变化），
//! 一律绑 `127.0.0.1`；唯一预期消费者是 g16web 后端，无认证（回环即边界）。
//!
//! server 内存态（`StateRef`/`Senders`）基于 `Rc` 不可跨线程，故 handler 不直接
//! 持有状态，而是经 [`HttpQuery`] 通道请求**本地桥接任务**（随 server 的
//! `LocalSet` 运行）代为调用 server 侧命令处理函数——与 RPC 消息循环共用同一
//! 实现，保证 HTTP 与 CLI `--output-mode json` 双路一致。
use axum::Router;
use axum::extract::{Path, Query, State};
use axum::http::StatusCode;
use axum::response::sse::{Event as SseFrame, KeepAlive, Sse};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use futures::stream::Stream;
use bstr::BString;
use serde::Deserialize;
use serde_json::{Value, json};
use std::collections::HashMap;
use std::path::PathBuf;
use std::time::Duration;
use tako::resources::{AllocationRequest, CPU_RESOURCE_NAME, ResourceAmount};
use tako::{Map, UserPriority};
use tokio::sync::mpsc::{UnboundedReceiver, UnboundedSender, unbounded_channel};
use tokio::sync::oneshot;

use crate::client::commands::submit::command::{DEFAULT_STDERR_PATH, DEFAULT_STDOUT_PATH};
use crate::client::output::json::{format_job_detail, format_job_info, format_worker_info};
use crate::common::arraydef::IntArray;
use crate::server::event::Event;
use crate::server::event::payload::EventPayload;
use crate::server::event::streamer::{EventFilter, EventFilterFlags};
use crate::server::Senders;
use crate::server::client::{
    compute_job_detail, compute_job_info, handle_get_list, handle_job_cancel, handle_submit,
};
use crate::server::state::StateRef;
use crate::transfer::messages::{
    IdSelector, JobDescription, JobSubmitDescription, JobTaskDescription,
    PinMode, SubmitRequest, TaskDescription, TaskKind, TaskKindProgram, ToClientMessage,
};
use tako::gateway::{CrashLimit, ResourceRequest, ResourceRequestEntry, ResourceRequestVariants};
use tako::program::{FileOnCloseBehavior, ProgramDefinition, StdioDef};

/// HTTP 层 → 本地桥接任务的请求（字段均 `Send`，通道可跨线程）。
pub(crate) enum HttpQuery {
    InfoReply { reply: oneshot::Sender<Reply> },
    Submit { request: SubmitRequest, reply: oneshot::Sender<Reply> },
    JobsInfo { selector: IdSelector, reply: oneshot::Sender<Reply> },
    /// 单 job 查询：缺失时桥接侧直接回 404
    JobInfo { job_id: u32, reply: oneshot::Sender<Reply> },
    Cancel { job_id: u32, reply: oneshot::Sender<Reply> },
    Workers { reply: oneshot::Sender<Reply> },
    /// 订阅全类事件流（薄桥接：不缓存不重放，断线由 REST 对账补齐）
    Subscribe { reply: oneshot::Sender<UnboundedReceiver<Event>> },
}

impl HttpQuery {
    fn info(reply: oneshot::Sender<Reply>) -> Self {
        HttpQuery::InfoReply { reply }
    }
}

/// 桥接任务应答：成功载荷或（状态码 + 统一 Error 格式）。
pub(crate) struct Reply(pub Result<Value, (StatusCode, Value)>);

impl Reply {
    fn ok(value: Value) -> Self {
        Reply(Ok(value))
    }
    fn err(status: StatusCode, message: impl Into<String>) -> Self {
        Reply(Err((status, json!({ "error": message.into() }))))
    }
}

/// axum 共享状态：仅持请求通道（满足 Router 的 `Send + Sync` 约束）。
#[derive(Clone)]
pub(crate) struct HttpState {
    query_tx: UnboundedSender<HttpQuery>,
}

impl HttpState {
    pub(crate) fn new(query_tx: UnboundedSender<HttpQuery>) -> Self {
        HttpState { query_tx }
    }

    async fn ask(&self, make: impl FnOnce(oneshot::Sender<Reply>) -> HttpQuery) -> Response {
        let (reply, rx) = oneshot::channel();
        if self.query_tx.send(make(reply)).is_err() {
            return service_unavailable();
        }
        match rx.await {
            Ok(Reply(Ok(value))) => (StatusCode::OK, axum::Json(value)).into_response(),
            Ok(Reply(Err((status, body)))) => (status, axum::Json(body)).into_response(),
            Err(_) => service_unavailable(),
        }
    }
}

pub(crate) fn router(state: HttpState) -> Router {
    Router::new()
        .route("/info", get(get_info))
        .route("/jobs", post(post_job).get(get_jobs))
        .route("/jobs/{id}", get(get_job))
        .route("/jobs/{id}/cancel", post(post_job_cancel))
        .route("/workers", get(get_workers))
        .route("/events", get(get_events))
        .with_state(state)
}

/// 启动本地桥接任务（必须在 server 的 `LocalSet` 上下文中调用），
/// 返回供 axum handler 使用的请求通道。
pub(crate) fn spawn_bridge(state_ref: StateRef, senders: Senders) -> UnboundedSender<HttpQuery> {
    let (query_tx, query_rx) = unbounded_channel();
    tokio::task::spawn_local(bridge_task(state_ref, senders, query_rx));
    query_tx
}

async fn bridge_task(
    state_ref: StateRef,
    senders: Senders,
    mut query_rx: UnboundedReceiver<HttpQuery>,
) {
    while let Some(query) = query_rx.recv().await {
        match query {
            HttpQuery::InfoReply { reply } => {
                let _ = reply.send(Reply::ok(compute_info(&state_ref)));
            }
            HttpQuery::Submit { request, reply } => {
                let response = handle_submit_reply(&state_ref, &senders, request);
                // 与 RPC 路径对齐（server/client/mod.rs submit 分支）：成功后立即
                // flush journal，消除 journal_flush_period（默认 30s）窗口内
                // kill -9 丢失 Submit 事件的恢复缺口（H4 实测结论，§2.4）
                if response.0.is_ok() {
                    senders.events.flush_journal().await;
                }
                let _ = reply.send(response);
            }
            HttpQuery::JobsInfo { selector, reply } => {
                let _ = reply.send(handle_jobs_info_reply(&state_ref, &selector));
            }
            HttpQuery::JobInfo { job_id, reply } => {
                let _ = reply.send(handle_job_info_reply(&state_ref, job_id));
            }
            HttpQuery::Cancel { job_id, reply } => {
                let response = handle_cancel_reply(&state_ref, &senders, job_id).await;
                // 与 RPC 路径对齐（server/client/mod.rs cancel 分支），理由同 Submit
                if response.0.is_ok() {
                    senders.events.flush_journal().await;
                }
                let _ = reply.send(response);
            }
            HttpQuery::Workers { reply } => {
                let _ = reply.send(handle_workers_reply(&state_ref));
            }
            HttpQuery::Subscribe { reply } => {
                let (tx, rx) = unbounded_channel();
                senders.events.register_listener(http_event_filter(), tx);
                let _ = reply.send(rx);
            }
        }
    }
}

// ---------------- 桥接任务侧：调用 server 内部处理并转换为 HTTP 载荷 ----------------

/// `GET /info`：server 版本/uptime/worker 概览（§2.1；字段对齐 `hq info --json`）。
fn compute_info(state_ref: &StateRef) -> Value {
    let guard = state_ref.get();
    let info = guard.server_info();
    let workers = guard.get_workers();
    let running = workers
        .values()
        .filter(|worker| worker.make_info(None).ended.is_none())
        .count();
    let uptime = chrono::Utc::now().signed_duration_since(info.start_date);
    json!({
        "server_uid": info.server_uid,
        "version": info.version,
        "start_date": info.start_date,
        "uptime_seconds": uptime.num_seconds(),
        "pid": info.pid,
        "client_host": info.client_host,
        "worker_host": info.worker_host,
        "client_port": info.client_port,
        "worker_port": info.worker_port,
        "journal_path": info.journal_path,
        "workers": {
            "total": workers.len(),
            "running": running,
        },
    })
}

fn handle_submit_reply(
    state_ref: &StateRef,
    senders: &Senders,
    request: SubmitRequest,
) -> Reply {
    // 与 CLI `hq submit` 共用 server 侧处理（§4.2 H2 双路一致）
    match handle_submit(state_ref, senders, request) {
        ToClientMessage::SubmitResponse(crate::transfer::messages::SubmitResponse::Ok {
            job, ..
        }) => Reply::ok(json!({ "id": job.info.id, "name": job.info.name })),
        ToClientMessage::SubmitResponse(other) => {
            Reply::err(StatusCode::UNPROCESSABLE_ENTITY, format!("{other:?}"))
        }
        ToClientMessage::Error(message) => Reply::err(StatusCode::BAD_REQUEST, message),
        other => Reply::err(StatusCode::INTERNAL_SERVER_ERROR, format!("unexpected reply: {other:?}")),
    }
}

fn handle_jobs_info_reply(state_ref: &StateRef, selector: &IdSelector) -> Reply {
    match compute_job_info(state_ref, selector, false) {
        ToClientMessage::JobInfoResponse(response) => {
            let jobs: Vec<Value> = response.jobs.iter().map(format_job_info).collect();
            Reply::ok(json!(jobs))
        }
        other => Reply::err(StatusCode::INTERNAL_SERVER_ERROR, format!("unexpected reply: {other:?}")),
    }
}

/// `GET /jobs/{id}`：job 详情，JSON 形状与 `hq job info <id> --output-mode json`
/// 的数组元素一致；缺失 → 404。
fn handle_job_info_reply(state_ref: &StateRef, job_id: u32) -> Reply {
    let selector = IdSelector::Specific(IntArray::from_id(job_id));
    match compute_job_detail(
        state_ref,
        selector,
        Some(crate::transfer::messages::TaskSelector {
            id_selector: crate::transfer::messages::TaskIdSelector::All,
            status_selector: crate::transfer::messages::TaskStatusSelector::All,
        }),
    ) {
        ToClientMessage::JobDetailResponse(response) => {
            match response.details.into_iter().find_map(|(_, detail)| detail) {
                Some(detail) => {
                    Reply::ok(format_job_detail(detail, &response.server_uid))
                }
                None => Reply::err(StatusCode::NOT_FOUND, format!("job {job_id} not found")),
            }
        }
        other => Reply::err(StatusCode::INTERNAL_SERVER_ERROR, format!("unexpected reply: {other:?}")),
    }
}

async fn handle_cancel_reply(state_ref: &StateRef, senders: &Senders, job_id: u32) -> Reply {
    let selector = IdSelector::Specific(IntArray::from_id(job_id));
    match handle_job_cancel(state_ref, senders, &selector, &None).await {
        ToClientMessage::CancelJobResponse(responses) => {
            let Some((_, response)) = responses.first() else {
                return Reply::err(StatusCode::INTERNAL_SERVER_ERROR, "empty cancel response");
            };
            use crate::transfer::messages::CancelJobResponse as C;
            match response {
                C::Canceled(canceled, already_finished) => Reply::ok(json!({
                    "id": job_id,
                    "canceled_tasks": canceled.len(),
                    "already_finished": already_finished,
                })),
                C::InvalidJob => {
                    Reply::err(StatusCode::NOT_FOUND, format!("job {job_id} not found"))
                }
                other => Reply::err(StatusCode::INTERNAL_SERVER_ERROR, format!("{other:?}")),
            }
        }
        ToClientMessage::Error(message) => Reply::err(StatusCode::BAD_REQUEST, message),
        other => Reply::err(StatusCode::INTERNAL_SERVER_ERROR, format!("unexpected reply: {other:?}")),
    }
}

fn handle_workers_reply(state_ref: &StateRef) -> Reply {
    match handle_get_list(state_ref, true) {
        ToClientMessage::GetListResponse(response) => {
            let workers: Vec<Value> = response.workers.into_iter().map(format_worker_info).collect();
            Reply::ok(json!(workers))
        }
        other => Reply::err(StatusCode::INTERNAL_SERVER_ERROR, format!("unexpected reply: {other:?}")),
    }
}

// ---------------- axum handler 侧 ----------------

async fn get_info(State(state): State<HttpState>) -> Response {
    state.ask(HttpQuery::info).await
}

/// `POST /jobs` 请求体（§2.1：program argv、cwd、env、stdout/stderr、resources）。
#[derive(Deserialize)]
struct HttpSubmit {
    /// program argv（含 argv[0]）
    args: Vec<String>,
    #[serde(default)]
    cwd: Option<String>,
    #[serde(default)]
    env: HashMap<String, String>,
    #[serde(default)]
    stdout: Option<String>,
    #[serde(default)]
    stderr: Option<String>,
    #[serde(default)]
    name: Option<String>,
    #[serde(default)]
    resources: Option<HttpResources>,
    /// 0 = 不设上限（§8.7 定稿：默认不设 time_limit）
    #[serde(default)]
    time_limit_s: u64,
}

#[derive(Deserialize)]
struct HttpResources {
    #[serde(default)]
    cpus: Option<u32>,
    #[serde(default)]
    mem_mib: Option<u32>,
}

async fn post_job(
    State(state): State<HttpState>,
    axum::Json(payload): axum::Json<HttpSubmit>,
) -> Response {
    if payload.args.is_empty() {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            axum::Json(json!({ "error": "args must not be empty" })),
        )
            .into_response();
    }
    let request = build_submit_request(payload);
    state.ask(|reply| HttpQuery::Submit { request, reply }).await
}

fn build_submit_request(payload: HttpSubmit) -> SubmitRequest {
    let name = payload.name.unwrap_or_else(|| {
        PathBuf::from(&payload.args[0])
            .file_name()
            .and_then(|s| s.to_str().map(str::to_string))
            .unwrap_or_else(|| "job".to_string())
    });
    let args: Vec<BString> = payload.args.into_iter().map(BString::from).collect();

    let mut env: Map<BString, BString> = Map::new();
    for (key, value) in payload.env {
        env.insert(BString::from(key), BString::from(value));
    }

    let file_stdio = |path: Option<String>, default: &str| match path {
        Some(p) => StdioDef::File {
            path: PathBuf::from(p),
            on_close: FileOnCloseBehavior::None,
        },
        None => StdioDef::File {
            path: PathBuf::from(default),
            on_close: FileOnCloseBehavior::None,
        },
    };

    let program = ProgramDefinition {
        args,
        env,
        stdout: file_stdio(payload.stdout, DEFAULT_STDOUT_PATH),
        stderr: file_stdio(payload.stderr, DEFAULT_STDERR_PATH),
        stdin: Vec::new(),
        cwd: payload
            .cwd
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("%{SUBMIT_DIR}")),
    };

    // 资源双账第二账（roadmap §2.1）：cpus 紧凑分配、mem 以 MiB 计；
    // 未指定时与 CLI 相同，默认 cpus=1
    let mut resources: Vec<ResourceRequestEntry> = Vec::new();
    if let Some(rq) = &payload.resources {
        if let Some(cpus) = rq.cpus {
            resources.push(ResourceRequestEntry {
                resource: CPU_RESOURCE_NAME.to_string(),
                policy: AllocationRequest::Compact(ResourceAmount::new_units(cpus)),
            });
        }
        if let Some(mem_mib) = rq.mem_mib {
            resources.push(ResourceRequestEntry {
                resource: "mem".to_string(),
                policy: AllocationRequest::Compact(ResourceAmount::new_units(mem_mib)),
            });
        }
    }
    if resources.is_empty() {
        resources.push(ResourceRequestEntry {
            resource: CPU_RESOURCE_NAME.to_string(),
            policy: AllocationRequest::Compact(ResourceAmount::new_units(1)),
        });
    }
    let resource_rq =
        ResourceRequestVariants::new(smallvec::smallvec![ResourceRequest {
            n_nodes: 1,
            min_time: Duration::ZERO,
            resources: resources.into(),
            weight: Default::default(),
        }]);

    let time_limit = (payload.time_limit_s > 0).then(|| Duration::from_secs(payload.time_limit_s));

    SubmitRequest {
        job_desc: JobDescription {
            name,
            max_fails: None,
        },
        submit_desc: JobSubmitDescription {
            task_desc: JobTaskDescription::Array {
                ids: IntArray::from_id(0),
                entries: None,
                task_desc: TaskDescription {
                    kind: TaskKind::ExternalProgram(TaskKindProgram {
                        program,
                        pin_mode: PinMode::None,
                        task_dir: false,
                    }),
                    priority: UserPriority::new(0),
                    time_limit,
                    crash_limit: CrashLimit::default(),
                },
                resource_rq,
            },
            submit_dir: std::env::current_dir().unwrap_or_default(),
            stream_path: None,
        },
        job_id: None,
    }
}

/// `GET /jobs?ids=1,2`：批量状态（缺省 = 全量，对账与轮询用）。
#[derive(Deserialize)]
struct JobsQuery {
    ids: Option<String>,
}

async fn get_jobs(
    State(state): State<HttpState>,
    Query(query): Query<JobsQuery>,
) -> Response {
    let selector = match &query.ids {
        None => IdSelector::All,
        Some(ids) => match ids.parse::<IntArray>() {
            Ok(array) => IdSelector::Specific(array),
            Err(error) => {
                return (
                    StatusCode::UNPROCESSABLE_ENTITY,
                    axum::Json(json!({ "error": format!("invalid ids: {error}") })),
                )
                    .into_response();
            }
        },
    };
    state.ask(|reply| HttpQuery::JobsInfo { selector, reply }).await
}

async fn get_job(State(state): State<HttpState>, Path(id): Path<u32>) -> Response {
    state.ask(|reply| HttpQuery::JobInfo { job_id: id, reply }).await
}

async fn post_job_cancel(State(state): State<HttpState>, Path(id): Path<u32>) -> Response {
    state.ask(|reply| HttpQuery::Cancel { job_id: id, reply }).await
}

async fn get_workers(State(state): State<HttpState>) -> Response {
    state.ask(|reply| HttpQuery::Workers { reply }).await
}

/// M1 订阅 job/task/worker/server 四域；Allocation\* 与 WorkerOverview 不在内
/// （单机本地模式不产生，§8.8 事件桥接定稿）。
fn http_event_filter() -> EventFilter {
    let mut flags = EventFilterFlags::empty();
    flags.insert(EventFilterFlags::JOB_EVENTS);
    flags.insert(EventFilterFlags::TASK_EVENTS);
    flags.insert(EventFilterFlags::WORKER_EVENTS);
    flags.insert(EventFilterFlags::NOTIFY_EVENTS);
    EventFilter::new(None, flags)
}

/// HQ 事件 →（变体名 snake_case，单行 JSON 载荷 `{time, 字段…}`）。
/// `Submit.serialized_desc` 为 bincode 字节，不透传（g16web 自持提交内容）。
fn event_to_frame(event: &Event) -> (&'static str, serde_json::Value) {
    let payload = &event.payload;
    match payload {
        EventPayload::WorkerConnected(worker_id, configuration) => (
            "worker_connected",
            json!({ "worker_id": worker_id, "configuration": configuration }),
        ),
        EventPayload::WorkerLost(worker_id, reason) => (
            "worker_lost",
            json!({ "worker_id": worker_id, "reason": reason }),
        ),
        EventPayload::WorkerOverviewReceived(overview) => (
            "worker_overview_received",
            json!({ "overview": overview }),
        ),
        EventPayload::Submit { job_id, closed_job, .. } => (
            "submit",
            json!({ "job_id": job_id, "closed_job": closed_job }),
        ),
        EventPayload::JobCompleted(job_id) => (
            "job_completed",
            json!({ "job_id": job_id }),
        ),
        EventPayload::JobOpen(job_id, desc) => (
            "job_open",
            json!({ "job_id": job_id, "name": desc.name, "max_fails": desc.max_fails }),
        ),
        EventPayload::JobClose(job_id) => (
            "job_close",
            json!({ "job_id": job_id }),
        ),
        EventPayload::JobIdle(job_id) => (
            "job_idle",
            json!({ "job_id": job_id }),
        ),
        EventPayload::JobCancel { job_id, cancel_reason } => (
            "job_cancel",
            json!({ "job_id": job_id, "cancel_reason": cancel_reason }),
        ),
        EventPayload::TaskStarted { task_id, instance_id, worker_ids, rv_id } => (
            "task_started",
            json!({ "task_id": task_id, "instance_id": instance_id, "worker_ids": worker_ids, "rv_id": rv_id }),
        ),
        EventPayload::TaskFinished { task_id } => (
            "task_finished",
            json!({ "task_id": task_id }),
        ),
        EventPayload::TaskFailed { task_id, error } => (
            "task_failed",
            json!({ "task_id": task_id, "error": error }),
        ),
        EventPayload::TasksCanceled { task_ids } => (
            "tasks_canceled",
            json!({ "task_ids": task_ids }),
        ),
        EventPayload::TasksAborted { task_ids } => (
            "tasks_aborted",
            json!({ "task_ids": task_ids }),
        ),
        EventPayload::AllocationQueueCreated(queue_id, parameters) => (
            "allocation_queue_created",
            json!({ "queue_id": queue_id, "parameters": parameters }),
        ),
        EventPayload::AllocationQueueRemoved(queue_id) => (
            "allocation_queue_removed",
            json!({ "queue_id": queue_id }),
        ),
        EventPayload::AllocationQueued { queue_id, allocation_id, worker_count } => (
            "allocation_queued",
            json!({ "queue_id": queue_id, "allocation_id": allocation_id, "worker_count": worker_count }),
        ),
        EventPayload::AllocationStarted(queue_id, allocation_id) => (
            "allocation_started",
            json!({ "queue_id": queue_id, "allocation_id": allocation_id }),
        ),
        EventPayload::AllocationFinished(queue_id, allocation_id) => (
            "allocation_finished",
            json!({ "queue_id": queue_id, "allocation_id": allocation_id }),
        ),
        EventPayload::ServerStart { server_uid } => (
            "server_start",
            json!({ "server_uid": server_uid }),
        ),
        EventPayload::ServerStop => (
            "server_stop",
            json!({}),
        ),
        EventPayload::TaskNotify(notify) => (
            "task_notify",
            json!({ "task_id": notify.task_id, "worker_id": notify.worker_id, "message": hex::encode(&notify.message) }),
        ),
    }
}

/// `GET /events`：SSE 事件流（§2.1）。空闲 15s 注释帧心跳（KeepAlive 默认）；
/// 连接断开时接收端 drop，发送失败即被 EventStreamer 清理（listener 生命周期
/// 绑定连接）。
async fn get_events(State(state): State<HttpState>) -> Result<Sse<impl Stream<Item = Result<SseFrame, std::convert::Infallible>>>, Response> {
    let (reply, rx) = oneshot::channel();
    if state.query_tx.send(HttpQuery::Subscribe { reply }).is_err() {
        return Err(service_unavailable());
    }
    let Ok(event_rx) = rx.await else {
        return Err(service_unavailable());
    };
    let stream = futures::stream::unfold(event_rx, |mut event_rx| async move {
        event_rx.recv().await.map(|event| {
            let (name, data) = event_to_frame(&event);
            let mut fields = match data {
                serde_json::Value::Object(fields) => fields,
                _ => unreachable!("event payload is always an object"),
            };
            fields.insert("time".into(), json!(event.time));
            let frame = SseFrame::default()
                .event(name)
                .data(serde_json::to_string(&serde_json::Value::Object(fields)).expect("event json"));
            (Ok(frame), event_rx)
        })
    });
    Ok(Sse::new(stream).keep_alive(KeepAlive::default()))
}

fn service_unavailable() -> Response {
    (
        StatusCode::SERVICE_UNAVAILABLE,
        axum::Json(json!({ "error": "server is shutting down" })),
    )
        .into_response()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::server::event::Event;
    use std::time::Duration as StdDuration;

    #[test]
    fn test_event_frame_names_and_payloads() {
        let cases: Vec<(EventPayload, &str)> = vec![
            (
                EventPayload::Submit {
                    job_id: 1.into(),
                    closed_job: true,
                    serialized_desc: crate::common::serialization::Serialized::new(
                        &crate::transfer::messages::SubmitRequest {
                            job_desc: crate::transfer::messages::JobDescription {
                                name: "n".into(),
                                max_fails: None,
                            },
                            submit_desc: crate::transfer::messages::JobSubmitDescription {
                                task_desc: crate::transfer::messages::JobTaskDescription::Array {
                                    ids: IntArray::from_id(0),
                                    entries: None,
                                    task_desc: sample_task_desc(),
                                    resource_rq: sample_resource_rq(),
                                },
                                submit_dir: "/tmp".into(),
                                stream_path: None,
                            },
                            job_id: None,
                        },
                    )
                    .unwrap(),
                },
                "submit",
            ),
            (EventPayload::JobOpen(2.into(), sample_job_desc()), "job_open"),
            (EventPayload::JobClose(2.into()), "job_close"),
            (EventPayload::JobIdle(2.into()), "job_idle"),
            (EventPayload::JobCompleted(2.into()), "job_completed"),
            (
                EventPayload::JobCancel {
                    job_id: 2.into(),
                    cancel_reason: "by hand".into(),
                },
                "job_cancel",
            ),
            (
                EventPayload::TaskStarted {
                    task_id: tako::TaskId::new(2.into(), 0.into()),
                    instance_id: 0.into(),
                    worker_ids: smallvec::smallvec![1.into()],
                    rv_id: 0.into(),
                },
                "task_started",
            ),
            (
                EventPayload::TaskFinished {
                    task_id: tako::TaskId::new(2.into(), 0.into()),
                },
                "task_finished",
            ),
            (
                EventPayload::TaskFailed {
                    task_id: tako::TaskId::new(2.into(), 0.into()),
                    error: "boom".into(),
                },
                "task_failed",
            ),
            (
                EventPayload::TasksCanceled {
                    task_ids: vec![tako::TaskId::new(2.into(), 0.into())],
                },
                "tasks_canceled",
            ),
            (EventPayload::ServerStop, "server_stop"),
        ];
        for (payload, name) in cases {
            let event = Event::at(chrono::Utc::now(), payload);
            let (got, data) = event_to_frame(&event);
            assert_eq!(got, name);
            // time 由流层并入，帧函数只管业务字段
            assert!(!data.to_string().contains('\n'), "frame data must be single line");
        }
    }

    #[test]
    fn test_submit_frame_hides_serialized_desc() {
        let request = crate::transfer::messages::SubmitRequest {
            job_desc: crate::transfer::messages::JobDescription {
                name: "n".into(),
                max_fails: None,
            },
            submit_desc: crate::transfer::messages::JobSubmitDescription {
                task_desc: crate::transfer::messages::JobTaskDescription::Array {
                    ids: IntArray::from_id(0),
                    entries: None,
                    task_desc: sample_task_desc(),
                    resource_rq: sample_resource_rq(),
                },
                submit_dir: "/tmp".into(),
                stream_path: None,
            },
            job_id: None,
        };
        let event = Event::at(
            chrono::Utc::now(),
            EventPayload::Submit {
                job_id: 1.into(),
                closed_job: true,
                serialized_desc: crate::common::serialization::Serialized::new(&request)
                    .unwrap(),
            },
        );
        let (name, data) = event_to_frame(&event);
        assert_eq!(name, "submit");
        let text = data.to_string();
        assert!(text.contains("\"job_id\""), "{text}");
        assert!(text.contains("closed_job"), "{text}");
        // bincode 字节不透传
        assert!(!text.contains("serialized_desc"), "{text}");
        assert!(!text.contains("/tmp"), "{text}");
    }

    fn sample_job_desc() -> crate::transfer::messages::JobDescription {
        crate::transfer::messages::JobDescription {
            name: "probe".into(),
            max_fails: None,
        }
    }

    fn sample_task_desc() -> crate::transfer::messages::TaskDescription {
        use crate::transfer::messages::{TaskDescription, TaskKind, TaskKindProgram};
        use tako::program::ProgramDefinition;
        TaskDescription {
            kind: TaskKind::ExternalProgram(TaskKindProgram {
                program: ProgramDefinition {
                    args: vec![bstr::BString::from("sleep")],
                    env: Map::new(),
                    stdout: tako::program::StdioDef::Null,
                    stderr: tako::program::StdioDef::Null,
                    stdin: Vec::new(),
                    cwd: "/tmp".into(),
                },
                pin_mode: PinMode::None,
                task_dir: false,
            }),
            priority: UserPriority::new(0),
            time_limit: Some(StdDuration::from_secs(1)),
            crash_limit: CrashLimit::default(),
        }
    }

    fn sample_resource_rq() -> tako::gateway::ResourceRequestVariants {
        tako::gateway::ResourceRequestVariants::new(smallvec::smallvec![
            tako::gateway::ResourceRequest {
                n_nodes: 1,
                min_time: StdDuration::ZERO,
                resources: smallvec::smallvec![tako::gateway::ResourceRequestEntry {
                    resource: "cpus".to_string(),
                    policy: tako::resources::AllocationRequest::Compact(
                        tako::resources::ResourceAmount::new_units(1),
                    ),
                }],
                weight: Default::default(),
            }
        ])
    }
}
