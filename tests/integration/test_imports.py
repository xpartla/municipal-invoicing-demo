"""Import runs end to end on a seeded database (P2-M3-T03): upload, mapping, the dry run
and apply jobs, the report's errors and warnings, applying with and without confirmation, a
list that changed meanwhile, idempotent jobs, a global list, and permissions."""

import csv
import io
from dataclasses import replace

import openpyxl
import pytest

from riso.api.composition import build_services
from riso.audit.domain.event import AuditFilter
from riso.codelists.application.lists import EditEntry, edit_list
from riso.codelists.domain import ListKind, VersionOrigin
from riso.exchange.application.imports import (
    ImportJobPayload,
    UploadImport,
    cancel_import,
    create_import,
    get_import,
    list_imports,
    preview_import,
    request_apply,
    set_mapping,
    start_dry_run,
)
from riso.exchange.domain.mapping import (
    ColumnMapping,
    Fact,
    FieldSource,
    ImportType,
    Trim,
    ZeroPad,
)
from riso.exchange.domain.run import RunState
from riso.exchange.domain.table import ReadOptions
from riso.identity.application.access import Grant
from riso.identity.infrastructure.hashing import Argon2Hasher
from riso.jobs import JobContext, JobStatus
from riso.platform import Settings
from riso.shared import InvalidState, PermissionDenied, RequestContext, ValidationFailed
from riso.store import StateStore

PASSWORD = "Ukážkové-heslo-2026"
YEAR = 2026


@pytest.fixture
def env(tmp_path, seeded_copy):
    settings = Settings(var_dir=tmp_path / "var", env="test")
    done = seeded_copy(settings.var_dir)
    services = build_services(settings, hasher=Argon2Hasher.fast())
    yield services, done
    services.close()


def _ctx(services, user_id: str) -> RequestContext:
    with services.uow(immediate=False) as uow:
        user = uow.users.get(user_id)
        grants = tuple(Grant(m.scope.kind, m.scope.id, m.role) for m in user.active_memberships())
    return RequestContext("test", user_id, policy=services.policy(grants))


@pytest.fixture
def boldog(env):
    services, done = env
    return services, done.customers["Obec Boldog"], _ctx(services, done.users["user"][0])


def _csv(rows: list[list[object]]) -> bytes:
    out = io.StringIO()
    csv.writer(out, delimiter=";", lineterminator="\r\n").writerows(rows)
    return out.getvalue().encode("windows-1250")


def _active(services, customer_id, kind):
    with services.uow(immediate=False) as uow:
        return uow.codelists.active(customer_id, kind, YEAR)


def _chart_rows(services, customer_id) -> list[list[object]]:
    version = _active(services, customer_id, ListKind.ACCOUNTS)
    types = {"active": "Aktívny", "passive": "Pasívny", "cost": "Nákladový", "revenue": "Výnosový"}
    return [
        [e.su, e.au, types[e.type], e.activity or "", e.description or ""] for e in version.entries
    ]


CHART_HEADER = ["SU", "AU", "Typ účtu", "Činnosť", "Popis"]


def _upload(services, ctx, customer_id, data, import_type=ImportType.ACCOUNTS, name="rozvrh.csv"):
    return create_import(
        ctx,
        services.uow(),
        services.storage,
        services.reader,
        UploadImport(customer_id, import_type, YEAR, name, data),
    )


def _map_suggested(services, ctx, customer_id, run, options=None):
    preview = preview_import(
        ctx, services.uow(), services.storage, services.reader, customer_id, run.id, options
    )
    options = options or ReadOptions(
        header_row=preview.header_row, encoding=preview.encoding, delimiter=preview.delimiter
    )
    return set_mapping(
        ctx,
        services.uow(),
        services.storage,
        services.reader,
        customer_id,
        run.id,
        options,
        preview.suggestion,
    )


def _dry_run(services, ctx, customer_id, run):
    start_dry_run(ctx, services.uow(), customer_id, run.id)
    assert services.worker().run_pending() >= 1
    return get_import(ctx, services.uow(), customer_id, run.id)


def _apply(services, ctx, customer_id, run, *, confirm=False):
    request_apply(ctx, services.uow(), customer_id, run.id, confirm_errors=confirm)
    assert services.worker().run_pending() >= 1
    return get_import(ctx, services.uow(), customer_id, run.id)


def _events(services, customer_id, action=None):
    with services.uow(immediate=False) as uow:
        events, _ = uow.audit_log.page(
            AuditFilter(customer_id=customer_id, action=action), size=200
        )
    return events


