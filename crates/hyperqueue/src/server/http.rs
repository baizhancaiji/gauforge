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
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
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
                let _ = reply.send(handle_submit_reply(&state_ref, &senders, request));
            }
            HttpQuery::JobsInfo { selector, reply } => {
                let _ = reply.send(handle_jobs_info_reply(&state_ref, &selector));
            }
            HttpQuery::JobInfo { job_id, reply } => {
                let _ = reply.send(handle_job_info_reply(&state_ref, job_id));
            }
            HttpQuery::Cancel { job_id, reply } => {
                let _ = reply.send(handle_cancel_reply(&state_ref, &senders, job_id).await);
            }
            HttpQuery::Workers { reply } => {
                let _ = reply.send(handle_workers_reply(&state_ref));
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
                C::Canceled(canceled, total) => Reply::ok(json!({
                    "id": job_id,
                    "canceled_tasks": canceled.len(),
                    "already_finished": total - canceled.len() as u32,
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

fn service_unavailable() -> Response {
    (
        StatusCode::SERVICE_UNAVAILABLE,
        axum::Json(json!({ "error": "server is shutting down" })),
    )
        .into_response()
}
