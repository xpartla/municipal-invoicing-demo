"""Document numbers (P2-M4-T02, plan §2 decisions 61 and 62): where a booking goes, what
moves to make room, what never moves, and the counter."""

from datetime import UTC, date, datetime, timedelta

import pytest

from riso.invoicing.domain.numbering import (
    Holder,
    HolderKind,
    Newcomer,
    NumberFrozen,
    NumberSeries,
    Release,
    numberable,
    place,
)
from riso.shared import ValidationFailed

T0 = datetime(2026, 7, 1, 8, tzinfo=UTC)
B, R, X = HolderKind.BOOKED, HolderKind.RESERVED, HolderKind.EXTERNAL


def held(sequence: int, day: int | None = None, kind: HolderKind = B, *, frozen=False, hour=0):
    """A holder of `sequence` supplied on `day` of June 2026 and uploaded at `hour`."""
    return Holder(
        id=f"h{sequence}",
        sequence=sequence,
        kind=kind,
        invoice_id=None if kind is X else f"inv-{sequence}",
        supply_date=None if day is None else date(2026, 6, day),
        received_at=None if kind is X else T0 + timedelta(hours=hour),
        frozen=frozen or kind is X,
    )


def new(day: int, sequence: int | None = None, *, hour: int = 5, invoice_id: str = "inv-new"):
    return Newcomer(invoice_id, date(2026, 6, day), T0 + timedelta(hours=hour), sequence)


CASES = [
    # (what, holders, newcomer, last_used, expected sequence, holders moving up)
    ("a free handwritten number", [held(144, 10)], new(12, 145), 144, 145, []),
    ("a handwritten number below the counter", [], new(12, 120), 222, 120, []),
    (
        "taken by one supplied earlier: the next number",
        [held(144, 10), held(145, 12)],
        new(13, 145),
        145,
        146,
        [],
    ),
    (
        "taken by one supplied earlier, the next held: those after move up",
        [held(144, 10), held(145, 11), held(146, 12), held(147, 13)],
        new(14, 145),
        147,
        146,
        [146, 147],
    ),
    (
        "taken by one supplied later: it takes the number, the others move up",
        [held(144, 10), held(145, 12), held(146, 13)],
        new(11, 145),
        146,
        145,
        [145, 146],
    ),
    (
        "the same date of supply: the earlier upload keeps the number",
        [held(145, 12, hour=1)],
        new(12, 145, hour=5),
        145,
        146,
        [],
    ),
    (
        "the same date, uploaded earlier than the holder",
        [held(145, 12, hour=9)],
        new(12, 145, hour=5),
        145,
        145,
        [145],
    ),
    (
        "a gap stops the move",
        [held(144, 10), held(145, 12), held(147, 14)],
        new(11, 145),
        147,
        145,
        [145],
    ),
    (
        "without a number, by date (the user's example)",
        [held(144, 10), held(145, 12)],
        new(11),
        145,
        145,
        [145],
    ),
    (
        "without a number, the latest: the end",
        [held(144, 10), held(145, 12)],
        new(13),
        145,
        146,
        [],
    ),
    (
        "without a number, the same date: after the holder",
        [held(144, 10), held(145, 12, hour=1)],
        new(12, hour=5),
        145,
        146,
        [],
    ),
    (
        "without a number, before every dated holder",
        [held(150, None, X), held(223, 5), held(224, 6)],
        new(1),
        224,
        223,
        [223, 224],
    ),
    (
        "without a number and nothing dated: after the counter",
        [held(183, None, X)],
        new(9),
        222,
        223,
        [],
    ),
    (
        "an external holder keeps its number",
        [held(183, None, X)],
        new(1, 183),
        222,
        184,
        [],
    ),
    (
        "a frozen holder supplied earlier keeps its number",
        [held(145, 10, frozen=True)],
        new(12, 145),
        145,
        146,
        [],
    ),
    (
        "a reserved holder moves like a booked one",
        [held(145, 12, R), held(146, 13)],
        new(11, 145),
        146,
        145,
        [145, 146],
    ),
    (
        "the newcomer's own reservation is not in the way",
        [held(144, 10), held(150, 12, R)],
        new(12, 150, invoice_id="inv-150"),
        150,
        150,
        [],
    ),
]


@pytest.mark.parametrize(
    ("holders", "newcomer", "last_used", "sequence", "moving"),
    [case[1:] for case in CASES],
    ids=[case[0] for case in CASES],
)
def test_where_a_booking_goes(holders, newcomer, last_used, sequence, moving):
    got, moved = place(holders, newcomer, last_used)
    assert got == sequence
    assert [h.sequence for h in moved] == moving


@pytest.mark.parametrize(
    ("holders", "newcomer", "blocked"),
    [
        ([held(145, 10), held(146, 12, frozen=True)], new(11, 145), 146),
        ([held(145, 12, frozen=True)], new(11, 145), 145),
        ([held(145, 10), held(146, 11), held(147, None, X)], new(9, 145), 147),
        ([held(144, 10), held(145, 12, frozen=True)], new(11), 145),
    ],
    ids=["exported in the way", "exported, supplied later", "external in the way", "by date"],
)
def test_a_move_that_reaches_a_frozen_number_is_refused(holders, newcomer, blocked):
    with pytest.raises(NumberFrozen) as raised:
        place(holders, newcomer, 200)
    assert raised.value.holder.sequence == blocked


def _series(*holders: Holder, last_used: int = 0) -> NumberSeries:
    series = NumberSeries.new("s1", "c1", "FD", 2026, "FD/XXX/RR", T0, last_used=last_used)
    series.holders = list(holders)
    return series


