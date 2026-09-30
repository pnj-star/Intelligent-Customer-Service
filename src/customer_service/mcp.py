"""customer_service MCP 服务端入口（薄层）。

支持 stdio / sse / streamable-http 三种传输方式；IDE 直接运行本文件时默认
streamable-http，已安装包 / python -m 方式默认 stdio。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if not __package__:
    script_dir = str(Path(sys.argv[0]).resolve().parent)
    sys.path[:] = [
        entry
        for entry in sys.path
        if entry and str(Path(entry).resolve()) != script_dir
    ]

if __package__:
    from .mcp_server import create_mcp_server
else:
    from customer_service.mcp_server import create_mcp_server


def _normalize_transport(value: str) -> str:
    return "streamable-http" if value.replace("_", "-") == "streamable-http" else value


def _run_server(server: Any, transport: str) -> None:
    import asyncio

    if transport == "stdio":
        server.run(transport="stdio")
        return
    if transport == "sse":
        asyncio.run(server.run_sse_async())
        return
    asyncio.run(server.run_streamable_http_async())


def _resolve_env_file(env_file: str | None) -> str | None:
    """环境文件优先级：--env-file > CUSTOMER_SERVICE_ENV_FILE > 项目根 .env。"""
    from common_core.config import load_env_files, resolve_env_file

    resolved = resolve_env_file(env_file, env_key="CUSTOMER_SERVICE_ENV_FILE")
    if resolved is None:
        fallback = Path(__file__).resolve().parents[2] / ".env"
        if fallback.is_file():
            resolved = str(fallback)
    if resolved:
        load_env_files(resolved)
    return resolved


def main(argv: list[str] | None = None) -> None:
    """启动客服 MCP 服务；argv 用于本地启动脚本注入默认传输参数。"""
    import argparse

    default_transport = "streamable-http" if not __package__ else "stdio"
    parser = argparse.ArgumentParser(prog="customer-service-mcp")
    parser.add_argument(
        "--env-file",
        default=None,
        help="Path to a .env file (default: CUSTOMER_SERVICE_ENV_FILE or ./.env)",
    )
    parser.add_argument(
        "--transport",
        default=default_transport,
        choices=["stdio", "sse", "streamable-http", "streamable_http"],
        help=f"Transport to expose (default: {default_transport}).",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Bind host for HTTP transports (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port for HTTP transports (default: 8000)",
    )
    parser.add_argument(
        "--path",
        default=None,
        help="HTTP endpoint path for streamable-http (default /streamable) or sse (default /sse)",
    )
    args = parser.parse_args(argv)

    env_path = _resolve_env_file(args.env_file)
    from .dependencies import build_default_dependencies

    deps = build_default_dependencies(env_file=env_path)
    transport = _normalize_transport(args.transport)
    if args.host is not None or args.port is not None or args.path is not None:
        host = "127.0.0.1" if args.host is None else args.host
        port = 8000 if args.port is None else args.port
        streamable_path = args.path or "/streamable"
        sse_path = args.path or "/sse"
    else:
        host, port, streamable_path, sse_path = None, None, "/streamable", "/sse"
    server = create_mcp_server(
        deps=deps,
        config_source=f"env:{env_path}" if env_path else "process-env",
        host=host,
        port=port,
        streamable_path=streamable_path,
        sse_path=sse_path,
    )
    _run_server(server, transport)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["create_mcp_server", "main"]
