"""Domov's statistics (P2-M7-T01, plan §10.2, decision 67) on hand-built invoice facts: the
Bratislava month and day around midnight UTC/CET and CEST, every tile, chart and table, and
the budget drawdown."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from riso.codelists import BudgetAmountView
from riso.invoicing import InvoiceFact, LineFact
from riso.reporting.application import Month, budget_drawdown, month_statistics

NOV = Month(2026, 11)
NAMES = {
    "01 110": ("01.1.1", "Výkonné a zákonodarné orgány"),
    "09 111": ("09.1.1.1", "Predprimárne vzdelávanie s bežnou starostlivosťou"),
}


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC)


_counter = iter(range(1, 10_000))
EARLY_NOVEMBER = datetime(2026, 11, 2, 9, tzinfo=UTC)


def fact(
    state: str = "booked",
    *,
    uploaded: datetime = EARLY_NOVEMBER,
    booked: datetime | None = None,
    gross: str | None = "100.00",
    series: str | None = "FD",
    credit_note: bool = False,
    ico: str | None = "35763469",
    name: str | None = "Slovak Telekom, a.s.",
    review: bool = False,
    lines: tuple[tuple[str, str, str], ...] = (),
) -> InvoiceFact:
    return InvoiceFact(
        id=f"inv-{next(_counter):04d}",
        state=state,
        series=series,
        credit_note=credit_note,
        gross=None if gross is None else Decimal(gross),
        supplier_ico=ico,
        supplier_name=name,
        needs_review=review,
        uploaded_at=uploaded,
        booked_at=booked,
        lines=tuple(LineFact(o, t, Decimal(a)) for o, t, a in lines),
    )


# --- the month -------------------------------------------------------------------------------


def test_a_month_starts_at_bratislava_midnight_in_winter_and_summer():
    assert NOV.start == utc(2026, 10, 31, 23)  # CET, UTC+1 (summer time ended on 25 October)
    assert NOV.end == utc(2026, 11, 30, 23)
    july = Month(2026, 7)
    assert july.start == utc(2026, 6, 30, 22)  # CEST, UTC+2
    assert Month(2026, 3).end == utc(2026, 3, 31, 22)  # summer time began on 29 March


def test_a_month_holds_its_instants_up_to_but_not_including_the_next_midnight():
    assert not NOV.holds(utc(2026, 10, 31, 22, 59, 59))
    assert NOV.holds(utc(2026, 10, 31, 23))
    assert NOV.holds(utc(2026, 11, 30, 22, 59, 59))
    assert not NOV.holds(utc(2026, 11, 30, 23))


@pytest.mark.parametrize(
    ("text", "month"),
    [("2026-11", Month(2026, 11)), ("2027-01", Month(2027, 1)), ("2000-12", Month(2000, 12))],
)
def test_months_parse_from_their_iso_form(text, month):
    assert Month.parse(text) == month and str(month) == text


@pytest.mark.parametrize("text", ["2026-13", "2026-00", "26-11", "2026-1", "2026/11", "abcd-ef"])
def test_malformed_months_are_refused(text):
    with pytest.raises(ValueError):
        Month.parse(text)


def test_months_shift_across_years():
    assert NOV.shifted(2) == Month(2027, 1)
    assert NOV.shifted(-11) == Month(2025, 12)
    assert Month(2026, 1).shifted(-1) == Month(2025, 12)
    assert NOV.days()[0] == date(2026, 11, 1) and len(NOV.days()) == 30
    assert len(Month(2028, 2).days()) == 29


# --- the tiles -------------------------------------------------------------------------------


def test_the_state_tiles_count_the_months_uploads_by_their_state_now():
    uploaded = [
        fact("extracted", uploaded=utc(2026, 10, 31, 23, 30)),  # 1 November, 00:30
        fact("extracted", uploaded=utc(2026, 11, 15, 10)),
        fact("needs_review", uploaded=utc(2026, 11, 15, 11)),
        fact("extraction_failed", uploaded=utc(2026, 11, 30, 22, 59)),  # 30 November, 23:59
        fact("ready", uploaded=utc(2026, 11, 3)),
        fact("discarded", uploaded=utc(2026, 11, 4)),
        fact("duplicate", uploaded=utc(2026, 11, 4)),
        fact("booked", uploaded=utc(2026, 11, 5), booked=utc(2026, 11, 6)),
        # Outside the month in Bratislava, inside it in UTC, and the other way round:
        fact("extracted", uploaded=utc(2026, 11, 30, 23, 0)),  # 1 December, 00:00
        fact("needs_review", uploaded=utc(2026, 10, 31, 22, 30)),  # 31 October, 23:30
    ]
    tiles = month_statistics(NOV, uploaded, [], NAMES).tiles
    assert (tiles.uploaded, tiles.waiting, tiles.review, tiles.failed) == (8, 2, 1, 1)
    assert (tiles.booked, tiles.booked_total) == (0, Decimal("0.00"))


def test_booked_tiles_count_bookings_made_in_the_month_whenever_uploaded():
    booked = [
        fact(uploaded=utc(2026, 9, 1), booked=utc(2026, 11, 2, 8), gross="120.50"),
        fact("exported", booked=utc(2026, 10, 31, 23, 15), gross="10.00"),  # 1 Nov, 00:15
        fact("paid", booked=utc(2026, 11, 20), gross="5.25"),
        fact(booked=utc(2026, 11, 21), gross="-30.00", credit_note=True),
        fact(booked=utc(2026, 11, 22), gross=None),  # no total read: counted, adds nothing
        fact(booked=utc(2026, 10, 31, 22, 45), gross="999.00"),  # 31 October, 23:45
        fact(booked=utc(2026, 11, 30, 23, 5), gross="999.00"),  # 1 December
    ]
    tiles = month_statistics(NOV, [], booked, NAMES).tiles
    assert tiles.uploaded == 0
    assert (tiles.booked, tiles.booked_total) == (5, Decimal("105.75"))


# --- per day, type, suppliers, units ---------------------------------------------------------


def test_bookings_per_day_fill_every_day_of_the_month_by_the_bratislava_day():
    booked = [
        fact(booked=utc(2026, 11, 5, 22, 59), gross="1.00"),  # 5 November, 23:59
        fact(booked=utc(2026, 11, 5, 23, 0), gross="2.00"),  # 6 November, 00:00
        fact(booked=utc(2026, 11, 6, 12), gross="3.00"),
        fact(booked=utc(2026, 10, 31, 23), gross="4.00"),  # 1 November, 00:00
    ]
    days = {d.day: (d.count, d.total) for d in month_statistics(NOV, [], booked, NAMES).per_day}
    assert list(days) == NOV.days()
    assert days[date(2026, 11, 1)] == (1, Decimal("4.00"))
    assert days[date(2026, 11, 5)] == (1, Decimal("1.00"))
    assert days[date(2026, 11, 6)] == (2, Decimal("5.00"))
    assert days[date(2026, 11, 2)] == (0, Decimal("0.00"))


def test_bookings_by_type_split_series_and_credit_notes():
    booked = [
        fact(booked=utc(2026, 11, 2), series="FD", gross="10.00"),
        fact(booked=utc(2026, 11, 3), series="FD", gross="20.00"),
        fact(booked=utc(2026, 11, 3), series="FD", gross="-5.00", credit_note=True),
        fact(booked=utc(2026, 11, 4), series="FDŠJ", gross="7.00"),
    ]
    by_type = month_statistics(NOV, [], booked, NAMES).by_type
    assert [(t.series, t.credit_note, t.count, t.total) for t in by_type] == [
        ("FD", False, 2, Decimal("30.00")),
        ("FD", True, 1, Decimal("-5.00")),
        ("FDŠJ", False, 1, Decimal("7.00")),
    ]


def test_top_suppliers_by_count_and_by_amount_keep_ten_each():
    booked = [
        fact(booked=utc(2026, 11, 2), ico="35763469", name="Slovak Telekom, a.s.", gross="10.00"),
        fact(booked=utc(2026, 11, 3), ico="35763469", name="Slovak Telekom, a.s.", gross="12.00"),
        fact(booked=utc(2026, 11, 3), ico="36361518", name="ZSE Energia, a.s.", gross="300.00"),
        fact(booked=utc(2026, 11, 4), ico=None, name="Ján Vzorový", gross="50.00"),
        fact(booked=utc(2026, 11, 4), ico=None, name="Ján Vzorový", gross="-50.00"),
    ] + [
        fact(booked=utc(2026, 11, 5), ico=f"999000{n:02d}", name=f"Dodávateľ {n:02d}", gross="1")
        for n in range(10)
    ]
    stats = month_statistics(NOV, [], booked, NAMES)
    by_count = [(s.ico, s.name, s.count, s.total) for s in stats.suppliers_by_count]
    assert len(by_count) == 10
    assert by_count[:3] == [
        ("35763469", "Slovak Telekom, a.s.", 2, Decimal("22.00")),
        (None, "Ján Vzorový", 2, Decimal("0.00")),
        ("36361518", "ZSE Energia, a.s.", 1, Decimal("300.00")),
    ]
    by_amount = [(s.name, s.total) for s in stats.suppliers_by_amount]
    assert by_amount[:2] == [("ZSE Energia, a.s.", Decimal("300.00")), ("Slovak Telekom, a.s.", 22)]
    assert ("Ján Vzorový", Decimal("0.00")) not in by_amount  # eleventh by amount


def test_units_sum_the_booked_lines_by_function_with_the_cofog_name():
    booked = [
        fact(
            booked=utc(2026, 11, 2),
            lines=(("01", "110", "60.00"), ("09", "111", "40.00")),
        ),
        fact(booked=utc(2026, 11, 3), lines=(("09", "111", "25.50"),)),
        fact(booked=utc(2026, 11, 3), lines=(("08", "209", "5.00"),)),  # not in the list
        fact(booked=utc(2026, 10, 3), lines=(("01", "110", "999.00"),)),  # October
    ]
    units = month_statistics(NOV, [], booked, NAMES).units
    assert [(u.function, u.code, u.name, u.invoices, u.total) for u in units] == [
        ("09 111", "09.1.1.1", NAMES["09 111"][1], 2, Decimal("65.50")),
        ("01 110", "01.1.1", NAMES["01 110"][1], 1, Decimal("60.00")),
        ("08 209", None, None, 1, Decimal("5.00")),
    ]


# --- twelve months, review -------------------------------------------------------------------


def test_twelve_months_end_with_the_chosen_one():
    booked = [
        fact(booked=utc(2025, 11, 30, 22, 59), gross="1.00"),  # 30 November 2025: too early
        fact(booked=utc(2025, 11, 30, 23, 0), gross="2.00"),  # 1 December 2025
        fact(booked=utc(2026, 6, 30, 22, 30), gross="3.00"),  # 1 July 2026, CEST
        fact(booked=utc(2026, 6, 30, 21, 30), gross="4.00"),  # 30 June 2026
        fact(booked=utc(2026, 11, 3), gross="5.00"),
    ]
    months = month_statistics(NOV, [], booked, NAMES).months
    assert [m.month for m in months] == [str(NOV.shifted(-n)) for n in range(11, -1, -1)]
    totals = {m.month: (m.count, m.total) for m in months}
    assert totals["2025-12"] == (1, Decimal("2.00"))
    assert totals["2026-06"] == (1, Decimal("4.00"))
    assert totals["2026-07"] == (1, Decimal("3.00"))
    assert totals["2026-11"] == (1, Decimal("5.00"))
    assert sum(c for c, _ in totals.values()) == 4


def test_review_rate_and_median_time_from_upload_to_booking():
    start = utc(2026, 11, 2, 8)
    booked = [
        fact(uploaded=start, booked=start + timedelta(hours=1), review=True),
        fact(uploaded=start, booked=start + timedelta(hours=3)),
        fact(uploaded=start, booked=start + timedelta(hours=4), review=True),
        fact(uploaded=start, booked=start + timedelta(days=2)),
        fact(uploaded=start - timedelta(days=60), booked=utc(2026, 10, 1), review=True),  # Oct
    ]
    review = month_statistics(NOV, [], booked, NAMES).review
    assert (review.booked, review.reviewed, review.rate) == (4, 2, 0.5)
    assert review.median_seconds == 3.5 * 3600


def test_an_empty_month_has_no_rate_and_no_median():
    stats = month_statistics(NOV, [], [], NAMES)
    assert (stats.review.rate, stats.review.median_seconds) == (None, None)
    assert stats.by_type == stats.units == stats.suppliers_by_count == []
    assert len(stats.per_day) == 30 and len(stats.months) == 12


# --- the budget ------------------------------------------------------------------------------


def position(key: str, approved: str | None, adjusted: str | None = None) -> BudgetAmountView:
    return BudgetAmountView(
        key,
        f"pozícia {key}",
        None if approved is None else Decimal(approved),
        None if adjusted is None else Decimal(adjusted),
    )


def test_the_drawdown_compares_the_booked_lines_with_the_adjusted_or_approved_amount():
    positions = [
        position("632001 41 01 110 001", "1000.00", "1200.00"),
        position("633006 41 01 110 000", "500.00"),
        position("637004 41 01 110 000", None),
    ]
    drawn = {
        "632001 41 01 110 001": Decimal("300.00"),
        "637004 41 01 110 000": Decimal("40.00"),
        "642006 41 01 110 000": Decimal("2.00"),
    }
    budget = budget_drawdown(2026, positions, drawn)
    assert budget is not None
    assert [(r.key, r.budgeted, r.drawn, r.share) for r in budget.rows] == [
        ("632001 41 01 110 001", Decimal("1200.00"), Decimal("300.00"), 0.25),
        ("633006 41 01 110 000", Decimal("500.00"), Decimal("0.00"), 0.0),
    ]
    assert (budget.budgeted, budget.drawn, budget.elsewhere) == (
        Decimal("1700.00"),
        Decimal("300.00"),
        Decimal("42.00"),
    )


def test_there_is_no_drawdown_when_the_budget_has_no_amounts():
    positions = [position("632001 41 01 110 001", None)]
    assert budget_drawdown(2026, positions, {"632001 41 01 110 001": Decimal("1")}) is None
    assert budget_drawdown(2026, [], {}) is None


def test_a_zero_budget_has_no_share():
    budget = budget_drawdown(2026, [position("632001 41 01 110 001", "0.00")], {})
    assert budget is not None and budget.rows[0].share is None
