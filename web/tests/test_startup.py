"""engine/startup.select_gateway 回归（GUI 走查冒烟发现）。

缺陷：工厂内部曾以 `from .cli_gateway` / `from .http_gateway` 相对导入，
而两实现位于 web/src/hq/——引擎开启时应用启动即 ModuleNotFoundError，
单测因注入 Gateway 未触达真实路径而漏检。本文件锁定工厂两分支的
模块可解析性与回落语义。
"""
from __future__ import annotations

from types import SimpleNamespace

from web.src.engine.startup import select_gateway
from web.src.hq.cli_gateway import CliGateway

_PM = SimpleNamespace(hq_path="/tmp/hq", server_dir="/tmp/hq-server")


def test_select_gateway_defaults_to_cli(monkeypatch):
    monkeypatch.setattr("web.src.config.HQ_HTTP_PORT", 0)
    assert isinstance(select_gateway(_PM), CliGateway)


def test_select_gateway_http_unreachable_falls_back(monkeypatch, capsys):
    # 端口 1 无监听（连接立即拒绝）→ HttpGateway 探测失败回落 CLI。
    monkeypatch.setattr("web.src.config.HQ_HTTP_PORT", 1)
    assert isinstance(select_gateway(_PM), CliGateway)
    assert "回落 CliGateway" in capsys.readouterr().err
