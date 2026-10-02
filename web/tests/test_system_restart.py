"""POST /system/restart 编排测试（用户验收反馈：一键重启）。

全部外溢动作（脚本拉起、延迟自退）patch 后打真实端点，不真杀进程：
- 受理 202（响应体过契约 schema 校验）与编排调用次序；
- 守卫：更新流程进行中 → 409 UPDATE_IN_PROGRESS（复用既有码）；
- 脚本定位：部署根 restart_g16web.sh 优先，源码形态回落 scripts/deploy/；
- 拉起参数：bash + 脚本 + --pid/--log、start_new_session、日志落盘。
"""
from __future__ import annotations

import os

from fastapi.testclient import TestClient

from web.src import config
from web.src.main import app
from web.src.services import restart as restart_svc
from web.src.services import update as update_svc
from .conftest import assert_contract_schema, load_spec

spec = load_spec()


def test_restart_accepted(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(restart_svc, "launch_script",
                        lambda: calls.append("launch"))
    monkeypatch.setattr(restart_svc, "schedule_self_terminate",
                        lambda: calls.append("terminate"))
    # 守卫取数不依赖全局更新单例（update 系测试会残留 in-flight 相）
    monkeypatch.setattr(update_svc, "get_service",
                        lambda: type("FakeSvc", (), {"phase": "idle"})())
    r = TestClient(app).post("/api/v1/system/restart")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "restarting"
    assert body["message"]
    assert calls == ["launch", "terminate"]  # 先拉脚本、后调度自退
    assert_contract_schema(spec, "POST", "/api/v1/system/restart", 202, body)


def test_restart_blocked_when_update_in_flight(monkeypatch) -> None:
    class FakeSvc:
        phase = "downloading"

    monkeypatch.setattr(update_svc, "get_service", lambda: FakeSvc())
    r = TestClient(app).post("/api/v1/system/restart")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "UPDATE_IN_PROGRESS"


def test_script_path_prefers_deploy_root(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    fallback = tmp_path / "scripts" / "deploy"
    fallback.mkdir(parents=True)
    (fallback / "restart_g16web.sh").write_text("#!/usr/bin/env bash\n",
                                                encoding="utf-8")
    assert restart_svc.script_path() == fallback / "restart_g16web.sh"
    (tmp_path / "restart_g16web.sh").write_text("#!/usr/bin/env bash\n",
                                                encoding="utf-8")
    assert restart_svc.script_path() == tmp_path / "restart_g16web.sh"


def test_script_path_missing_raises(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    try:
        restart_svc.script_path()
        raise AssertionError("空布局应抛 FileNotFoundError")
    except FileNotFoundError:
        pass


def test_script_path_falls_back_to_repo_scripts() -> None:
    assert restart_svc.script_path() == (
        config.PROJECT_ROOT / "scripts" / "deploy" / "restart_g16web.sh")


def test_launch_script_popen_args(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    (tmp_path / "restart_g16web.sh").write_text("#!/usr/bin/env bash\n",
                                                encoding="utf-8")
    seen: dict = {}

    def fake_popen(args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs

    monkeypatch.setattr(restart_svc, "_popen", fake_popen)
    script = restart_svc.launch_script()
    assert script == tmp_path / "restart_g16web.sh"
    assert seen["args"] == ["bash", str(script), "--pid", str(os.getpid()),
                            "--log", str(tmp_path / "restart.log")]
    assert seen["kwargs"]["start_new_session"] is True
    assert (tmp_path / "restart.log").exists()
