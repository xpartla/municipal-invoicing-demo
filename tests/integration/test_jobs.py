"""The jobs table and the worker, on a real SQLite file."""

import threading
import time
from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel

from riso.cli import main
from riso.jobs import JobRegistry, JobStatus, Worker, register_builtin
from riso.jobs.domain import Job
from riso.jobs.infrastructure.thread import WorkerThread
from riso.jobs.infrastructure.uow import SqlJobsUnitOfWork, jobs_uow_factory
from riso.platform import Database
from riso.shared import FixedClock, NotFound, UuidV7Generator, ValidationFailed

T0 = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


class Empty(BaseModel):
    pass


class Setup:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.clock = FixedClock(T0)
        self.ids = UuidV7Generator(self.clock)
        self.registry = register_builtin(JobRegistry())
        self.failures: Counter[str] = Counter()
        self.release = threading.Event()
        self.registry.register("flaky", Empty, self._flaky)
        self.registry.register("broken", Empty, self._broken)
        self.registry.register("blocking", Empty, self._blocking)

    def _flaky(self, payload: Empty, context) -> None:
        if self.failures[context.job_id] < 1:
            self.failures[context.job_id] += 1
            raise RuntimeError(f"transient failure of job {context.job_id}")

    def _broken(self, payload: Empty, context) -> None:
        raise RuntimeError("always fails")

    def _blocking(self, payload: Empty, context) -> None:
        assert self.release.wait(10)

    def uow(self, immediate: bool = True) -> SqlJobsUnitOfWork:
        return SqlJobsUnitOfWork(
            self.db, self.registry, clock=self.clock, ids=self.ids, immediate=immediate
        )

    def worker(self, db: Database | None = None, worker_id: str = "w1") -> Worker:
        factory = jobs_uow_factory(db or self.db, self.registry, clock=self.clock, ids=self.ids)
        return Worker(factory, self.registry, worker_id=worker_id)

    def enqueue(self, kind: str, payload: dict | None = None, **options) -> str:
        with self.uow() as uow:
            job_id = uow.queue.enqueue(kind, payload or {}, **options)
            uow.commit()
        return job_id

    def job(self, job_id: str) -> Job:
        with self.uow(immediate=False) as uow:
            return uow.jobs.get(job_id)


@pytest.fixture
def setup(migrated) -> Setup:
    return Setup(migrated)


def test_a_job_runs_and_keeps_its_result(setup):
    job_id = setup.enqueue("noop", {"note": "hello"}, customer_id="c1", created_by="u1")
    assert setup.worker().run_pending() == 1
    job = setup.job(job_id)
    assert job.status is JobStatus.SUCCEEDED
    assert job.result == {"note": "hello", "attempt": 1}
    assert (job.attempts, job.customer_id, job.created_by) == (1, "c1", "u1")
    assert (job.started_at, job.finished_at, job.locked_by) == (T0, T0, None)


def test_a_failure_is_retried_after_the_backoff(setup):
    job_id = setup.enqueue("flaky")
    worker = setup.worker()
    assert worker.run_pending() == 1
    job = setup.job(job_id)
    assert (job.status, job.attempts) == (JobStatus.QUEUED, 1)
    assert job.run_after == T0 + timedelta(seconds=5)
    assert job.last_error == f"RuntimeError: transient failure of job {job_id}"
    assert worker.run_pending() == 0  # not due yet
    setup.clock.advance(timedelta(seconds=5))
    assert worker.run_pending() == 1
    job = setup.job(job_id)
    assert (job.status, job.attempts, len(job.errors)) == (JobStatus.SUCCEEDED, 2, 1)


def test_a_job_gives_up_after_three_attempts(setup):
    job_id = setup.enqueue("broken")
    worker = setup.worker()
    for _ in range(3):
        assert worker.run_pending() == 1
        setup.clock.advance(timedelta(minutes=1))
    job = setup.job(job_id)
    assert (job.status, job.attempts) == (JobStatus.FAILED, 3)
    assert [e.attempt for e in job.errors] == [1, 2, 3]
    assert worker.run_pending() == 0


