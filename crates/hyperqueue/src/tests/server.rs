use crate::client::globalsettings::GlobalSettings;
use crate::client::output::cli::CliOutput;
use crate::server::bootstrap::{ServerConfig, get_client_session, initialize_server};
use crate::transfer::connection::ClientSession;
use cli_table::ColorChoice;
use std::future::Future;
use std::path::PathBuf;
use std::time::Duration;
use tempfile::TempDir;
use tokio::task::LocalSet;
use tokio::time::timeout;

pub struct RunningHqServer {
    dir: PathBuf,
    notify_quit: bool,
    /// 内嵌 HTTP API 的实际监听端口（未启用时为 None，H4 测试用）
    pub http_port: Option<u16>,
}

impl RunningHqServer {
    /// Do not explicitly stop the server, it will be stopped by the test itself.
    pub fn do_not_notify(&mut self) {
        self.notify_quit = false;
    }

    pub async fn client(&self) -> ClientSession {
        get_client_session(&self.dir)
            .await
            .expect("Cannot connect to server")
    }
}

/// Start the whole HQ server, including almost all bells and whistles,
/// and then run a future that will perform the actual test on it.
/// After the future finishes, the server will be shut down.
///
/// If you need to configure the server, add parameters (or some builder) here.
pub async fn run_hq_test<F, Fut>(test_fn: F)
where
    // We pass the server by value and return it because of problematic lifetimes
    // with the closure + future combination. Async closures should fix this.
    F: FnOnce(RunningHqServer) -> Fut,
    Fut: Future<Output = anyhow::Result<RunningHqServer>>,
{
    run_hq_test_with_cfg(ServerConfig::for_test(None), test_fn).await
}

/// Start the server with a custom configuration (e.g. the embedded HTTP API).
pub async fn run_hq_test_with_cfg<F, Fut>(server_cfg: ServerConfig, test_fn: F)
where
    F: FnOnce(RunningHqServer) -> Fut,
    Fut: Future<Output = anyhow::Result<RunningHqServer>>,
{
    let tmp_dir = TempDir::with_prefix("hq-test").unwrap();

    let gsettings = GlobalSettings::new(
        tmp_dir.path().to_path_buf(),
        Box::new(CliOutput::new(ColorChoice::Never)),
    );
    let ServerConfig {
        worker_host,
        client_host,
        idle_timeout,
        client_port,
        worker_port,
        journal_path,
        journal_flush_period,
        worker_secret_key,
        client_secret_key,
        server_uid,
        scheduler_mip_time_limit,
        http_port,
    } = server_cfg;
    let (fut, notify, _state, _senders) =
        initialize_server(
            &gsettings,
            ServerConfig {
                worker_host,
                client_host,
                idle_timeout,
                client_port,
                worker_port,
                journal_path,
                journal_flush_period,
                worker_secret_key,
                client_secret_key,
                server_uid,
                scheduler_mip_time_limit,
                http_port,
            },
            1.into(),
            1,
            None,
        )
        .await
        .unwrap();
    let localset = LocalSet::new();

    // Run the server in the background, concurrently with the testing future
    let server_fut = localset.spawn_local(fut);

    let server = RunningHqServer {
        dir: tmp_dir.path().to_path_buf(),
        notify_quit: true,
        http_port,
    };
    // Run the test itself. If it fails, we still try to finish the server itself,
    // for better error propagation.
    let test_error = localset.run_until(test_fn(server)).await;
    let notify_quit = test_error.as_ref().map(|s| s.notify_quit).unwrap_or(true);

    // Tell the server to quit if the test didn't opt out
    if notify_quit {
        notify.notify_one();
    }

    // Wait for it to quit. Panics will be propagated from `run_until`.
    let server_error = localset
        .run_until(async move {
            match timeout(Duration::from_secs(5), server_fut).await {
                Ok(res) => res.unwrap(),
                Err(_) => {
                    panic!("The server has not finished in 5 seconds. Maybe there is a deadlock?")
                }
            }
        })
        .await;

    // Wait for any background processes to quit
    localset.await;

    // Propagate the errors
    if server_error.is_err() && test_error.is_err() {
        eprintln!("{server_error:?}");
        test_error.expect("Test failed");
    } else {
        test_error.expect("Test failed");
        server_error.expect("Server failed");
    }
}
