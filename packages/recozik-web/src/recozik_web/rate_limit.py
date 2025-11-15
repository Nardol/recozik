"""Rate limiting implementation for API endpoints."""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request, status


class RateLimiter:
    """In-memory rate limiter using sliding window algorithm."""

    def __init__(self, max_requests: int, window_seconds: int = 60) -> None:
        """Initialize rate limiter with max requests per window.

        Args:
            max_requests: Maximum number of requests allowed in the time window
            window_seconds: Time window in seconds (default: 60)

        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def check_rate_limit(self, identifier: str) -> None:
        """Check if the identifier has exceeded the rate limit.

        Args:
            identifier: Unique identifier (e.g., IP address, user ID)

        Raises:
            HTTPException: 429 Too Many Requests if limit exceeded

        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            # Remove old requests outside the window
            self._requests[identifier] = [
                timestamp for timestamp in self._requests[identifier] if timestamp > cutoff
            ]

            # Check if limit exceeded
            if len(self._requests[identifier]) >= self.max_requests:
                detail = (
                    f"Rate limit exceeded: {self.max_requests} requests per {self.window_seconds}s"
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=detail,
                    headers={"Retry-After": str(self.window_seconds)},
                )

            # Record this request
            self._requests[identifier].append(now)

    def cleanup_old_entries(self, max_age_seconds: int = 3600) -> None:
        """Remove entries older than max_age to prevent memory leaks.

        Args:
            max_age_seconds: Maximum age of entries to keep (default: 1 hour)

        """
        now = time.time()
        cutoff = now - max_age_seconds

        with self._lock:
            # Remove identifiers with no recent requests
            to_remove = [
                identifier
                for identifier, timestamps in self._requests.items()
                if not timestamps or max(timestamps) < cutoff
            ]
            for identifier in to_remove:
                del self._requests[identifier]


class AuthRateLimiter:
    """Rate limiter specifically for authentication endpoints."""

    def __init__(self, limiter: RateLimiter) -> None:
        """Initialize with a RateLimiter instance."""
        self.limiter = limiter
        self._failed_attempts: dict[str, int] = defaultdict(int)
        self._lock = Lock()

    def check_auth_attempt(self, request: Request) -> None:
        """Check rate limit for authentication attempts.

        Args:
            request: FastAPI Request object

        Raises:
            HTTPException: 429 if rate limit exceeded

        """
        # Use client IP as identifier
        client_ip = self._get_client_ip(request)
        self.limiter.check_rate_limit(f"auth:{client_ip}")

    def record_failed_auth(self, request: Request) -> None:
        """Record a failed authentication attempt.

        Args:
            request: FastAPI Request object

        """
        client_ip = self._get_client_ip(request)
        with self._lock:
            self._failed_attempts[client_ip] += 1

    def record_successful_auth(self, request: Request) -> None:
        """Clear failed attempts on successful authentication.

        Args:
            request: FastAPI Request object

        """
        client_ip = self._get_client_ip(request)
        with self._lock:
            self._failed_attempts.pop(client_ip, None)

    def get_failed_attempts(self, request: Request) -> int:
        """Get number of failed attempts for a client.

        Args:
            request: FastAPI Request object

        Returns:
            Number of failed authentication attempts

        """
        client_ip = self._get_client_ip(request)
        return self._failed_attempts.get(client_ip, 0)

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Extract client IP from request, considering proxies.

        Args:
            request: FastAPI Request object

        Returns:
            Client IP address

        """
        # Check X-Forwarded-For header first (for proxies/load balancers)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take the first IP in the chain
            return forwarded.split(",")[0].strip()

        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # Fall back to direct client
        if request.client:
            return request.client.host

        return "unknown"


# Global rate limiter instances
_rate_limiter: RateLimiter | None = None
_auth_rate_limiter: AuthRateLimiter | None = None


def get_rate_limiter(max_requests: int = 60, window_seconds: int = 60) -> RateLimiter:
    """Get or create the global rate limiter instance.

    Args:
        max_requests: Maximum requests per window (used on first call)
        window_seconds: Time window in seconds (used on first call)

    Returns:
        Global RateLimiter instance

    """
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(max_requests, window_seconds)
    return _rate_limiter


def get_auth_rate_limiter(max_requests: int = 20, window_seconds: int = 60) -> AuthRateLimiter:
    """Get or create the global auth rate limiter instance.

    Args:
        max_requests: Maximum auth attempts per window (used on first call)
        window_seconds: Time window in seconds (used on first call)

    Returns:
        Global AuthRateLimiter instance

    """
    global _auth_rate_limiter
    if _auth_rate_limiter is None:
        limiter = RateLimiter(max_requests, window_seconds)
        _auth_rate_limiter = AuthRateLimiter(limiter)
    return _auth_rate_limiter