def test_allocating_moves_the_holders_and_raises_the_counter():
    series = _series(held(144, 10), held(145, 12), held(146, 13), last_used=146)
    placement = series.allocate(new(11), "h-new", T0, requested=None)
    assert (placement.number, placement.sequence, placement.moved) == ("FD/145/26", 145, False)
    assert [(s.invoice_id, s.old, s.new) for s in placement.shifts] == [
        ("inv-145", "FD/145/26", "FD/146/26"),
        ("inv-146", "FD/146/26", "FD/147/26"),
    ]
    by_invoice = {h.invoice_id: h.sequence for h in series.holders}
    assert by_invoice == {"inv-144": 144, "inv-new": 145, "inv-145": 146, "inv-146": 147}
    assert series.last_used == 147 and series.updated_at == T0
    mine = series.holder_of("inv-new")
    assert mine is not None and (mine.id, mine.kind, mine.supply_date) == (
        "h-new",
        B,
        date(2026, 6, 11),
    )


def test_a_moved_handwritten_number_says_so():
    series = _series(held(145, 10), last_used=145)
    placement = series.allocate(new(12, 145), "h-new", T0, requested="FD/145/26")
    assert placement.number == "FD/146/26" and placement.moved


def test_a_preview_changes_nothing_and_a_frozen_one_names_the_number():
    series = _series(held(145, 10), held(146, 12, frozen=True), last_used=146)
    with pytest.raises(NumberFrozen, match="FD/146/26 is exported") as raised:
        series.preview(new(11, 145))
    assert raised.value.number == "FD/146/26"
    external = _series(held(144, 10), held(145, None, X), last_used=145)
    with pytest.raises(NumberFrozen, match="imported"):
        external.preview(new(5, 144))  # 144 would move onto the imported 145
    assert external.preview(new(12, 145)).number == "FD/146/26"
    assert series.holders == [held(145, 10), held(146, 12, frozen=True)]


def test_booking_again_takes_back_the_reservation():
    series = _series(held(144, 10), held(150, 12, R), held(151, 13), last_used=151)
    placement = series.allocate(new(12, 150, invoice_id="inv-150"), "h-again", T0)
    assert placement.number == "FD/150/26" and placement.shifts == ()
    mine = series.holder_of("inv-150")
    assert mine is not None and (mine.id, mine.kind) == ("h-again", B)
    assert len(series.holders) == 3


def test_unbooking_the_last_number_frees_it():
    series = _series(held(144, 10), held(145, 12), last_used=145)
    assert series.release("inv-145", T0) is Release.RELEASED
    assert series.last_used == 144 and series.holder_of("inv-145") is None


def test_unbooking_another_number_reserves_it():
    series = _series(held(144, 10), held(145, 12), last_used=145)
    assert series.release("inv-144", T0) is Release.RESERVED
    holder = series.holder_of("inv-144")
    assert holder is not None and holder.kind is R and series.last_used == 145
    assert series.release("inv-144", T0) is Release.NONE  # not booked any more
    assert series.release("inv-9", T0) is Release.NONE
    assert series.drop_reservation("inv-144", T0)
    assert series.holder_of("inv-144") is None and not series.drop_reservation("inv-144", T0)


def test_a_number_below_an_edited_counter_is_not_the_last():
    series = _series(held(145, 12), last_used=160)
    assert series.release("inv-145", T0) is Release.RESERVED


def test_exported_and_paid_numbers_are_frozen():
    series = _series(held(145, 10), held(146, 12), last_used=146)
    assert series.freeze("inv-146", T0) and not series.freeze("inv-146", T0)
    assert not series.freeze("inv-9", T0)
    with pytest.raises(NumberFrozen):
        series.preview(new(11, 145))


def test_external_numbers_and_the_counter():
    series = _series(last_used=222)
    assert series.mark_external(183, "h183", T0)
    assert not series.mark_external(183, "h183b", T0)
    assert series.last_used == 222
    assert series.mark_external(230, "h230", T0) and series.last_used == 230
    holder = series.holder_at(183)
    assert holder is not None and holder.frozen and not holder.movable
    with pytest.raises(ValidationFailed):
        series.mark_external(0, "h0", T0)
    series.raise_counter(225, T0)
    assert series.last_used == 230
    series.raise_counter(240, T0)
    assert series.last_used == 240


def test_the_counter_cannot_go_below_a_used_number():
    series = _series(held(145, 12), last_used=150)
    with pytest.raises(ValidationFailed) as raised:
        series.set_last_used(144, T0)
    assert raised.value.errors[0].code == "below_used"
    with pytest.raises(ValidationFailed):
        series.set_last_used(-1, T0)
    assert series.set_last_used(145, T0) == 150 and series.last_used == 145


def test_numbers_of_the_series():
    series = _series(held(140), held(141), held(144), held(147))
    assert series.key == "FD/2026" and series.highest == 147
    assert series.gaps() == [142, 143, 145, 146]
    assert _series().gaps() == []
    assert series.number(7) == "FD/007/26"
    assert series.sequence_of("FD/144/26") == 144
    assert series.sequence_of("FD/144/25") is None  # another year
    assert series.sequence_of("FDŠJ/1/26") is None
    with pytest.raises(ValidationFailed):
        NumberSeries.new("s", "c", "FD", 2026, "FD/XXX/RR", T0, last_used=-1)


def test_series_numbered_per_month_are_not_number_series():
    assert numberable("FD/XXX/RR") and numberable("P1-X/001")
    assert not numberable("BU1/MM-RR/XXX")
    with pytest.raises(ValidationFailed, match="numbered per month"):
        NumberSeries.new("s", "c", "BU1", 2026, "BU1/MM-RR/XXX", T0)
