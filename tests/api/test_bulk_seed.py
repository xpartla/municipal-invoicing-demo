"""`riso seed --bulk N` (P2-M8-T04, decision 68): synthetic invoices for Boldog to measure the
invoice table with: states over the whole lifecycle, the booked ones numbered in their series
in the order of their dates of supply, the same invoices for the same N and seed, Boldog's
supplier memory untouched, and a refusal without Boldog."""

from collections import Counter

import pytest
from sqlalchemy import func, select, text

from riso.api.bulk_seed import BulkSeedRefused, seed_bulk
from riso.api.seed import seeded_already
from riso.cli import main
from riso.platform import Database
from riso.platform import Settings as PlatformSettings
from tests.conftest import copy_seeded


@pytest.fixture
def settings(seed_template, tmp_path):
    copy_seeded(seed_template, tmp_path / "var")
    return PlatformSettings(var_dir=tmp_path / "var", env="test")


def _rows(settings, sql: str) -> list[tuple]:
    db = Database(settings.db_url)
    try:
        with db.connect() as connection:
            return [tuple(row) for row in connection.execute(text(sql))]
    finally:
        db.dispose()


def test_bulk_invoices_span_the_lifecycle_and_hold_their_numbers(settings):
    precedents = _rows(settings, "SELECT count(*) FROM precedents")
    before = _rows(settings, "SELECT count(*) FROM invoices")[0][0]

    done = seed_bulk(settings, 400, seed=7)

    assert done.invoices == 400
    states = Counter(dict(_rows(settings, "SELECT state, count(*) FROM invoices GROUP BY state")))
    assert sum(states.values()) == before + 400
    assert {"paid", "exported", "booked"} <= set(done.by_state)
    assert done.by_state["paid"] > done.by_state["booked"]
    # Every booked, exported or paid invoice holds its number once, in its series and year.
    held = _rows(
        settings,
        "SELECT n.series, n.year, u.sequence, i.document_number, i.supply_date "
        "FROM used_numbers u JOIN number_series n ON n.id = u.series_id "
        "JOIN invoices i ON i.id = u.invoice_id ORDER BY n.series, n.year, u.sequence",
    )
    booked = sum(done.by_state.get(s, 0) for s in ("booked", "exported", "paid"))
    assert len(held) == booked
    assert len({(series, year, seq) for series, year, seq, _, _ in held}) == booked
    for series, year, _, number, _ in held:
        assert number.startswith(f"{series}/") and number.endswith(f"/{year % 100}")
    # Within a series and year the numbers follow the dates of supply.
    by_series: dict[tuple[str, int], list[str]] = {}
    for series, year, _, _, supplied in held:
        by_series.setdefault((series, year), []).append(supplied)
    for supplied in by_series.values():
        assert supplied == sorted(supplied)
    assert {year for _, year in by_series} == {2024, 2025, 2026}
    # The demo's proposals do not change: the supplier memory is left alone.
    assert _rows(settings, "SELECT count(*) FROM precedents") == precedents


def test_the_same_count_and_seed_give_the_same_invoices(seed_template, tmp_path):
    numbers = []
    for name in ("a", "b"):
        copy_seeded(seed_template, tmp_path / name)
        settings = PlatformSettings(var_dir=tmp_path / name, env="test")
        seed_bulk(settings, 60, seed=11)
        numbers.append(
            _rows(
                settings,
                "SELECT invoice_number, state, document_number, gross_cents FROM invoices "
                "WHERE invoice_number LIKE 'B%' ORDER BY invoice_number",
            )
        )
    assert numbers[0] == numbers[1] and len(numbers[0]) == 60


def test_without_boldog_it_is_refused(tmp_path):
    settings = PlatformSettings(var_dir=tmp_path / "var", env="test")
    assert not seeded_already(settings)
    from riso.platform.migrations import upgrade

    upgrade(settings.db_url)
    with pytest.raises(BulkSeedRefused):
        seed_bulk(settings, 5)


def test_the_cli_adds_to_a_seeded_database(settings, monkeypatch, capsys):
    monkeypatch.setenv("RISO_VAR_DIR", str(settings.var_dir))
    monkeypatch.setenv("RISO_ENV", "test")
    assert seeded_already(settings)
    assert main(["seed", "--bulk", "25"]) == 0
    assert "added 25 synthetic invoices to Obec Boldog" in capsys.readouterr().out
    db = Database(settings.db_url)
    try:
        with db.session() as session:
            from riso.invoicing.infrastructure.orm import InvoiceRow

            count = session.scalar(
                select(func.count()).select_from(InvoiceRow).where(InvoiceRow.channel == "manual")
            )
    finally:
        db.dispose()
    assert count == 25
    assert main(["seed", "--bulk", "0"]) == 2
