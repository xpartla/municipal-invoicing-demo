"""The handwritten note's suggestions (P2-M5-T06, plan §8.1 conclusion 2, §8.2 step 3)."""

import datetime as dt

from riso.intake.domain.note import date_suggestions, number_suggestions, read_note

TODAY = dt.date(2026, 9, 30)


def test_dates_and_numbers_are_read_from_the_digits_pass():
    assert read_note(["23.6.26", "144"]) == ([dt.date(2026, 6, 23)], ["144"])
    assert read_note(["11.6.2026 / 135"]) == ([dt.date(2026, 6, 11)], ["135"])
    assert read_note(["009", "1.7.26", "9"]) == ([dt.date(2026, 7, 1)], ["9"])
    assert read_note(["20924", "12345"]) == ([], [])  # no date, nothing of four digits or less


def test_a_number_between_the_counters_next_and_fifty_on_unused_is_plausible():
    [ok, counter] = number_suggestions(["230"], 228, used={226, 227})
    assert (ok.value, ok.source, ok.plausible) == ("230", "ocr", True)
    assert (counter.value, counter.source, counter.plausible) == ("228", "counter", True)


def test_numbers_below_the_counter_far_ahead_or_used_are_marked():
    marks = {s.value: s.reasons for s in number_suggestions(["120", "300", "226"], 228, {226})}
    assert marks == {
        "120": ("below_counter",),
        "300": ("far_ahead",),
        "226": ("below_counter", "already_used"),
        "228": (),
    }


def test_the_plausible_readings_come_first_and_the_counter_last():
    found = number_suggestions(["2733", "233"], 230, used=())
    assert [(s.value, s.plausible) for s in found] == [
        ("233", True),
        ("2733", False),
        ("230", True),
    ]
    assert number_suggestions(["230"], 230, used=())[0].source == "ocr"  # the counter agrees
    assert len(number_suggestions(["230"], 230, used=())) == 1


def test_without_a_reading_the_counter_is_the_suggestion():
    assert [s.source for s in number_suggestions([], 228, ())] == ["counter"]
    assert number_suggestions([], None, ()) == ()


def test_a_date_between_the_issue_date_and_today_in_the_budget_year_is_plausible():
    issue = dt.date(2026, 9, 10)
    [ok] = date_suggestions([dt.date(2026, 9, 14)], issue, TODAY, 2026)
    assert ok.plausible and ok.source == "ocr"
    marks = {
        s.value: s.reasons
        for s in date_suggestions(
            [dt.date(2026, 9, 1), dt.date(2026, 10, 2), dt.date(2025, 9, 14)], issue, TODAY, 2026
        )
    }
    assert marks == {
        "2026-09-01": ("before_issue",),
        "2026-10-02": ("in_future",),
        "2025-09-14": ("before_issue", "other_year"),
    }
    assert date_suggestions([], issue, TODAY, 2026) == ()
