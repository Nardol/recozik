"""Job persistence and notifier helpers for Recozik web."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlmodel import JSON, Column, Field, Session, SQLModel, create_engine, select


class JobStatus(str, Enum):
    """Lifecycle statuses for identify jobs."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobRecord(SQLModel, table=True):
    """Database representation of an identify job."""

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    user_id: str | None = Field(default=None, index=True)
    status: JobStatus = Field(default=JobStatus.QUEUED)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    messages: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    result: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    error: str | None = None


class JobRepository:
    """Simple SQLModel-backed repository for jobs."""

    def __init__(self, database_url: str) -> None:
        """Initialize the SQLModel engine for job persistence."""
        connect_args: dict[str, Any] = {}
        if database_url.startswith("sqlite:///"):
            sqlite_path = Path(database_url.replace("sqlite:///", "", 1))
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            connect_args = {"check_same_thread": False}
        self._engine = create_engine(database_url, connect_args=connect_args)
        SQLModel.metadata.create_all(self._engine)

    def create_job(self, *, user_id: str | None) -> JobRecord:
        """Insert a new job record owned by the provided user and return it."""
        job = JobRecord(user_id=user_id)
        with Session(self._engine) as session:
            session.add(job)
            session.commit()
            session.refresh(job)
        _NOTIFIER.publish(
            job.id,
            {
                "type": "status",
                "status": job.status.value,
                "timestamp": job.updated_at.isoformat(),
            },
        )
        return job

    def get(self, job_id: str) -> JobRecord | None:
        """Fetch a job by identifier."""
        with Session(self._engine) as session:
            return session.get(JobRecord, job_id)

    def list_messages(self, job_id: str) -> list[str]:
        """Return accumulated messages for the job, if it exists."""
        job = self.get(job_id)
        return list(job.messages) if job else []

    def as_dict(self, job: JobRecord) -> dict[str, Any]:
        """Serialize a job to JSON-friendly primitives."""

        def _dt(value: datetime | None) -> str | None:
            return value.isoformat() if value else None

        return {
            "job_id": job.id,
            "status": job.status.value,
            "created_at": _dt(job.created_at),
            "updated_at": _dt(job.updated_at),
            "finished_at": _dt(job.finished_at),
            "messages": list(job.messages),
            "result": job.result,
            "error": job.error,
        }

    def set_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> JobRecord | None:
        """Persist a status change and optional result/error."""
        now = datetime.now(timezone.utc)
        with Session(self._engine) as session:
            job = session.get(JobRecord, job_id)
            if not job:
                return None
            job.status = status
            job.updated_at = now
            if status in {JobStatus.COMPLETED, JobStatus.FAILED}:
                job.finished_at = now
                job.result = result
                job.error = error
            session.add(job)
            session.commit()
            session.refresh(job)
            _NOTIFIER.publish(
                job.id,
                {
                    "type": "status",
                    "status": job.status.value,
                    "timestamp": job.updated_at.isoformat(),
                    "error": job.error,
                },
            )
            if job.result is not None:
                _NOTIFIER.publish(
                    job.id,
                    {
                        "type": "result",
                        "result": job.result,
                    },
                )
            return job

    def append_message(self, job_id: str, message: str) -> JobRecord | None:
        """Append a message to the job and notify listeners."""
        now = datetime.now(timezone.utc)
        with Session(self._engine) as session:
            job = session.get(JobRecord, job_id)
            if not job:
                return None
            job.messages.append(message)
            job.updated_at = now
            session.add(job)
            session.commit()
            session.refresh(job)
            _NOTIFIER.publish(
                job.id,
                {
                    "type": "message",
                    "message": message,
                    "timestamp": job.updated_at.isoformat(),
                },
            )
            return job

    def list_jobs(
        self,
        *,
        user_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[JobRecord]:
        """Return recent jobs optionally filtered by owner."""
        statement = select(JobRecord).order_by(
            JobRecord.__table__.c.created_at.desc()  # type: ignore[attr-defined]
        )
        if user_id is not None:
            statement = statement.where(JobRecord.user_id == user_id)
        statement = statement.offset(offset).limit(limit)
        with Session(self._engine) as session:
            return list(session.exec(statement))


class JobNotifier:
    """Fan-out notifier used for WebSocket streaming."""

    def __init__(self) -> None:
        """Prepare the in-memory subscriber registry."""
        self._queues: dict[
            str, set[tuple[asyncio.Queue[dict[str, Any]], asyncio.AbstractEventLoop]]
        ] = defaultdict(set)

    def subscribe(self, job_id: str) -> asyncio.Queue[dict[str, Any]]:
        """Register a queue for the provided job ID."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        self._queues[job_id].add((queue, loop))
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Remove a queue from the subscriber list."""
        pairs = self._queues.get(job_id)
        if not pairs:
            return
        filtered = {pair for pair in pairs if pair[0] is not queue}
        if filtered:
            self._queues[job_id] = filtered
        else:
            self._queues.pop(job_id, None)

    def publish(self, job_id: str, payload: dict[str, Any]) -> None:
        """Fan out payloads to every subscriber."""
        for queue, loop in list(self._queues.get(job_id, set())):
            loop.call_soon_threadsafe(queue.put_nowait, payload)


_REPOSITORIES: dict[str, JobRepository] = {}
_NOTIFIER = JobNotifier()


def get_job_repository(database_url: str) -> JobRepository:
    """Return cached job repository for the given database URL."""
    repo = _REPOSITORIES.get(database_url)
    if repo is None:
        repo = JobRepository(database_url)
        _REPOSITORIES[database_url] = repo
    return repo


def get_notifier() -> JobNotifier:
    """Return the global job notifier instance."""
    return _NOTIFIER
