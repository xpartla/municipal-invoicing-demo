"""The job lifecycle: every allowed transition, every refused one, retries and leases."""

from datetime import UTC, datetime, timedelta

import pytest

from riso.jobs.domain import TRANSITIONS, Job, JobStatus, RetryPolicy
from riso.shared import InvalidState

T0 = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
LEASE = timedelta(minutes=10)
RETRY = RetryPolicy(base_delay=timedelta(seconds=5))


def job(**changes) -> Job:
    made = Job.new("j1", "noop", {}, T0)
    for name, value in changes.items():
        setattr(made, name, value)
    return made


def running(attempts: int = 1) -> Job:
    made = job()
    made.claim(T0, "w1", LEASE)
    made.attempts = attempts
    return made


def test_a_new_job_is_queued_and_due_now():
    made = job()
    assert made.status is JobStatus.QUEUED
    assert made.is_claimable(T0)
    assert not made.is_claimable(T0 - timedelta(seconds=1))


def test_claiming_starts_an_attempt_under_a_lease():
    made = job()
    assert made.claim(T0, "w1", LEASE)
    assert (made.status, made.attempts, made.locked_by) == (JobStatus.RUNNING, 1, "w1")
    assert made.locked_until == T0 + LEASE
    assert not made.is_claimable(T0 + LEASE - timedelta(seconds=1))
    assert made.is_claimable(T0 + LEASE)


def test_a_job_that_is_not_due_cannot_be_claimed():
    with pytest.raises(InvalidState):
        job(run_after=T0 + timedelta(minutes=1)).claim(T0, "w1", LEASE)


def test_success_keeps_the_result_and_releases_the_lease():
    made = running()
    made.succeed(T0 + timedelta(seconds=1), {"pages": 2})
    assert (made.status, made.result, made.locked_by) == (JobStatus.SUCCEEDED, {"pages": 2}, None)
    assert made.finished_at == T0 + timedelta(seconds=1)


@pytest.mark.parametrize(("attempt", "delay"), [(1, 5), (2, 10), (3, 20)])
def test_the_backoff_doubles(attempt, delay):
    assert RETRY.delay(attempt) == timedelta(seconds=delay)


def test_a_failure_with_attempts_left_is_queued_after_the_backoff():
    made = running(attempts=1)
    made.fail(T0, "RuntimeError: boom", RETRY)
    assert made.status is JobStatus.QUEUED
    assert made.run_after == T0 + timedelta(seconds=5)
    assert made.last_error == "RuntimeError: boom"
    assert made.errors[0].attempt == 1


def test_the_last_attempt_fails_the_job():
    made = running(attempts=3)
    made.fail(T0, "RuntimeError: boom", RETRY)
    assert made.status is JobStatus.FAILED
    assert made.finished_at == T0


def test_a_permanent_failure_does_not_retry():
    made = running(attempts=1)
    made.fail(T0, "NotFound: no job kind x", RETRY, permanent=True)
    assert made.status is JobStatus.FAILED


def test_error_texts_are_capped():
    made = running()
    made.fail(T0, "x" * 2000, RETRY)
    assert len(made.errors[0].message) == 500


def test_an_expired_lease_is_reclaimed_as_a_failed_attempt():
    made = running(attempts=1)
    later = T0 + LEASE
    assert made.claim(later, "w2", LEASE)
    assert (made.status, made.attempts, made.locked_by) == (JobStatus.RUNNING, 2, "w2")
    assert "lease expired" in made.errors[0].message


def test_an_expired_lease_on_the_last_attempt_fails_the_job():
    made = running(attempts=3)
    assert not made.claim(T0 + LEASE, "w2", LEASE)
    assert made.status is JobStatus.FAILED


def test_an_admin_retry_gives_a_failed_job_fresh_attempts():
    made = running(attempts=3)
    made.fail(T0, "boom", RETRY)
    made.retry(T0 + timedelta(hours=1))
    assert (made.status, made.attempts) == (JobStatus.QUEUED, 0)
    assert made.is_claimable(T0 + timedelta(hours=1))


def test_a_queued_job_can_be_cancelled():
    made = job()
    made.cancel(T0)
    assert made.status is JobStatus.CANCELLED
    assert not made.is_claimable(T0)


# Every pair of states: the allowed ones are exactly TRANSITIONS.
ACTIONS = {
    (JobStatus.QUEUED, JobStatus.RUNNING): lambda j: j.claim(T0, "w", LEASE),
    (JobStatus.RUNNING, JobStatus.RUNNING): lambda j: j.claim(T0 + LEASE, "w", LEASE),
    (JobStatus.RUNNING, JobStatus.SUCCEEDED): lambda j: j.succeed(T0),
    (JobStatus.RUNNING, JobStatus.QUEUED): lambda j: j.fail(T0, "e", RETRY),
    (JobStatus.RUNNING, JobStatus.FAILED): lambda j: j.fail(T0, "e", RETRY, permanent=True),
    (JobStatus.QUEUED, JobStatus.CANCELLED): lambda j: j.cancel(T0),
    (JobStatus.FAILED, JobStatus.QUEUED): lambda j: j.retry(T0),
}


def in_state(status: JobStatus) -> Job:
    made = job()
    if status is not JobStatus.QUEUED:
        made.claim(T0, "w", LEASE)
    if status is JobStatus.SUCCEEDED:
        made.succeed(T0)
    elif status is JobStatus.FAILED:
        made.fail(T0, "e", RETRY, permanent=True)
    elif status is JobStatus.CANCELLED:
        made = job()
        made.cancel(T0)
    assert made.status is status
    return made


def test_the_table_lists_exactly_the_actions():
    assert set(ACTIONS) == TRANSITIONS


@pytest.mark.parametrize(("source", "target"), sorted(TRANSITIONS))
def test_every_allowed_transition_happens(source, target):
    made = in_state(source)
    ACTIONS[(source, target)](made)
    assert made.status is target


# Each method, and the states it may start from; from every other state it is refused.
METHODS = {
    "claim": (lambda j: j.claim(T0 + LEASE, "w", LEASE), {JobStatus.QUEUED, JobStatus.RUNNING}),
    "succeed": (lambda j: j.succeed(T0), {JobStatus.RUNNING}),
    "fail": (lambda j: j.fail(T0, "e", RETRY), {JobStatus.RUNNING}),
    "cancel": (lambda j: j.cancel(T0), {JobStatus.QUEUED}),
    "retry": (lambda j: j.retry(T0), {JobStatus.FAILED}),
}


def test_the_methods_start_from_the_sources_of_the_table():
    assert set().union(*(valid for _, valid in METHODS.values())) == {s for s, _ in TRANSITIONS}


@pytest.mark.parametrize(
    ("method", "source"),
    [
        (method, source)
        for method, (_, valid) in sorted(METHODS.items())
        for source in JobStatus
        if source not in valid
    ],
)
def test_every_other_transition_is_refused(method, source):
    made = in_state(source)
    with pytest.raises(InvalidState):
        METHODS[method][0](made)
