"""The field extractor on layouts written by hand (P2-M5-T05): every label variant the
synthetic layouts print (plan §8.2), and every validation (plan §8.2 step 5)."""

import datetime as dt
from decimal import Decimal

import pytest

from riso.intake.domain.extract import DOUBTFUL, Context, FieldExtractor
from riso.intake.domain.layout import Box, DocumentLayout, PageLayout, Word
from riso.testdata.layouts import LABELS

BOLDOG = Context(customer_ico="00305863", customer_name="Obec Boldog")
CHAR, HEIGHT = 18, 30


def layout(*rows: str | tuple[str, ...], confidence: float = 0.95) -> DocumentLayout:
    """A page of lines; a tuple is one row of cells side by side (each its own line)."""
    words, line = [], 0
    for r, row in enumerate(rows):
        cells = row if isinstance(row, tuple) else (row,)
        for c, cell in enumerate(cells):
            x = 150 + c * 1100
            for text in cell.split():
                box = Box(x, 200 + r * 60, x + CHAR * len(text), 200 + r * 60 + HEIGHT)
                words.append(Word(text, box, confidence, c, line))
                x = box.x1 + CHAR
            line += 1
    page = PageLayout(0, 2480, 3508, 300, tuple(words))
    return DocumentLayout((page,), "test", "1")


def extract(*rows, context=BOLDOG, confidence=0.95):
    return FieldExtractor().extract(
        layout(*rows, confidence=confidence), document_id="inv-1", context=context
    )


def _colon(label: str) -> str:
    return f"{label}:"


@pytest.mark.parametrize("label", LABELS["issue"])
def test_issue_date_labels(label):
    assert extract(f"{_colon(label)} 19.08.2026").document.invoice.issue_date == dt.date(
        2026, 8, 19
    )


@pytest.mark.parametrize("label", LABELS["delivery"])
def test_date_of_supply_labels(label):
    doc = extract(f"{_colon(label)} 31. 7. 2026").document
    assert doc.invoice.delivery_date == dt.date(2026, 7, 31)


@pytest.mark.parametrize("label", LABELS["due"])
def test_due_date_labels(label):
    assert extract(f"{label} 2.9.2026").document.invoice.due_date == dt.date(2026, 9, 2)


@pytest.mark.parametrize("label", LABELS["total"])
def test_total_labels(label):
    assert extract(f"{_colon(label)} 1 234,56 €").document.totals.gross == Decimal("1234.56")


@pytest.mark.parametrize("label", LABELS["vs"])
def test_variable_symbol_labels(label):
    assert extract(f"{_colon(label)} 7102214478").document.invoice.variable_symbol == "7102214478"


@pytest.mark.parametrize("label", LABELS["iban"])
def test_iban_labels(label):
    doc = extract(f"{_colon(label)} SK80 1100 0000 0026 2410 5532").document
    assert doc.supplier.iban == "SK8011000000002624105532"


@pytest.mark.parametrize("label", LABELS["ic_dph"])
def test_ic_dph_labels(label):
    assert extract(f"{label} SK2020285512").document.supplier.ic_dph == "SK2020285512"


@pytest.mark.parametrize("label", LABELS["title"])
def test_invoice_number_labels(label):
    assert extract(f"{label} 2026/0012").document.invoice.number == "2026/0012"


@pytest.mark.parametrize("label", LABELS["credit_title"])
def test_credit_note_titles(label):
    doc = extract(f"{label} 112/0026/029914").document
    assert doc.invoice.document_type == "credit_note"
    assert doc.invoice.number == "112/0026/029914"


@pytest.mark.parametrize("label", LABELS["supplier"])
def test_supplier_blocks(label):
    doc = extract(
        label, "Slovak Telekom, a.s.", "Bajkalská 28", "817 62 Bratislava", "IČO: 35763469"
    ).document
    assert doc.supplier.name == "Slovak Telekom, a.s."
    assert doc.supplier.ico == "35763469"


@pytest.mark.parametrize("label", LABELS["customer"])
def test_customer_blocks_hold_the_customers_ico(label):
    doc = extract(
        ("Dodávateľ", label),
        ("Firma, s.r.o.", "Obec Boldog"),
        ("Hlavná 1, 811 01 Bratislava", "925 26 Boldog"),
        ("IČO: 35763469", "IČO: 00305863"),
    ).document
    assert doc.customer.ico == "00305863" and doc.supplier.ico == "35763469"
    assert doc.supplier.name == "Firma, s.r.o." and doc.customer.name == "Obec Boldog"


