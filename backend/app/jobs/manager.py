"""In-process job registry + worker pool (SPEC §5.4)."""

import asyncio
import multiprocessing
import queue as queue_mod
import uuid
from collections.abc import Callable
from concurrent.futures import Executor, ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from app.analysis.fetch import RepoSpec
from app.errors import AppError
from app.jobs.pipeline import run_pipeline

MAX_KEPT_JOBS = 50


@dataclass
class Job:
    id: str
    key: tuple[str, str, str | None]
    events: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = False

    def push(self, event: str, data: dict[str, Any]) -> None:
        self.events.append({"event": event, "data": data})
        if event in ("done", "error"):
            self.finished = True


class JobManager:
    def __init__(
        self,
        executor: Executor | None = None,
        queue_factory: Callable[[], Any] | None = None,
        pipeline: Callable[[RepoSpec, Any], dict[str, Any]] = run_pipeline,
        timeout_s: float = 600,
        max_workers: int = 2,
        finalize: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ):
        # Runs in the API process on the pipeline result (e.g. persists the diagram).
        self.finalize = finalize
        self._executor = executor
        self._queue_factory = queue_factory
        self._pipeline = pipeline
        self._timeout_s = timeout_s
        self._max_workers = max_workers
        self._mp_manager: Any = None
        self.jobs: dict[str, Job] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def start(self) -> None:
        if self._executor is None:
            # spawn, not fork: the API process runs threads.
            ctx = multiprocessing.get_context("spawn")
            self._mp_manager = ctx.Manager()
            self._queue_factory = self._mp_manager.Queue
            self._executor = ProcessPoolExecutor(self._max_workers, mp_context=ctx)
        elif self._queue_factory is None:
            self._queue_factory = queue_mod.Queue

    def stop(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
        if self._mp_manager is not None:
            self._mp_manager.shutdown()

    def get(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None:
            raise AppError("JOB_NOT_FOUND", "Unknown job.")
        return job

    def submit(self, spec: RepoSpec) -> Job:
        key = (spec.owner.lower(), spec.name.lower(), spec.ref)
        for job in self.jobs.values():  # one job at a time per repo
            if job.key == key and not job.finished:
                return job
        job = Job(id=uuid.uuid4().hex, key=key)
        self.jobs[job.id] = job
        self._prune()
        task = asyncio.get_running_loop().create_task(self._run(job, spec))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    def _prune(self) -> None:
        finished = [j for j in self.jobs.values() if j.finished]
        for j in finished[: max(0, len(self.jobs) - MAX_KEPT_JOBS)]:
            del self.jobs[j.id]

    async def _run(self, job: Job, spec: RepoSpec) -> None:
        assert self._executor is not None and self._queue_factory is not None
        loop = asyncio.get_running_loop()
        q = self._queue_factory()

        def drain() -> None:
            while True:
                try:
                    item = q.get_nowait()
                except queue_mod.Empty:
                    return
                job.push(item["event"], item["data"])

        fut = loop.run_in_executor(self._executor, self._pipeline, spec, q)
        deadline = loop.time() + self._timeout_s
        try:
            while not fut.done():
                if loop.time() > deadline:
                    raise AppError(
                        "TIMEOUT", f"Analysis exceeded {int(self._timeout_s)}s and was stopped."
                    )
                drain()
                await asyncio.wait({fut}, timeout=0.1)
            drain()
            job.push("done", self.finalize(fut.result()) if self.finalize else fut.result())
        except AppError as e:
            drain()
            job.push("error", {"code": e.code, "message": e.message})
        except Exception as e:  # noqa: BLE001 - surface anything unexpected to the UI
            job.push("error", {"code": "INTERNAL_ERROR", "message": f"{type(e).__name__}: {e}"})
