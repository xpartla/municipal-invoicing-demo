import html
from collections import Counter

import pytest

from riso.testdata import layouts, printed
from riso.testdata.scans import dataset_cases
from riso.testdata.truth import LAYOUT_NAMES

SEED = 2026


@pytest.fixture(scope="module")
def cases():
    return {case.id: case for case in dataset_cases()}


def _page(case, layout, seed=SEED):
    style = layouts.style_for(layouts.supplier_key(case.invoice), layout, seed)
    extras = layouts.extras_for(case.invoice, layout, seed)
    text = html.unescape(layouts.page_html(case.invoice, style, extras, "https://fonts.test"))
    return text, style


def test_the_scan_set_is_the_seventy_seed_and_held_out_cases(cases):
    assert len(cases) == 70
    assert {case.split for case in cases.values()} == {"seed", "heldout"}


def test_suppliers_spread_evenly_over_the_layouts_and_the_seed_reshuffles_them(cases):
    keys = [layouts.supplier_key(case.invoice) for case in cases.values()]
    assigned = layouts.assign_layouts(keys, SEED)
    counts = Counter(assigned.values())

    assert set(counts) == set(LAYOUT_NAMES)
    assert max(counts.values()) - min(counts.values()) <= 1
    assert layouts.assign_layouts(reversed(keys), SEED) == assigned
    assert layouts.assign_layouts(keys, SEED + 1) != assigned


@pytest.mark.parametrize("layout", LAYOUT_NAMES)
def test_every_layout_prints_the_fields_the_case_holds(cases, layout):
    case = cases["seed-01-zse-electricity-ocu"]
    doc = case.invoice
    text, style = _page(case, layout)

    assert doc.supplier.name in text
    assert printed.ico(doc.supplier.ico, spaced=style.spaced_ico) in text
    assert doc.supplier.dic in text and doc.supplier.ic_dph in text
    assert printed.iban(doc.supplier.iban, grouped=style.grouped_iban) in text
    assert doc.invoice.variable_symbol in text and doc.invoice.number in text
    assert printed.money(doc.totals.gross, style.currency) in text
    for value in (doc.invoice.issue_date, doc.invoice.delivery_date, doc.invoice.due_date):
        assert printed.date(value, style.date_style) in text
    assert "00305863" in text and "Obec Boldog" in text
    for line in doc.lines:
        assert line.description in text


@pytest.mark.parametrize("layout", LAYOUT_NAMES)
def test_a_field_the_case_lacks_is_not_printed(cases, layout):
    missing_ico = cases["heldout-17-slovnaft-noise"]
    sole_trader = cases["heldout-04-vzorova-accounting"]

    text, _ = _page(missing_ico, layout)
    assert missing_ico.invoice.supplier.ico is None
    assert text.count("IČO") == 1  # the customer's

    text, _ = _page(sole_trader, layout)
    assert "DIČ" not in text and "IČ DPH" not in text and "IBAN SK" not in text
    assert "Nie som platca DPH" in text


def test_a_credit_note_is_titled_as_one(cases):
    text, style = _page(cases["heldout-35-metro-credit-note"], "classic")
    assert style.labels["credit_title"] in text
    assert "obropis" in text.lower() or "DOBROPIS" in text


def test_bills_list_further_accounts_with_valid_check_digits(cases):
    from riso.shared.values import iban_is_valid

    case = cases["seed-01-zse-electricity-ocu"]
    extras = layouts.extras_for(case.invoice, "bill", SEED)
    own = case.invoice.supplier.iban.replace(" ", "")

    assert 1 <= len(extras.other_accounts) <= 2
    assert all(iban_is_valid(iban) and iban != own for iban in extras.other_accounts)
    assert layouts.extras_for(case.invoice, "grid", SEED).other_accounts == ()


def test_values_are_escaped(cases):
    case = cases["seed-01-zse-electricity-ocu"]
    supplier = case.invoice.supplier.model_copy(update={"name": "<b>Zlá & firma</b>"})
    doc = case.invoice.model_copy(update={"supplier": supplier})
    style = layouts.style_for("x", "modern", SEED)
    page = layouts.page_html(doc, style, layouts.extras_for(doc, "modern", SEED), "https://f.test")

    assert "<b>Zlá" not in page and "&lt;b&gt;Zlá &amp; firma&lt;/b&gt;" in page


def test_riso_testdata_scans_refuses_unknown_cases_and_mixed_options(tmp_path, capsys):
    from riso.cli import main

    assert main(["testdata", "scans", "--out", str(tmp_path), "--case", "seed-99-none"]) == 1
    assert "no seed or held-out case seed-99-none" in capsys.readouterr().err
    assert main(["testdata", "scans", "--samples", "--case", "seed-01-zse-electricity-ocu"]) == 2
    assert not any(tmp_path.iterdir())