def test_a_value_in_the_next_cell_or_under_its_label():
    beside = extract(("Variabilný symbol", "7102214478")).document
    under = extract("Dátum splatnosti", "02.09.2026").document
    assert beside.invoice.variable_symbol == "7102214478"
    assert under.invoice.due_date == dt.date(2026, 9, 2)


def test_not_a_vat_payer():
    assert extract("Nie som platca DPH.").document.supplier.vat_payer is False
    assert extract("IČ DPH: SK2020285512").document.supplier.vat_payer is True


# Validation ---------------------------------------------------------------------------------


def test_an_ico_failing_its_check_digit_is_doubtful():
    good = extract("IČO: 35763469")
    bad = extract("IČO: 35763468")
    assert good.document.ocr_meta.confidence["supplier.ico"] >= 0.9
    assert bad.document.supplier.ico == "35763468"
    assert bad.document.ocr_meta.confidence["supplier.ico"] < DOUBTFUL
    assert "supplier_ico_check_digit" in bad.warnings


def test_an_iban_failing_mod_97_is_doubtful_and_a_valid_one_wins():
    bad = extract("IBAN: SK81 1100 0000 0026 2410 5532")
    assert bad.document.ocr_meta.confidence["supplier.iban"] < DOUBTFUL
    both = extract("IBAN: SK81 1100 0000 0026 2410 5532", "SK80 1100 0000 0026 2410 5532")
    assert both.document.supplier.iban == "SK8011000000002624105532"


def test_an_iban_wrapped_onto_the_next_line_is_joined_when_it_passes_mod_97():
    """A narrow box wraps the IBAN after its third group (the bill layout's accounts)."""
    wrapped = extract("Bankové spojenie SK95 0900 0000", "0001 7612 4588")
    assert wrapped.document.supplier.iban == "SK9509000000000176124588"
    assert wrapped.document.ocr_meta.confidence["supplier.iban"] >= 0.9
    misread = extract("Bankové spojenie SK95 0900 0000", "0001 7612 4589")
    assert misread.document.supplier.iban != "SK9509000000000176124589"
    assert misread.document.ocr_meta.confidence.get("supplier.iban", 0.0) < DOUBTFUL


def test_net_and_vat_must_add_up_to_the_total():
    ok = extract("Na úhradu: 105,87 €", ("23 %", "86,07", "19,80", "105,87"))
    assert (ok.document.totals.net, ok.document.totals.vat) == (Decimal("86.07"), Decimal("19.80"))
    assert ok.document.ocr_meta.confidence["totals.net"] >= 0.9
    off = extract("Na úhradu: 105,87 €", "Základ DPH: 86,00 €", "DPH: 19,80 €")
    assert off.document.ocr_meta.confidence["totals.net"] < DOUBTFUL
    assert "totals_do_not_add_up" in off.warnings


def test_dates_out_of_order_are_doubtful():
    found = extract("Dátum vystavenia: 19.08.2026", "Dátum splatnosti: 02.08.2026")
    assert found.document.ocr_meta.confidence["invoice.due_date"] < DOUBTFUL
    assert "dates_out_of_order" in found.warnings


def test_an_invoice_addressed_to_another_entity_is_warned_about():
    found = extract(
        "Odberateľ", "Obec Štefanová", "IČO: 00305111", "Dodávateľ", "Firma", "IČO: 35763469"
    )
    assert found.document.customer.ico == "00305111"
    assert "addressed_to_another_entity" in found.warnings


def test_dic_agreeing_with_ic_dph_is_trusted():
    found = extract("DIČ: 2020285512", "IČ DPH: SK2020285512", confidence=0.7)
    assert found.document.ocr_meta.confidence["supplier.dic"] >= 0.9


def test_low_ocr_confidence_carries_through_unless_validated():
    found = extract("Variabilný symbol: 123456", confidence=0.5)
    assert found.document.ocr_meta.confidence["invoice.variable_symbol"] < DOUBTFUL


def test_the_handwritten_fields_are_never_filled():
    doc = extract("11.6.2026 135", "Dátum vystavenia: 10.06.2026").document
    assert doc.handwritten.date is None and doc.handwritten.number is None