def _audit(services, customer_id):
    return [e.action for e in _events(services, customer_id)]


def test_a_clean_run_from_upload_to_a_new_version(boldog):
    services, boldog_id, ctx = boldog
    rows = _chart_rows(services, boldog_id)
    rows[0][4] = "Zmenený popis"  # changed
    removed = rows.pop(1)  # removed
    rows.append(["518", "099", "Nákladový", "", "Nový účet"])  # added
    run = _upload(services, ctx, boldog_id, _csv([CHART_HEADER, *rows]))
    assert run.state is RunState.UPLOADED and run.file_name == "rozvrh.csv"

    preview = preview_import(
        ctx, services.uow(), services.storage, services.reader, boldog_id, run.id
    )
    assert preview.format == "csv" and preview.encoding == "windows-1250"
    assert preview.header_row == 1 and preview.data_rows == len(rows)
    assert preview.rows[0].number == 2
    assert set(preview.suggestion.fields) == {"su", "au", "type", "activity", "description"}

    run = _map_suggested(services, ctx, boldog_id, run)
    assert run.state is RunState.MAPPED
    before = _active(services, boldog_id, ListKind.ACCOUNTS)

    run = _dry_run(services, ctx, boldog_id, run)
    assert run.state is RunState.DRY_RUN_OK, run.report.errors
    report = run.report
    assert report.rows_read == len(rows) and report.entries == len(rows)
    assert (report.diff.added, report.diff.removed, report.diff.changed) == (1, 1, 1)
    assert report.diff.base_version_id == before.id
    assert report.diff.removed_sample[0]["su"] == removed[0]
    assert report.diff.changed_sample[0].after["description"] == "Zmenený popis"
    assert len(report.preview) == 20
    # Boldog's chart has synthetic accounts the 2022 framework chart lacks: warnings only.
    assert {w.code for w in report.warnings} <= {
        "unknown_synthetic_account",
        "missing_description",
    }

    run = _apply(services, ctx, boldog_id, run)
    assert run.state is RunState.APPLIED
    after = _active(services, boldog_id, ListKind.ACCOUNTS)
    assert after.id == run.version_id and after.number == before.number + 1
    assert after.origin is VersionOrigin.IMPORT and after.import_run_id == run.id
    assert after.source.name == "rozvrh.csv" and after.source.data_rows == len(rows)
    assert "518 099" in {e.key for e in after.entries}
    assert {"imports.uploaded", "imports.mapped", "imports.dry_run_started"} <= set(
        _audit(services, boldog_id)
    )
    assert "imports.applied" in _audit(services, boldog_id)

    items, total = list_imports(ctx, services.uow(), boldog_id)
    assert total == 1 and items[0].id == run.id


def test_a_failing_run_lists_errors_with_row_numbers_and_cannot_be_applied(boldog):
    services, boldog_id, ctx = boldog
    rows = [
        CHART_HEADER,
        ["518", "001", "Nákladový", "", "Telefóny"],
        ["5x8", "002", "Nákladový", "", "zlý SU"],
        ["518", "003", "Iný", "", "zlý typ"],
        ["518", "", "Nákladový", "", "bez AU"],
    ]
    run = _map_suggested(services, ctx, boldog_id, _upload(services, ctx, boldog_id, _csv(rows)))
    run = _dry_run(services, ctx, boldog_id, run)
    assert run.state is RunState.DRY_RUN_FAILED
    errors = {(e.rows, e.field, e.code) for e in run.report.errors}
    assert errors == {
        ((3,), "su", "string_pattern_mismatch"),
        ((4,), "type", "unknown_account_type"),
        ((5,), "au", "missing"),
    }
    assert all(not e.confirmable for e in run.report.errors)
    assert not run.can_apply
    for confirm in (False, True):
        with pytest.raises(InvalidState):
            request_apply(ctx, services.uow(), boldog_id, run.id, confirm_errors=confirm)
    assert _active(services, boldog_id, ListKind.ACCOUNTS).number == 1


def _budget_rows(services, customer_id, kind):
    version = _active(services, customer_id, kind)
    return [
        [e.ek, e.zdroj, e.oddiel or "", e.trieda or "", e.analytika, e.description or ""]
        for e in version.entries
    ]


BUDGET_HEADER = ["Kód", "Zdroj", "Oddiel", "Trieda", "Analytika", "Popis"]


