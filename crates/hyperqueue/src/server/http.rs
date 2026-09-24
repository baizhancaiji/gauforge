//! HQ server 内嵌 HTTP/SSE 层（m1-plan §2.1、§4.2 H1–H3）。
//!
//! 仅在 `hq server start --http-port <P>` 时启动（默认关，HQ 行为零变化），
//! 一律绑 `127.0.0.1`；唯一预期消费者是 g16web 后端，无认证（回环即边界）。
//!
//! server 内存态（`StateRef`/`Senders`）基于 `Rc` 不可跨线程，故 handler 不直接
//! 持有状态，而是经 [`HttpQuery`] 通道请求**本地桥接任务**（随 server 的
//! `LocalSet` 运行）代为调用 server 侧命令处理函数——与 RPC 消息循环共用同一
//! 实现，保证 HTTP 与 CLI `--output-mode json` 双路一致。
use axum::Json;
use axum::Router;
use axum::extract::State;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use serde_json::{Value, json};
use tokio::sync::mpsc::{UnboundedReceiver, UnboundedSender, unbounded_channel};
use tokio::sync::oneshot;

use crate::server::Senders;
use crate::server::state::StateRef;

/// HTTP 层 → 本地桥接任务的请求（字段均 `Send`，通道可跨线程）。
pub(crate) enum HttpQuery {
    Info { reply: oneshot::Sender<Value> },
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
}

pub(crate) fn router(state: HttpState) -> Router {
    Router::new().route("/info", get(get_info)).with_state(state)
}

/// 启动本地桥接任务（必须在 server 的 `LocalSet` 上下文中调用），
/// 返回供 axum handler 使用的请求通道。
pub(crate) fn spawn_bridge(
    state_ref: StateRef,
    senders: Senders,
) -> UnboundedSender<HttpQuery> {
    let (query_tx, query_rx) = unbounded_channel();
    tokio::task::spawn_local(bridge_task(state_ref, senders, query_rx));
    query_tx
}

async fn bridge_task(
    state_ref: StateRef,
    _senders: Senders,
    mut query_rx: UnboundedReceiver<HttpQuery>,
) {
    while let Some(query) = query_rx.recv().await {
        match query {
            HttpQuery::Info { reply } => {
                let _ = reply.send(compute_info(&state_ref));
            }
        }
    }
}

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

async fn get_info(State(state): State<HttpState>) -> Response {
    let (reply, rx) = oneshot::channel();
    if state.query_tx.send(HttpQuery::Info { reply }).is_err() {
        return service_unavailable();
    }
    match rx.await {
        Ok(value) => Json(value).into_response(),
        Err(_) => service_unavailable(),
    }
}

fn service_unavailable() -> Response {
    (
        StatusCode::SERVICE_UNAVAILABLE,
        Json(json!({ "error": "server is shutting down" })),
    )
        .into_response()
}
