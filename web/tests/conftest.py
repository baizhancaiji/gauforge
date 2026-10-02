"""契约测试公共工具：openapi-core 响应体校验 harness。

openapi-core 的 Request/Response 为运行时协议，需按字段构造最小对象。
契约 server url 为 "/api/v1"，故校验用 path 带此前缀（对应 _find_path 的
urljoin(host_url, path) 语义）。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# pytest 默认 pythonpath=web/src；补一条仓库根以便 `from web.src...` 导入。
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest
import yaml
from openapi_core import OpenAPI
from openapi_core.datatypes import RequestParameters

from web.src import config

@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """B1 起全局隔离：每个用例注入独立 SQLite（内存级临时文件），不触真实工作区。"""
    from web.src import store
    db = store.Database(tmp_path / "isolated.db")
    store.run_migrations(db)
    store.set_db(db)
    # 引擎默认关闭（B10）：不 spawn 真 HQ、lifespan 走 M0 演示模式；
    # 引擎用例自行置 True 并注入 FakeGateway/FakePM。
    monkeypatch.setattr(config, "ENGINE_ENABLED", False)
    # 更新自动检查调度（v2.1.0）在测试环境预置 never：lifespan 挂载的调度
    # 协程醒来即空转，防止长用例（>30s，如 e2e）里真实触发检查（触网/写
    # 伴生文件）；清表用例自行回落默认值，调度器方法保持真实语义可测。
    store.settings().set("update_check_interval", "never")
    yield
    store.reset_db()


def pytest_sessionfinish(session, exitstatus) -> None:
    """会话收尾兜底：强停一切仍存活的 HqProcessManager。

    HqProcessManager 以 start_new_session 脱离进程组 spawn（§8.7 复用
    语义），未走 stop() 的路径（异常中断、竞态遗漏）会让 HQ server/worker
    在 pytest 退出后永久残留；此处对全部存活实例统一 stop（内含 SIGKILL
    兜底），保证测试会话零残留。"""
    from web.src.hq.process import HqProcessManager
    for mgr in list(HqProcessManager._instances):
        try:
            mgr.stop()
        except Exception:  # noqa: BLE001 — 收尾清理尽力而为，不掩盖退出状态
            pass


def load_spec() -> OpenAPI:
    with config.CONTRACT_PATH.open(encoding="utf-8") as fh:
        return OpenAPI.from_dict(yaml.safe_load(fh))


def newer_version() -> str:
    """必然大于本地当前版本的测试版本串（v2.9.9 段内自增基线）。

    update 域用例此前硬编码「远端 v2.1.1 比本地新」，tag v2.2.0 后本地
    基线上移、前提翻转致 15 用例失败（2026-10-02 实测）。比较口径剥
    git describe 后缀（update._comparable），故 v2.9.9 系列对任何
    v2.x 基线恒为「有更新」，后续 tag 不再翻转。"""
    m = re.match(r"v2\.(\d+)\.(\d+)", config.APP_VERSION)
    minor = int(m.group(2)) if m else 0
    return f"v2.9.{minor + 1}"


class FakeRequest:
    """openapi-core Request 协议最小实现。"""

    def __init__(self, method: str, path: str,
                 query: dict[str, Any] | None = None,
                 headers: dict[str, Any] | None = None,
                 content_type: str = "application/json") -> None:
        self._m = method.lower()
        self._raw_path = path
        self._p = "/api/v1" + path if not path.startswith("/api/v1") else path
        self._q = query or {}
        self._h = headers or {}
        self._b = None
        self._ct = content_type

    @property
    def method(self) -> str:
        return self._m

    @property
    def path(self) -> str:
        return self._p

    @property
    def host_url(self) -> str:
        return "http://test"

    @property
    def full_url_pattern(self) -> str:
        return "http://test" + self._p

    @property
    def content_type(self) -> str:
        return self._ct

    @property
    def body(self) -> bytes | None:
        return self._b

    @property
    def parameters(self) -> RequestParameters:
        return RequestParameters(query=self._q, header=self._h)


class FakeResponse:
    """openapi-core Response 协议最小实现。"""

    def __init__(self, status_code: int, data: Any,
                 content_type: str = "application/json") -> None:
        self._sc = status_code
        self._haml = data if isinstance(data, bytes) else \
            json.dumps(data, ensure_ascii=False).encode()
        self._ct = content_type
        self._h: dict[str, str] = {}

    @property
    def status_code(self) -> int:
        return self._sc

    @property
    def content_type(self) -> str:
        return self._ct

    @property
    def headers(self) -> dict[str, str]:
        return self._h

    @property
    def data(self) -> bytes:
        return self._haml


def validate(spec: OpenAPI, method: str, path: str,
             status_code: int, data: Any,
             query: dict[str, Any] | None = None,
             content_type: str = "application/json") -> list:
    """返回响应校验错误列表（空=通过；content_type 供二进制流端点）。"""
    req = FakeRequest(method, path, query=query)
    resp = FakeResponse(status_code, data, content_type=content_type)
    return list(spec.iter_response_errors(req, resp))


def assert_contract_schema(spec: OpenAPI, method: str, path: str,
                           status_code: int, data: Any,
                           query: dict[str, Any] | None = None,
                           content_type: str = "application/json") -> None:
    errors = validate(spec, method, path, status_code, data, query=query,
                      content_type=content_type)
    if errors:
        raise AssertionError(
            f"响应不符合契约 {method} {path}（{status_code}）: {[repr(e) for e in errors]}")