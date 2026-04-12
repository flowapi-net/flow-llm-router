"""IP whitelist middleware.

Three modes:
- ``local_only`` (default): only 127.0.0.1 / ::1
- ``whitelist``: configurable IP list with CIDR support
- ``open``: no restriction
"""

from __future__ import annotations

import ipaddress
from typing import Sequence

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

_LOCALHOST_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
]


class IPGuardMiddleware(BaseHTTPMiddleware):
    """Reject requests whose client IP is not in the allowed set."""

    def __init__(
        self,
        app,
        *,
        mode: str = "local_only",
        allowed_ips: Sequence[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.mode = mode
        self.allowed_networks = self._parse_networks(allowed_ips or [])

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if self.mode == "open":
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        if client_ip is None:
            return self._forbidden()

        try:
            addr = ipaddress.ip_address(client_ip)
        except ValueError:
            return self._forbidden()

        if self.mode == "local_only":
            if not self._is_local(addr):
                return self._forbidden()
        elif self.mode == "whitelist":
            if not self._is_allowed(addr):
                return self._forbidden()

        return await call_next(request)

    def _get_client_ip(self, request: Request) -> str | None:
        if request.client:
            return request.client.host
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return None

    @staticmethod
    def _is_local(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        return any(addr in net for net in _LOCALHOST_NETWORKS)

    def _is_allowed(self, addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        if self._is_local(addr):
            return True
        return any(addr in net for net in self.allowed_networks)

    @staticmethod
    def _parse_networks(ip_list: Sequence[str]) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for ip_str in ip_list:
            try:
                networks.append(ipaddress.ip_network(ip_str, strict=False))
            except ValueError:
                pass
        return networks

    @staticmethod
    def _forbidden() -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"error": {"message": "Access denied: IP not in whitelist", "type": "forbidden"}},
        )
