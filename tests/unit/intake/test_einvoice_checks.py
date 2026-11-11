"""The e-invoice business checks (plan §8.4, decision 65) and the unit table: a failed check
or a missing optional field is a warning, and only a missing supplier or total fails."""

import datetime as dt
from decimal import Decimal

import pytest

from riso.contracts import InvoiceDocument
from riso.intake.domain.einvoice import check, require_essentials
from riso.intake.domain.layout import ReadingFailed
from riso.intake.domain.units import code_of, unit_of
from riso.testdata.scans import dataset_cases

ZSE = next(c for c in dataset_cases() if c.id == "seed-01-zse-electricity-ocu").invoice
BOLDOG = "00305863"


def changed(document: InvoiceDocument, **parts: dict[str, object]) -> InvoiceDocument:
    return document.model_copy(
        update={
            name: getattr(document, name).model_copy(update=values)
            for name, values in parts.items()
        }
    )


def test_a_good_invoice_has_no_warnings():
    assert check(ZSE, customer_ico=BOLDOG) == ()


@pytest.mark.parametrize(
    ("parts", "warning"),
    [
        ({"supplier": {"ico": "35823552"}}, "supplier_ico_check_digit"),
        ({"supplier": {"ico": None}}, "missing_supplier_ico"),
        ({"supplier": {"iban": "SK81 1100 0000 0026 2410 5532"}}, "iban_check_digits"),
        ({"supplier": {"iban": None}}, "missing_iban"),
        ({"supplier": {"dic": "2020285513"}}, "tax_ids_do_not_match"),
        ({"invoice": {"variable_symbol": None}}, "missing_variable_symbol"),
        ({"invoice": {"due_date": None}}, "missing_due_date"),
        ({"invoice": {"due_date": dt.date(2026, 1, 1)}}, "dates_out_of_order"),
        ({"invoice": {"delivery_date": dt.date(2026, 3, 1)}}, "dates_out_of_order"),
        ({"totals": {"vat": Decimal("60.40")}}, "totals_do_not_add_up"),
        (
            {
                "totals": {
                    "net": Decimal("262.33"),
                    "vat": Decimal("60.34"),
                    "gross": Decimal("322.67"),
                }
            },
            None,
        ),
        ({"customer": {"ico": "00305871"}}, "addressed_to_another_entity"),
    ],
)
def test_each_check_gives_its_warning(parts, warning):
    warnings = check(changed(ZSE, **parts), customer_ico=BOLDOG)
    assert warnings == ((warning,) if warning else ())


def test_lines_that_do_not_add_up_to_the_net_are_flagged():
    lines = [ZSE.lines[0].model_copy(update={"net": Decimal("100")}), *ZSE.lines[1:]]
    assert check(ZSE.model_copy(update={"lines": lines}), customer_ico=BOLDOG) == (
        "lines_do_not_add_up",
    )


def test_a_short_ico_is_checked_padded():
    """An IČO written without its leading zeros is checked as eight digits."""
    document = changed(ZSE, supplier={"ico": "305863"}, customer={"ico": "305863"})
    assert check(document, customer_ico=BOLDOG) == ()


def test_schema_errors_are_a_warning_and_not_a_failure():
    assert check(ZSE, customer_ico=BOLDOG, schema_errors=["line 3: …"]) == ("einvoice_schema",)


def test_without_a_supplier_or_a_total_the_reading_fails():
    with pytest.raises(ReadingFailed) as failed:
        require_essentials(changed(ZSE, supplier={"name": None, "ico": None}))
    assert failed.value.reason == "einvoice_no_supplier"
    with pytest.raises(ReadingFailed) as failed:
        require_essentials(changed(ZSE, totals={"gross": None}))
    assert failed.value.reason == "einvoice_no_total"
    require_essentials(changed(ZSE, supplier={"name": None}))  # the IČO is enough


@pytest.mark.parametrize(
    ("unit", "code", "back"),
    [("kWh", "KWH", "kWh"), ("ks", "C62", "ks"), ("mes.", "MON", "mes."), ("výsyp", "C62", "ks")],
)
def test_units_go_through_their_codes(unit, code, back):
    assert code_of(unit) == code
    assert unit_of(code) == back


def test_a_code_missing_from_the_table_is_kept():
    assert unit_of(" XYZ ") == "XYZ"
    assert unit_of("H87") == "ks"