def test_an_unknown_kind_fails_at_once(setup):
    with setup.uow() as uow:
        uow.jobs.add(Job.new("j-gone", "gone", {}, T0))
        uow.commit()
    assert setup.worker().run_pending() == 1
    job = setup.job("j-gone")
    assert (job.status, job.attempts) == (JobStatus.FAILED, 1)
    assert job.last_error == "NotFound: no job kind gone"


def test_enqueueing_checks_the_kind_and_the_payload(setup):
    with pytest.raises(NotFound):
        setup.enqueue("gone")
    with pytest.raises(ValidationFailed):
        setup.enqueue("noop", {"unexpected": 1})


def test_a_job_queued_in_a_rolled_back_transaction_never_runs(setup):
    with setup.uow() as uow:
        uow.queue.enqueue("noop", {})
    assert setup.worker().run_pending() == 0


def test_a_job_waits_until_it_is_due(setup):
    job_id = setup.enqueue("noop", run_after=T0 + timedelta(hours=1))
    assert setup.worker().run_pending() == 0
    setup.clock.advance(timedelta(hours=1))
    assert setup.worker().run_pending() == 1
    assert setup.job(job_id).status is JobStatus.SUCCEEDED


def test_an_expired_lease_is_claimed_again(setup):
    job_id = setup.enqueue("noop")
    with setup.uow(immediate=True) as uow:  # a worker claims it, then dies
        job = uow.jobs.next_claimable(T0)
        job.claim(T0, "dead-worker", timedelta(minutes=10))
        uow.jobs.save(job)
        uow.commit()
    assert setup.worker().run_pending() == 0  # still leased
    setup.clock.advance(timedelta(minutes=10))
    assert setup.worker().run_pending() == 1
    job = setup.job(job_id)
    assert (job.status, job.attempts) == (JobStatus.SUCCEEDED, 2)
    assert "lease expired" in job.errors[0].message


def test_two_workers_never_claim_the_same_job(setup, db_url):
    runs: list[str] = []
    lock = threading.Lock()

    def record(payload: Empty, context) -> None:
        with lock:
            runs.append(context.job_id)
        time.sleep(0.002)

    setup.registry.register("record", Empty, record)
    job_ids = [setup.enqueue("record") for _ in range(60)]

    second_db = Database(db_url)  # a second engine: its own connections
    workers = [setup.worker(setup.db, "w1"), setup.worker(second_db, "w2")]
    threads = [threading.Thread(target=w.run_pending) for w in workers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    second_db.dispose()

    assert Counter(runs) == Counter(job_ids)  # every job ran exactly once
    assert {setup.job(j).status for j in job_ids} == {JobStatus.SUCCEEDED}


def wait_for(condition, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("timed out")
        time.sleep(0.01)


def test_the_worker_thread_runs_jobs_and_stops_cleanly(setup):
    thread = WorkerThread(setup.worker(), poll_interval=0.05)
    thread.start()
    assert thread.running
    job_id = setup.enqueue("noop")
    thread.wake()
    wait_for(lambda: setup.job(job_id).status is JobStatus.SUCCEEDED)
    assert thread.stop()
    assert not thread.running


def test_stopping_waits_for_the_job_in_hand(setup):
    thread = WorkerThread(setup.worker(), poll_interval=0.05)
    thread.start()
    job_id = setup.enqueue("blocking")
    thread.wake()
    wait_for(lambda: setup.job(job_id).status is JobStatus.RUNNING)
    assert not thread.stop(timeout=0.2)  # still in the job
    setup.release.set()
    assert thread.stop(timeout=5)
    assert setup.job(job_id).status is JobStatus.SUCCEEDED


def test_riso_worker_once_runs_the_due_jobs(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("RISO_VAR_DIR", str(tmp_path))
    monkeypatch.delenv("RISO_DB_URL", raising=False)
    assert main(["migrate"]) == 0
    from riso.api.composition import build_services

    services = build_services()
    with services.jobs_uow() as uow:
        uow.queue.enqueue("noop", {})
        uow.queue.enqueue("noop", {"note": "second"})
        uow.commit()
    services.close()
    capsys.readouterr()
    assert main(["worker", "--once"]) == 0
    assert capsys.readouterr().out == "ran 2 job(s)\n"
