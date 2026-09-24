//! 内嵌 HTTP/SSE 层测试（m1-plan §4.2 H4①：axum 层请求/响应、事件序列化）。
//!
//! 经真实 socket（原始 HTTP/1.1 报文）驱动 `--http-port` 启动的 server，
//! 事件序列化则直接对纯函数 [`crate::server::http::event_to_frame`] 断言。
use crate::server::bootstrap::ServerConfig;
use crate::tests::server::run_hq_test_with_cfg;
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::time::timeout;

/// 预占一个空闲端口再释放，交给 server 绑定（竞争窗口极小）。
fn pick_free_port() -> u16 {
    std::net::TcpListener::bind(("127.0.0.1", 0))
        .unwrap()
        .local_addr()
        .unwrap()
        .port()
}

/// 发送原始 HTTP/1.1 请求（Connection: close 保证读到 EOF），返回 (状态码, 全文)。
async fn http_request(port: u16, request: &str) -> (u16, String) {
    let mut stream = TcpStream::connect(("127.0.0.1", port))
        .await
        .expect("cannot connect to HTTP API");
    stream.write_all(request.as_bytes()).await.unwrap();
    let mut buf = Vec::new();
    timeout(Duration::from_secs(5), stream.read_to_end(&mut buf))
        .await
        .expect("read timeout")
        .expect("read error");
    let text = String::from_utf8_lossy(&buf).to_string();
    let status: u16 = text
        .split_whitespace()
        .nth(1)
        .unwrap_or_else(|| panic!("no status line: {text}"))
        .parse()
        .unwrap();
    (status, text)
}

fn get(path: &str) -> String {
    format!("GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
}

fn post(path: &str, body: &str) -> String {
    format!(
        "POST {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    )
}

fn body_of(response: &str) -> String {
    match response.split_once("\r\n\r\n") {
        Some((_, body)) => body.to_string(),
        None => String::new(),
    }
}

#[tokio::test]
async fn test_http_info_endpoint() {
    let port = pick_free_port();
    run_hq_test_with_cfg(ServerConfig::for_test(Some(port)), |server| async move {
        let port = server.http_port.expect("http port should be set");
        let (status, text) = http_request(port, &get("/info")).await;
        assert_eq!(status, 200);
        let body = body_of(&text);
        assert!(body.contains("\"version\""), "{body}");
        assert!(body.contains("\"workers\""), "{body}");
        assert!(body.contains("\"uptime_seconds\""), "{body}");
        Ok(server)
    })
    .await;
}

#[tokio::test]
async fn test_http_job_endpoints() {
    let port = pick_free_port();
    run_hq_test_with_cfg(ServerConfig::for_test(Some(port)), |server| async move {
        let port = server.http_port.unwrap();

        // 提交（无 worker，任务保持 Waiting，足以驱动查询/取消断言）
        let (status, text) = http_request(
            port,
            &post("/jobs", r#"{"args":["/bin/sleep","5"],"cwd":"/tmp"}"#),
        )
        .await;
        assert_eq!(status, 200, "{text}");
        let body = body_of(&text);
        assert!(body.contains("\"id\""), "{body}");
        let id: u32 = {
            let v: serde_json::Value = serde_json::from_str(&body).unwrap();
            v["id"].as_u64().unwrap() as u32
        };

        // 单查询：详情含 info.id
        let (status, text) = http_request(port, &get(&format!("/jobs/{id}"))).await;
        assert_eq!(status, 200, "{text}");
        assert!(body_of(&text).contains(&format!("\"id\":{id}")), "{text}");

        // 批量查询
        let (status, text) = http_request(port, &get(&format!("/jobs?ids={id}"))).await;
        assert_eq!(status, 200, "{text}");
        let jobs: Vec<serde_json::Value> = serde_json::from_str(&body_of(&text)).unwrap();
        assert_eq!(jobs.len(), 1);

        // 取消
        let (status, text) =
            http_request(port, &post(&format!("/jobs/{id}/cancel"), "")).await;
        assert_eq!(status, 200, "{text}");
        assert!(body_of(&text).contains("\"canceled_tasks\""), "{text}");

        // 错误路径
        let (status, _) = http_request(port, &get("/jobs/999999")).await;
        assert_eq!(status, 404);
        let (status, _) = http_request(port, &post("/jobs", r#"{"args":[]}"#)).await;
        assert_eq!(status, 422);
        let (status, _) = http_request(port, &get("/jobs?ids=notanumber")).await;
        assert_eq!(status, 422);
        Ok(server)
    })
    .await;
}

#[tokio::test]
async fn test_http_workers_endpoint() {
    let port = pick_free_port();
    run_hq_test_with_cfg(ServerConfig::for_test(Some(port)), |server| async move {
        let port = server.http_port.unwrap();
        let (status, text) = http_request(port, &get("/workers")).await;
        assert_eq!(status, 200, "{text}");
        let workers: Vec<serde_json::Value> = serde_json::from_str(&body_of(&text)).unwrap();
        assert!(workers.is_empty()); // 测试未接 worker
        Ok(server)
    })
    .await;
}

/// SSE：订阅在先，经 HTTP 提交与取消后应收到 submit → job_cancel 帧帧序
/// （无 worker 场景的完整事件链）。
#[tokio::test]
async fn test_http_events_stream_frames() {
    let port = pick_free_port();
    run_hq_test_with_cfg(ServerConfig::for_test(Some(port)), |server| async move {
        let port = server.http_port.unwrap();
        let mut stream = TcpStream::connect(("127.0.0.1", port)).await.unwrap();
        stream
            .write_all(b"GET /events HTTP/1.1\r\nHost: 127.0.0.1\r\nAccept: text/event-stream\r\n\r\n")
            .await
            .unwrap();

        // 提交 + 取消，驱动事件
        let (status, _) = http_request(
            port,
            &post("/jobs", r#"{"args":["/bin/sleep","5"],"cwd":"/tmp"}"#),
        )
        .await;
        assert_eq!(status, 200);
        let body = {
            let (_, text) = http_request(port, &get("/jobs?ids=1")).await;
            body_of(&text)
        };
        let id: u64 = {
            let jobs: Vec<serde_json::Value> = serde_json::from_str(&body).unwrap();
            jobs[0]["id"].as_u64().unwrap()
        };
        let (status, _) =
            http_request(port, &post(&format!("/jobs/{id}/cancel"), "")).await;
        assert_eq!(status, 200);

        // 读流直到出现 job_cancel 帧
        let mut buf = Vec::new();
        let mut chunk = [0u8; 2048];
        let deadline = tokio::time::Instant::now() + Duration::from_secs(10);
        while !String::from_utf8_lossy(&buf).contains("job_cancel") {
            if tokio::time::Instant::now() >= deadline {
                panic!("no job_cancel frame within 10s, got: {}", String::from_utf8_lossy(&buf));
            }
            let n = timeout(Duration::from_secs(2), stream.read(&mut chunk))
                .await
                .expect("read timeout")
                .expect("read error");
            if n == 0 {
                break;
            }
            buf.extend_from_slice(&chunk[..n]);
        }
        let text = String::from_utf8_lossy(&buf);
        assert!(text.contains("event: submit"), "{text}");
        assert!(text.contains("event: job_cancel"), "{text}");
        // 帧 data 为含 time 的单行 JSON
        let data_line = text
            .lines()
            .find(|l| l.starts_with("data: "))
            .expect("no data line");
        let payload: serde_json::Value =
            serde_json::from_str(data_line.trim_start_matches("data: ")).unwrap();
        assert!(payload.get("time").is_some(), "{data_line}");
        Ok(server)
    })
    .await;
}
