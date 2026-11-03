"""Small in-process login limiter and trusted-proxy client identification."""

from __future__ import annotations

import hashlib
import ipaddress
import math
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from ipaddress import IPv4Network, IPv6Network

from starlette.requests import Request

DEFAULT_MAX_BUCKETS = 10_000


class InMemoryLoginRateLimiter:
    """Fixed-window limiter for local/single-process use with bounded memory capacity."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        max_buckets: int = DEFAULT_MAX_BUCKETS,
    ) -> None:
        self._clock = clock
        self._max_buckets = max(1, int(max_buckets))
        self._buckets: OrderedDict[str, tuple[float, int]] = OrderedDict()
        self._last_cleanup = 0.0
        self._lock = threading.Lock()

    def _purge_expired(self, now: float, window_seconds: int) -> None:
        """Purge expired buckets in-place without rebuilding the collection."""
        expired_keys = [
            key
            for key, (started_at, _) in self._buckets.items()
            if now - started_at >= window_seconds
        ]
        for key in expired_keys:
            del self._buckets[key]

    def check_rate_limit(
        self, client_key: str, attempts: int, window_seconds: int
    ) -> int | None:
        """Return retry-after seconds if client_key has exhausted attempts, else None."""
        now = self._clock()
        with self._lock:
            if now - self._last_cleanup >= min(window_seconds, 60):
                self._purge_expired(now, window_seconds)
                self._last_cleanup = now

            bucket = self._buckets.get(client_key)
            if bucket is None or now - bucket[0] >= window_seconds:
                return None

            started_at, count = bucket
            if count >= attempts:
                return max(1, math.ceil(window_seconds - (now - started_at)))
            return None

    def record_failure(
        self, client_key: str, attempts: int, window_seconds: int
    ) -> None:
        """Record a failed login attempt for client_key."""
        now = self._clock()
        with self._lock:
            if now - self._last_cleanup >= min(window_seconds, 60):
                self._purge_expired(now, window_seconds)
                self._last_cleanup = now

            bucket = self._buckets.get(client_key)
            if bucket is None or now - bucket[0] >= window_seconds:
                if bucket is None and len(self._buckets) >= self._max_buckets:
                    self._purge_expired(now, window_seconds)
                    if len(self._buckets) >= self._max_buckets:
                        self._buckets.popitem(last=False)

                self._buckets[client_key] = (now, 1)
                self._buckets.move_to_end(client_key)
                return

            started_at, count = bucket
            self._buckets[client_key] = (started_at, count + 1)

    def check(self, client_key: str, attempts: int, window_seconds: int) -> int | None:
        """Convenience method for tests: check rate limit and record an attempt."""
        retry_after = self.check_rate_limit(client_key, attempts, window_seconds)
        if retry_after is not None:
            return retry_after
        self.record_failure(client_key, attempts, window_seconds)
        return None


def _normalize_ip(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Normalize dual-stack IPv4-mapped IPv6 addresses to IPv4Address."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _is_trusted(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    networks: Sequence[IPv4Network | IPv6Network],
) -> bool:
    """Check whether an IP address belongs to any of the trusted networks."""
    normalized = _normalize_ip(address)
    return any(
        normalized.version == network.version and normalized in network
        for network in networks
    )


def client_rate_limit_key(
    request: Request,
    trusted_proxy_networks: Sequence[IPv4Network | IPv6Network] = (),
) -> str:
    """Use the socket peer unless it is explicitly trusted to supply X-Forwarded-For."""
    peer_text = request.client.host.strip() if request.client is not None and request.client.host else ""
    if not peer_text:
        header_parts = [
            ", ".join(request.headers.getlist("x-forwarded-for")).strip(),
            request.headers.get("x-real-ip", "").strip(),
            request.headers.get("user-agent", "").strip(),
            request.headers.get("host", "").strip(),
        ]
        raw_identifier = "|".join(part for part in header_parts if part)
        if raw_identifier:
            digest = hashlib.sha256(raw_identifier.encode("utf-8")).hexdigest()[:16]
            return f"fallback:{digest}"
        return "fallback:no-client"

    try:
        raw_peer = ipaddress.ip_address(peer_text)
    except ValueError:
        return f"client:{peer_text}"

    peer = _normalize_ip(raw_peer)
    if not _is_trusted(peer, trusted_proxy_networks):
        return peer.compressed

    forwarded_headers = request.headers.getlist("x-forwarded-for")
    if not forwarded_headers:
        return peer.compressed

    forwarded = ", ".join(forwarded_headers).strip()
    if not forwarded or len(forwarded) > 2048:
        return peer.compressed

    forwarded_parts = [part.strip() for part in forwarded.split(",") if part.strip()]
    if not forwarded_parts or len(forwarded_parts) > 20:
        return peer.compressed

    try:
        chain = [_normalize_ip(ipaddress.ip_address(part)) for part in forwarded_parts]
    except ValueError:
        return peer.compressed

    current = peer
    for previous in reversed(chain):
        if not _is_trusted(current, trusted_proxy_networks):
            break
        current = previous
    return current.compressed