def test_warnings_duplicates_missing_descriptions_and_precedents_on_removed_codes(boldog):
    services, boldog_id, ctx = boldog
    memory = StateStore(services.settings.var_dir).supplier_memory("00305863")
    used = memory.suppliers[0].precedents[0].lines[0].budget_key
    rows = [r for r in _budget_rows(services, boldog_id, ListKind.BUDGET_EXPENSE)]
    keep = [r for r in rows if " ".join(str(c) for c in r[:5] if c != "") != used]
    assert len(keep) == len(rows) - 1
    keep.append(list(keep[0][:5]) + ["Ešte raz"])  # a duplicate key, merged
    keep[1][5] = ""  # a missing description
    data = _csv([BUDGET_HEADER, *keep])
    run = _upload(services, ctx, boldog_id, data, ImportType.BUDGET_EXPENSE, "vydavky.csv")
    run = _dry_run(services, ctx, boldog_id, _map_suggested(services, ctx, boldog_id, run))
    warnings = {w.code: w for w in run.report.warnings}
    assert warnings["duplicate_key"].rows == (2, len(keep) + 1)
    assert "merged, keeping the descriptions" in warnings["duplicate_key"].message
    assert 3 in warnings["missing_description"].rows
    precedent = warnings["precedent_removed_code"]
    assert precedent.key == used and "which the import removes" in precedent.message
    # Boldog's budget has EKs and zdroje dropped from the 2026 lists (plan §2 decision 58).
    assert run.state is RunState.DRY_RUN_FAILED
    assert run.report.errors and all(e.confirmable for e in run.report.errors)
    assert {e.code for e in run.report.errors} <= {"unknown_ek", "unknown_zdroj"}
    assert run.report.diff.removed == 1


def test_errors_against_the_global_lists_need_the_confirmation(boldog):
    services, boldog_id, ctx = boldog
    rows = [
        BUDGET_HEADER,
        ["632001", "41", "01", "110", "000", "Energie"],
        ["999999", "41", "01", "110", "000", "Neznáma EK"],
        ["632002", "9Z9", "01", "110", "000", "Neznámy zdroj"],
    ]
    data = _csv(rows)
    run = _upload(services, ctx, boldog_id, data, ImportType.BUDGET_EXPENSE, "vydavky.csv")
    run = _dry_run(services, ctx, boldog_id, _map_suggested(services, ctx, boldog_id, run))
    assert run.state is RunState.DRY_RUN_FAILED and run.can_apply
    assert {(e.code, e.rows, e.confirmable) for e in run.report.errors} == {
        ("unknown_ek", (3,), True),
        ("unknown_zdroj", (4,), True),
    }
    with pytest.raises(InvalidState, match="confirm them"):
        request_apply(ctx, services.uow(), boldog_id, run.id, confirm_errors=False)
    run = _apply(services, ctx, boldog_id, run, confirm=True)
    assert run.state is RunState.APPLIED and run.errors_confirmed
    version = _active(services, boldog_id, ListKind.BUDGET_EXPENSE)
    assert [e.key for e in version.entries] == [
        "632001 41 01 110 000",
        "999999 41 01 110 000",
        "632002 9Z9 01 110 000",
    ]
    entries = _events(services, boldog_id, "imports.applied")
    assert entries[0].details["errors_confirmed"] is True
    assert entries[0].details["confirmed_errors"] == 2


def test_an_apply_after_the_list_changed_goes_back_to_mapped(boldog):
    services, boldog_id, ctx = boldog
    rows = _chart_rows(services, boldog_id)
    run = _upload(services, ctx, boldog_id, _csv([CHART_HEADER, *rows]))
    run = _dry_run(services, ctx, boldog_id, _map_suggested(services, ctx, boldog_id, run))
    assert run.state is RunState.DRY_RUN_OK
    active = _active(services, boldog_id, ListKind.ACCOUNTS)
    edit_list(
        ctx,
        services.uow(),
        boldog_id,
        ListKind.ACCOUNTS,
        YEAR,
        EditEntry(active.entries[0].key, {"description": "medzitým"}),
        version_id=active.id,
    )
    run = _apply(services, ctx, boldog_id, run)
    assert run.state is RunState.MAPPED and run.report is None
    assert run.last_error == "the list changed since the dry run"
    assert _active(services, boldog_id, ListKind.ACCOUNTS).origin is VersionOrigin.EDIT
    assert "imports.apply_refused" in _audit(services, boldog_id)
    # A new dry run against the new version, and the apply goes through.
    run = _apply(services, ctx, boldog_id, _dry_run(services, ctx, boldog_id, run))
    assert run.state is RunState.APPLIED


