"""The `ImportRun` aggregate (P2-M3-T03): every allowed transition, every other one refused,
the jobs it waits for, and the apply rules of plan §2 decision 58."""

from datetime import UTC, datetime, timedelta

import pytest

from riso.exchange.domain.mapping import ColumnMapping, FieldSource, ImportType
from riso.exchange.domain.report import DryRunReport, Issue
from riso.exchange.domain.run import (
    TRANSITIONS,
    ImportApplied,
    ImportFile,
    ImportRun,
    ImportRunCreated,
    RunState,
)
from riso.exchange.domain.table import FileFormat, ReadOptions
from riso.shared import InvalidState

T0 = datetime(2026, 11, 9, 10, tzinfo=UTC)
FILE = ImportFile("c/2026/11/" + "a" * 64 + ".csv", "a" * 64, "rozvrh.csv", 120, FileFormat.CSV)
MAPPING = ColumnMapping(
    import_type=ImportType.ACCOUNTS,
    fields={
        "su": FieldSource(column="SU"),
        "au": FieldSource(column="AU"),
        "type": FieldSource(column="Typ"),
    },
)
OPTIONS = ReadOptions(header_row=1, encoding="utf-8", delimiter=";")
HARD = Issue(severity="error", code="missing", message="required", rows=(3,), field="su")
SOFT = Issue(severity="error", code="unknown_ek", message="x", key="k", confirmable=True)


def _report(*errors: Issue) -> DryRunReport:
    return DryRunReport(checked_at=T0, rows_read=3, entries=3, errors=errors)


def _run() -> ImportRun:
    return ImportRun.new("r1", "c1", ImportType.ACCOUNTS, 2026, FILE, at=T0, actor="u1")


def _mapped() -> ImportRun:
    run = _run()
    run.map(OPTIONS, MAPPING, T0)
    return run


def _dry_run(*errors: Issue) -> ImportRun:
    run = _mapped()
    run.start_dry_run("j1", T0)
    assert run.record_dry_run("j1", _report(*errors), "v1", T0)
    return run


def _in(state: RunState) -> ImportRun:
    if state is RunState.UPLOADED:
        return _run()
    if state is RunState.MAPPED:
        return _mapped()
    if state is RunState.DRY_RUN_OK:
        return _dry_run()
    if state is RunState.DRY_RUN_FAILED:
        return _dry_run(SOFT)
    if state is RunState.APPLIED:
        run = _dry_run()
        run.request_apply("j2", T0, confirm_errors=False)
        run.applied("j2", "v2", T0)
        return run
    run = _run()
    run.cancel(T0)
    return run


def _try(run: ImportRun, target: RunState) -> None:
    """Drives the run towards `target` by the method that leads there."""
    if target is RunState.MAPPED:
        run.map(OPTIONS, MAPPING, T0)
    elif target is RunState.CANCELLED:
        run.cancel(T0)
    elif target in (RunState.DRY_RUN_OK, RunState.DRY_RUN_FAILED):
        run._go(target, T0)  # the dry run's only way there, tested below by the job
    elif target is RunState.APPLIED:
        run.request_apply("jx", T0, confirm_errors=True)
        run.applied("jx", "v9", T0)
    else:
        run._go(target, T0)


@pytest.mark.parametrize("source", list(RunState))
@pytest.mark.parametrize("target", list(RunState))
def test_the_transition_table(source, target):
    run = _in(source)
    assert run.state is source
    if (source, target) in TRANSITIONS:
        _try(run, target)
        assert run.state is target
    else:
        with pytest.raises(InvalidState):
            _try(run, target)
        assert run.state is source


def test_a_new_run_is_uploaded_and_records_an_event():
    run = _run()
    assert run.state is RunState.UPLOADED and not run.final
    assert run.events == [ImportRunCreated("r1", "c1", ImportType.ACCOUNTS, 2026)]


