"""Persistent quota policy using SQLite for tracking usage."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from recozik_services.security import (
    QuotaExceededError,
    QuotaPolicy,
    QuotaScope,
    ServiceUser,
)
from sqlmodel import Field, Session, SQLModel, create_engine, select

logger = logging.getLogger("recozik.web.quota")


class QuotaUsageRecord(SQLModel, table=True):
    """Track quota usage per user and scope with time windows."""

    __tablename__ = "quota_usage"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    scope: str = Field(index=True)
    period_start: datetime = Field(index=True)
    period_end: datetime
    usage_count: int = Field(default=0)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PersistentQuotaPolicy(QuotaPolicy):
    """Quota policy that persists usage to SQLite with rolling windows.

    Features:
    - Persistent storage survives restarts
    - Rolling time windows (hourly, daily, monthly)
    - Automatic cleanup of old records
    """

    def __init__(self, database_url: str, window_hours: int = 24) -> None:
        """Initialize persistent quota policy.

        Args:
            database_url: SQLite database URL
            window_hours: Rolling window size in hours (default: 24)

        """
        self.window_hours = window_hours
        connect_args: dict[str, Any] = {}

        if database_url.startswith("sqlite:///"):
            sqlite_path = Path(database_url.replace("sqlite:///", "", 1))
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            connect_args = {"check_same_thread": False}

        self._engine = create_engine(database_url, connect_args=connect_args)
        SQLModel.metadata.create_all(self._engine)
        self._last_cleanup = datetime.now(timezone.utc)
        logger.info("Persistent quota policy initialized with %dh window", window_hours)

    def consume(
        self,
        user: ServiceUser,
        scope: QuotaScope,
        *,
        cost: int = 1,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        """Record quota usage and enforce limits.

        Args:
            user: User consuming the quota
            scope: Quota scope being consumed
            cost: Number of units to consume (default: 1)
            context: Additional context (unused)

        Raises:
            QuotaExceededError: If quota limit is exceeded

        """
        limits: Mapping[QuotaScope, int | None] = user.attributes.get("quota_limits", {})
        limit = limits.get(scope)

        # No limit configured for this scope
        if limit is None:
            return

        user_key = user.user_id or "anonymous"
        scope_key = scope.value

        now = datetime.now(timezone.utc)
        period_start = now - timedelta(hours=self.window_hours)

        with Session(self._engine) as session:
            # Get or create usage record for current window
            # IMPORTANT: Use period_end > cutoff to include bins that partially overlap
            # the window (e.g., a bin from 12:00-13:00 when cutoff is 12:45)
            statement = (
                select(QuotaUsageRecord)
                .where(QuotaUsageRecord.user_id == user_key)
                .where(QuotaUsageRecord.scope == scope_key)
                .where(QuotaUsageRecord.period_end > period_start)
            )
            records = list(session.exec(statement))

            # Calculate total usage in current window
            current_usage = sum(record.usage_count for record in records)

            # Check if adding this cost would exceed the limit
            if current_usage + cost > limit:
                logger.warning(
                    "Quota exceeded for user %s, scope %s: %d + %d > %d",
                    user_key,
                    scope_key,
                    current_usage,
                    cost,
                    limit,
                )
                raise QuotaExceededError(
                    f"Quota exceeded for {scope.value}: {current_usage + cost} > {limit} "
                    f"(rolling {self.window_hours}h window)"
                )

            # Find or create record for current hour
            current_hour = now.replace(minute=0, second=0, microsecond=0)
            hour_record = next(
                (r for r in records if r.period_start == current_hour),
                None,
            )

            if hour_record is None:
                # Create new record for this hour
                hour_record = QuotaUsageRecord(
                    user_id=user_key,
                    scope=scope_key,
                    period_start=current_hour,
                    period_end=current_hour + timedelta(hours=1),
                    usage_count=cost,
                    last_updated=now,
                )
                session.add(hour_record)
            else:
                # Update existing record
                hour_record.usage_count += cost
                hour_record.last_updated = now
                session.add(hour_record)

            session.commit()

            logger.debug(
                "Quota consumed for user %s, scope %s: %d/%d (cost: %d)",
                user_key,
                scope_key,
                current_usage + cost,
                limit,
                cost,
            )

        # Periodic cleanup to prevent database growth
        # Clean up once per hour to avoid performance impact
        if (now - self._last_cleanup).total_seconds() > 3600:
            self._last_cleanup = now
            try:
                # Keep records for 2x window_hours (e.g., 48h for 24h window)
                # Convert hours to days, keeping at least 2 days
                days_to_keep = max(2, (self.window_hours * 2) // 24)
                deleted = self.cleanup_old_records(days_to_keep=days_to_keep)
                if deleted > 0:
                    logger.info("Periodic cleanup removed %d old quota records", deleted)
            except Exception as e:
                logger.warning("Quota cleanup failed: %s", e)

    def get_usage(self, user_id: str, scope: QuotaScope) -> int:
        """Get current usage for a user and scope in the rolling window.

        Args:
            user_id: User identifier
            scope: Quota scope to check

        Returns:
            Current usage count in the rolling window

        """
        now = datetime.now(timezone.utc)
        period_start = now - timedelta(hours=self.window_hours)

        with Session(self._engine) as session:
            # IMPORTANT: Use period_end > cutoff to include bins that partially overlap
            statement = (
                select(QuotaUsageRecord)
                .where(QuotaUsageRecord.user_id == user_id)
                .where(QuotaUsageRecord.scope == scope.value)
                .where(QuotaUsageRecord.period_end > period_start)
            )
            records = list(session.exec(statement))
            return sum(record.usage_count for record in records)

    def cleanup_old_records(self, days_to_keep: int = 30) -> int:
        """Remove quota records older than the specified number of days.

        Args:
            days_to_keep: Number of days of history to retain (default: 30)

        Returns:
            Number of records deleted

        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

        with Session(self._engine) as session:
            statement = select(QuotaUsageRecord).where(QuotaUsageRecord.period_end < cutoff)
            old_records = list(session.exec(statement))
            count = len(old_records)

            for record in old_records:
                session.delete(record)

            session.commit()

        if count > 0:
            logger.info("Cleaned up %d old quota records (older than %d days)", count, days_to_keep)

        return count

    def reset_user_quota(self, user_id: str, scope: QuotaScope | None = None) -> None:
        """Reset quota usage for a user (admin operation).

        Args:
            user_id: User identifier
            scope: Optional specific scope to reset (None = all scopes)

        """
        with Session(self._engine) as session:
            statement = select(QuotaUsageRecord).where(QuotaUsageRecord.user_id == user_id)

            if scope is not None:
                statement = statement.where(QuotaUsageRecord.scope == scope.value)

            records = list(session.exec(statement))

            for record in records:
                session.delete(record)

            session.commit()

        scope_text = f"scope {scope.value}" if scope else "all scopes"
        logger.info("Reset quota for user %s (%s)", user_id, scope_text)


_persistent_quota_policy: PersistentQuotaPolicy | None = None


def get_persistent_quota_policy(database_url: str, window_hours: int = 24) -> PersistentQuotaPolicy:
    """Get or create the global persistent quota policy instance.

    Args:
        database_url: SQLite database URL (used on first call)
        window_hours: Rolling window size in hours (used on first call)

    Returns:
        Global PersistentQuotaPolicy instance

    """
    global _persistent_quota_policy
    if _persistent_quota_policy is None:
        _persistent_quota_policy = PersistentQuotaPolicy(database_url, window_hours)
    return _persistent_quota_policy