def test_the_jobs_are_idempotent(boldog):
    services, boldog_id, ctx = boldog
    rows = _chart_rows(services, boldog_id)
    run = _upload(services, ctx, boldog_id, _csv([CHART_HEADER, *rows]))
    run = _map_suggested(services, ctx, boldog_id, run)
    run = start_dry_run(ctx, services.uow(), boldog_id, run.id)
    jobs = services.import_jobs()
    payload = ImportJobPayload(run_id=run.id, customer_id=boldog_id)
    job = JobContext(run.job_id, "import_dry_run", 1, boldog_id, ctx.actor_id, ctx)
    assert jobs.dry_run(payload, job)["state"] == "dry_run_ok"
    assert jobs.dry_run(payload, job) == {"skipped": True}  # a retry of the same job
    stale = replace(job, job_id="not-awaited")
    assert jobs.dry_run(payload, stale) == {"skipped": True}

    run = request_apply(ctx, services.uow(), boldog_id, run.id)
    apply_job = JobContext(run.job_id, "import_apply", 1, boldog_id, ctx.actor_id, ctx)
    first = jobs.apply(payload, apply_job)
    assert jobs.apply(payload, apply_job) == {"version_id": first["version_id"]}
    assert _active(services, boldog_id, ListKind.ACCOUNTS).number == 2
    services.worker().run_pending()  # the queued copies of both jobs: nothing more happens
    assert _active(services, boldog_id, ListKind.ACCOUNTS).number == 2


def test_cancel_and_remap(boldog):
    services, boldog_id, ctx = boldog
    run = _upload(services, ctx, boldog_id, _csv([CHART_HEADER, ["518", "001", "Nákladový"]]))
    run = _dry_run(services, ctx, boldog_id, _map_suggested(services, ctx, boldog_id, run))
    run = _map_suggested(services, ctx, boldog_id, run)
    assert run.state is RunState.MAPPED and run.report is None
    run = cancel_import(ctx, services.uow(), boldog_id, run.id)
    assert run.state is RunState.CANCELLED
    with pytest.raises(InvalidState):
        start_dry_run(ctx, services.uow(), boldog_id, run.id)


def test_a_mapping_that_does_not_fit_the_file_is_refused(boldog):
    services, boldog_id, ctx = boldog
    run = _upload(services, ctx, boldog_id, _csv([CHART_HEADER, ["518", "001", "Nákladový"]]))
    bad = ColumnMapping(
        import_type=ImportType.ACCOUNTS, fields={"su": FieldSource(column="Syntetika")}
    )
    with pytest.raises(ValidationFailed) as caught:
        set_mapping(
            ctx,
            services.uow(),
            services.storage,
            services.reader,
            boldog_id,
            run.id,
            ReadOptions(header_row=1),
            bad,
        )
    assert {e.code for e in caught.value.errors} == {"unknown_column", "missing"}


def test_an_unreadable_file_is_refused_at_upload(boldog):
    services, boldog_id, ctx = boldog
    with pytest.raises(ValidationFailed) as caught:
        _upload(services, ctx, boldog_id, b"\x89PNG\r\n\x1a\n\x00\x00")
    assert caught.value.errors[0].code == "unsupported_format"


def _chart_with_title(ico: str, period: str) -> bytes:
    return _csv(
        [
            [f"UctovnyRozvrh, Obdobie: {period}. IČO: {ico}"],
            ["Obec"],
            CHART_HEADER,
            ["518", "001", "Nákladový", "", "Telefóny"],
        ]
    )


FACTS = (
    Fact(name="ico", row=1, pattern=r"IČO:\s*(?P<ico>\d{6,8})"),
    Fact(name="period", row=1, pattern=r"Obdobie:\s*(?P<month>\d{1,2})\.\s*(?P<year>\d{4})"),
)


def _map_with_facts(services, ctx, customer_id, run):
    preview = preview_import(
        ctx, services.uow(), services.storage, services.reader, customer_id, run.id
    )
    mapping = preview.suggestion.model_copy(update={"facts": FACTS})
    return set_mapping(
        ctx,
        services.uow(),
        services.storage,
        services.reader,
        customer_id,
        run.id,
        ReadOptions(header_row=3, delimiter=";"),
        mapping,
    )