def test_the_owner_must_fit_the_type():
    with pytest.raises(InvalidState, match="belong to a customer"):
        ImportRun.new("r", None, ImportType.ACCOUNTS, 2026, FILE, at=T0, actor=None)
    with pytest.raises(InvalidState, match="belong to the platform"):
        ImportRun.new("r", "c1", ImportType.EK, 2026, FILE, at=T0, actor=None)
    ImportRun.new("r", None, ImportType.EK, 2026, FILE, at=T0, actor=None)


def test_a_mapping_of_another_type_is_refused():
    run = _run()
    other = ColumnMapping(import_type=ImportType.EK)
    with pytest.raises(InvalidState, match="a ek mapping"):
        run.map(OPTIONS, other, T0)


def test_a_dry_run_needs_a_mapping_and_ignores_jobs_it_does_not_await():
    run = _run()
    with pytest.raises(InvalidState, match="no mapping"):
        run.start_dry_run("j1", T0)
    run.map(OPTIONS, MAPPING, T0)
    run.start_dry_run("j1", T0)
    assert run.awaits("j1")
    assert not run.record_dry_run("j0", _report(), "v1", T0)  # an older job
    assert run.state is RunState.MAPPED
    assert run.record_dry_run("j1", _report(), "v1", T0)
    assert run.state is RunState.DRY_RUN_OK and run.based_on_version_id == "v1"
    assert not run.record_dry_run("j1", _report(), "v1", T0)  # a retry of the same job


def test_mapping_again_drops_the_report():
    run = _dry_run(HARD)
    assert run.state is RunState.DRY_RUN_FAILED and run.report is not None
    run.map(OPTIONS, MAPPING, T0 + timedelta(minutes=1))
    assert run.state is RunState.MAPPED and run.report is None
    assert run.based_on_version_id is None and run.updated_at == T0 + timedelta(minutes=1)


def test_a_new_dry_run_after_one_goes_back_to_mapped():
    run = _dry_run(SOFT)
    run.start_dry_run("j3", T0)
    assert run.state is RunState.MAPPED and run.report is None and run.awaits("j3")


def test_applying_needs_a_dry_run_without_hard_errors():
    with pytest.raises(InvalidState, match="dry run first"):
        _mapped().request_apply("j", T0, confirm_errors=False)
    run = _dry_run(HARD, SOFT)
    with pytest.raises(InvalidState, match="cannot be imported"):
        run.request_apply("j", T0, confirm_errors=True)
    assert not run.applying


def test_confirmable_errors_need_the_confirmation():
    run = _dry_run(SOFT)
    with pytest.raises(InvalidState, match="confirm them"):
        run.request_apply("j2", T0, confirm_errors=False)
    run.request_apply("j2", T0, confirm_errors=True)
    assert run.applying and run.errors_confirmed
    assert run.applied("j2", "v2", T0)
    assert run.state is RunState.APPLIED and run.version_id == "v2" and run.final
    assert run.events[-1] == ImportApplied("r1", "c1", ImportType.ACCOUNTS, 2026, "v2", True)


def test_a_clean_run_records_no_confirmation():
    run = _dry_run()
    run.request_apply("j2", T0, confirm_errors=True)
    assert not run.errors_confirmed


def test_while_applying_the_run_cannot_change():
    run = _dry_run()
    run.request_apply("j2", T0, confirm_errors=False)
    for change in (
        lambda: run.map(OPTIONS, MAPPING, T0),
        lambda: run.start_dry_run("j3", T0),
        lambda: run.request_apply("j3", T0, confirm_errors=False),
        lambda: run.cancel(T0),
    ):
        with pytest.raises(InvalidState, match="being applied"):
            change()
    assert not run.applied("j9", "v2", T0)  # not the awaited job
    assert run.applying


def test_a_refused_apply_goes_back_to_mapped_with_the_reason():
    run = _dry_run(SOFT)
    run.request_apply("j2", T0, confirm_errors=True)
    assert not run.apply_refused("j9", "x", T0)
    assert run.apply_refused("j2", "the list changed since the dry run", T0)
    assert run.state is RunState.MAPPED and not run.applying and run.report is None
    assert run.last_error == "the list changed since the dry run"
    assert not run.errors_confirmed
