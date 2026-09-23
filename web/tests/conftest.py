"""契约测试公共工具：openapi-core 响应体校验 harness。

openapi-core 的 Request/Response 为运行时协议，需按字段构造最小对象。
契约 server url 为 "/api/v1"，故校验用 path 带此前缀（对应 _find_path 的
urljoin(host_url, path) 语义）。
"""
from __future__ import annotations

import json
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
def _isolated_db(tmp_path):
    """B1 起全局隔离：每个用例注入独立 SQLite（内存级临时文件），不触真实工作区。"""
    from web.src import store
    db = store.Database(tmp_path / "isolated.db")
    store.run_migrations(db)
    store.set_db(db)
    yield
    store.reset_db()


def load_spec() -> OpenAPI:
    with config.CONTRACT_PATH.open(encoding="utf-8") as fh:
        return OpenAPI.from_dict(yaml.safe_load(fh))


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
             query: dict[str, Any] | None = None) -> list:
    """返回响应校验错误列表（空=通过）。"""
    req = FakeRequest(method, path, query=query)
    resp = FakeResponse(status_code, data)
    return list(spec.iter_response_errors(req, resp))


def assert_contract_schema(spec: OpenAPI, method: str, path: str,
                           status_code: int, data: Any,
                           query: dict[str, Any] | None = None) -> None:
    errors = validate(spec, method, path, status_code, data, query=query)
    if errors:
        raise AssertionError(
            f"响应不符合契约 {method} {path}（{status_code}）: {[repr(e) for e in errors]}")