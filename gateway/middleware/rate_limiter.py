"""
Rate Limiter — sliding window per IP.
"""

import time
from collections import defaultdict


class RateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_ip: str) -> tuple[bool, dict]:
        now = time.time()
        cutoff = now - self.window_seconds

        self._requests[client_ip] = [
            t for t in self._requests[client_ip] if t > cutoff
        ]

        current = len(self._requests[client_ip])

        if current >= self.max_requests:
            oldest = self._requests[client_ip][0]
            retry_after = int(oldest + self.window_seconds - now) + 1
            return False, {
                "remaining": 0,
                "retry_after": retry_after,
                "limit": self.max_requests,
            }

        self._requests[client_ip].append(now)
        return True, {
            "remaining": self.max_requests - current - 1,
            "retry_after": 0,
            "limit": self.max_requests,
        }

    def reset(self, client_ip: str | None = None):
        if client_ip:
            self._requests.pop(client_ip, None)
        else:
            self._requests.clear()