def test_a_file_of_another_customer_is_a_hard_error_and_another_year_a_warning(boldog):
    services, boldog_id, ctx = boldog
    run = _upload(services, ctx, boldog_id, _chart_with_title("36126624", "08. 2026"))
    run = _dry_run(services, ctx, boldog_id, _map_with_facts(services, ctx, boldog_id, run))
    assert [(e.code, e.confirmable) for e in run.report.errors] == [("other_customer", False)]

    run = _upload(services, ctx, boldog_id, _chart_with_title("305863", "12. 2025"))
    run = _dry_run(services, ctx, boldog_id, _map_with_facts(services, ctx, boldog_id, run))
    assert run.state is RunState.DRY_RUN_OK
    assert run.report.period == "2025-12" and run.report.file_ico == "00305863"
    assert "other_year" in {w.code for w in run.report.warnings}
    run = _apply(services, ctx, boldog_id, run)
    assert _active(services, boldog_id, ListKind.ACCOUNTS).period == "2025-12"


def test_the_admin_imports_a_global_list(env):
    services, done = env
    admin = _ctx(services, done.users["admin"][0])
    with services.uow(immediate=False) as uow:
        ek = uow.codelists.active(None, ListKind.EK, YEAR)
    rows = [["code", "name"], *[[e.code, e.name] for e in ek.entries], ["999", "Nová položka"]]
    data = io.StringIO()
    csv.writer(data, lineterminator="\n").writerows(rows)
    run = _upload(services, admin, None, data.getvalue().encode(), ImportType.EK, "ek.csv")
    run = _dry_run(services, admin, None, _map_suggested(services, admin, None, run))
    assert run.state is RunState.DRY_RUN_OK and run.report.diff.added == 1
    run = _apply(services, admin, None, run)
    with services.uow(immediate=False) as uow:
        after = uow.codelists.active(None, ListKind.EK, YEAR)
    assert after.number == ek.number + 1 and after.import_run_id == run.id


def test_permissions(env, boldog):
    services, done = env
    _, boldog_id, user = boldog
    viewer = _ctx(services, done.users["viewer"][0])
    data = _csv([CHART_HEADER, ["518", "001", "Nákladový"]])
    with pytest.raises(PermissionDenied):
        _upload(services, viewer, boldog_id, data)
    with pytest.raises(PermissionDenied):
        _upload(services, user, None, data, ImportType.EK)  # a global list: admins only
    run = _upload(services, user, boldog_id, data)
    list_imports(viewer, services.uow(), boldog_id)  # the history is readable
    with pytest.raises(PermissionDenied):
        start_dry_run(viewer, services.uow(), boldog_id, run.id)
    other = done.customers["Obec Nezávislá"]
    with pytest.raises(PermissionDenied):
        get_import(user, services.uow(), other, run.id)


def test_a_job_runs_with_the_starters_permissions(env, boldog):
    services, done = env
    _, boldog_id, user = boldog
    run = _upload(services, user, boldog_id, _csv([CHART_HEADER, ["518", "001", "Nákladový"]]))
    run = _map_suggested(services, user, boldog_id, run)
    run = start_dry_run(user, services.uow(), boldog_id, run.id)
    # The user loses Boldog before the worker runs: the job is refused (and retried later,
    # as any failed job, until its attempts run out).
    with services.uow() as uow:
        account = uow.users.get(done.users["user"][0])
        account.deactivate_membership(account.active_memberships()[0].scope, services.clock.now())
        uow.users.save(account)
        uow.commit()
    services.worker().run_pending()
    with services.jobs_uow(immediate=False) as uow:
        job = uow.jobs.get(run.job_id)
    assert job.status is not JobStatus.SUCCEEDED and "PermissionDenied" in job.last_error
    assert (
        get_import(_ctx(services, done.users["admin"][0]), services.uow(), boldog_id, run.id).state
        is RunState.MAPPED
    )


def test_zero_padding_codes_written_as_numbers(boldog):
    services, boldog_id, ctx = boldog
    rows = [CHART_HEADER, [518, 1, "Nákladový", "", "Telefóny"]]
    data = io.BytesIO()
    workbook = openpyxl.Workbook()
    for row in rows:
        workbook.active.append(row)
    workbook.save(data)
    run = _upload(services, ctx, boldog_id, data.getvalue(), name="rozvrh.xlsx")
    run = _dry_run(services, ctx, boldog_id, _map_suggested(services, ctx, boldog_id, run))
    assert run.report.preview[0]["su"] == "518" and run.report.preview[0]["au"] == "001"
    assert run.mapping.fields["au"].transforms == (Trim(), ZeroPad(width=3))
