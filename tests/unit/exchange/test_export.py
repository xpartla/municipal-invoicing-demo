"""Export files (P2-M4-T06, plan §7.4): the exact CSV bytes of a split invoice, the same values
in XLSX, the formula guard, and the `ExportRun`."""

import csv
import io
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from riso.contracts import Coding
from riso.exchange.application.exports import rows
from riso.exchange.domain.export import (
    COLUMNS,
    ExportFile,
    ExportFormat,
    ExportRequested,
    ExportRun,
    ExportState,
    guard,
)
from riso.exchange.infrastructure.writers import TableWriter, csv_bytes, xlsx_bytes
from riso.invoicing import ExportableInvoice
from riso.shared import InvalidState

T0 = datetime(2026, 7, 1, 8, tzinfo=UTC)


def _line(md: str, amount: str, text: str, unit: str, budget_text: str) -> tuple[dict, dict]:
    return (
        {"md": md, "dal": "321 000", "amount": amount, "text": text},
        {
            "key": f"632001 41 {unit} 000",
            "ek": "632001",
            "zdroj": "41",
            "oddiel": unit.split()[0],
            "trieda": unit.split()[1],
            "analytika": "000",
            "amount": amount,
            "text": budget_text,
        },
    )


def invoice(
    *, supplier: str = "ZSE Energia, a.s.", gross: str = "150.505", text: str = "elektrina OcÚ"
) -> ExportableInvoice:
    first = _line("502 001", "100.25", text, "01 110", "energie OcÚ")
    second = _line("502 002", "50.26", "elektrina KD", "08 200", "energie KD")
    coding = Coding.model_validate(
        {
            "document": {"series": "FD", "number": "FD/250/26", "booking_date": "2026-06-23"},
            "posting": [first[0], second[0]],
            "budget": [first[1], second[1]],
        }
    )
    return ExportableInvoice(
        id="inv-1",
        state="booked",
        exported_before=False,
        series="FD",
        number="FD/250/26",
        booking_date=date(2026, 6, 23),
        supplier_name=supplier,
        supplier_ico="36677281",
        invoice_number="2026-0042",
        variable_symbol="20260042",
        issue_date=date(2026, 6, 20),
        supply_date=date(2026, 6, 15),
        due_date=date(2026, 7, 5),
        gross=Decimal(gross),
        coding=coding,
    )


EXPECTED_CSV = (
    "﻿"
    "Rad;Číslo dokladu;Dátum zaúčtovania;Dodávateľ;IČO;Číslo faktúry;VS;Dátum vystavenia;"
    "Dátum dodania;Dátum splatnosti;Suma faktúry;MD;DAL;Suma;Text zaúčtovania;"
    "Rozpočtová položka;EK;Zdroj;Oddiel;Trieda;Analytika;Transfer;Text rozpočtu\r\n"
    "FD;FD/250/26;23.06.2026;ZSE Energia, a.s.;36677281;2026-0042;20260042;20.06.2026;"
    "15.06.2026;05.07.2026;150,51;502 001;321 000;100,25;elektrina OcÚ;"
    "632001 41 01 110 000;632001;41;01;110;000;;energie OcÚ\r\n"
    "FD;FD/250/26;23.06.2026;ZSE Energia, a.s.;36677281;2026-0042;20260042;20.06.2026;"
    "15.06.2026;05.07.2026;150,51;502 002;321 000;50,26;elektrina KD;"
    "632001 41 08 200 000;632001;41;08;200;000;;energie KD\r\n"
).encode()


def test_the_csv_of_a_split_invoice_byte_for_byte():
    data = csv_bytes(COLUMNS, rows([invoice()]))
    assert data == EXPECTED_CSV
    assert data.startswith(b"\xef\xbb\xbf")  # the BOM Slovak Excel needs


def test_the_xlsx_holds_the_same_values_typed():
    book = load_workbook(io.BytesIO(xlsx_bytes(COLUMNS, rows([invoice()]))))
    sheet = book["Faktúry"]
    values = [list(r) for r in sheet.iter_rows(values_only=True)]
    assert values[0] == [c.header for c in COLUMNS]
    first = values[1]
    assert first[:3] == ["FD", "FD/250/26", datetime(2026, 6, 23)]
    assert first[10] == pytest.approx(150.51) and first[13] == pytest.approx(100.25)
    assert first[15] == "632001 41 01 110 000" and first[21] is None
    assert values[2][13] == pytest.approx(50.26) and len(values) == 3
    assert sheet["C2"].number_format == "dd.mm.yyyy" and sheet["K2"].number_format == "0.00"
    csv_rows = list(csv.reader(io.StringIO(EXPECTED_CSV.decode("utf-8-sig")), delimiter=";"))
    for got, want in zip(values[1:], csv_rows[1:], strict=True):
        texts = [i for i, c in enumerate(COLUMNS) if c.kind == "text"]
        assert [got[i] or "" for i in texts] == [want[i] for i in texts]


@pytest.mark.parametrize("text", ['=HYPERLINK("http://x")', "+421 900", "-5 %", "@SUM(A1)", "\tx"])
def test_formula_injection_is_neutralised(text):
    assert guard(text) == "'" + text
    exported = invoice(supplier=text, text=text)
    parsed = list(
        csv.reader(
            io.StringIO(csv_bytes(COLUMNS, rows([exported])).decode("utf-8-sig")), delimiter=";"
        )
    )
    assert parsed[1][3] == "'" + text and parsed[1][14] == "'" + text
    sheet = load_workbook(io.BytesIO(xlsx_bytes(COLUMNS, rows([exported]))))["Faktúry"]
    assert sheet["D2"].value == "'" + text and sheet["D2"].data_type == "s"


def test_negative_amounts_stay_numbers():
    credit = invoice(gross="-12.5")
    assert (
        csv_bytes(COLUMNS, rows([credit])).decode("utf-8-sig").split("\r\n")[1].split(";")[10]
        == "-12,50"
    )
    sheet = load_workbook(io.BytesIO(xlsx_bytes(COLUMNS, rows([credit]))))["Faktúry"]
    assert sheet["K2"].value == pytest.approx(-12.5)
    assert guard("plain text") == "plain text"


def test_the_writer_picks_the_format():
    writer = TableWriter()
    assert writer.write(ExportFormat.CSV, COLUMNS, rows([invoice()])) == EXPECTED_CSV
    assert writer.write(ExportFormat.XLSX, COLUMNS, rows([invoice()]))[:2] == b"PK"
    assert ExportFormat.XLSX.media_type.endswith("spreadsheetml.sheet")


def _run() -> ExportRun:
    run = ExportRun.new(
        "e1", "c1", ExportFormat.CSV, {"invoice_ids": ["i1"]}, ("i1",), at=T0, actor="u1"
    )
    run.queued_as("j1")
    return run


def test_an_export_run_waits_for_its_job():
    run = _run()
    assert run.state is ExportState.QUEUED and run.events == [ExportRequested("e1", "c1", 1)]
    assert run.awaits("j1") and not run.awaits("j0")
    with pytest.raises(InvalidState):
        run.finished(
            "j0", ExportFile("k", "s", "n.csv", 1), invoices=1, rows=1, again=0, skipped=(), at=T0
        )
    run.finished(
        "j1", ExportFile("k", "s", "n.csv", 9), invoices=1, rows=2, again=1, skipped=("i9",), at=T0
    )
    assert (run.state, run.rows, run.again, run.skipped) == (ExportState.DONE, 2, 1, ("i9",))
    assert not run.awaits("j1")
    failing = _run()
    failing.failed("j1", "nothing booked", T0)
    assert failing.state is ExportState.FAILED and failing.error == "nothing booked"
    with pytest.raises(InvalidState):
        failing.failed("j1", "again", T0)
    with pytest.raises(InvalidState, match="at least one"):
        ExportRun.new("e2", "c1", ExportFormat.CSV, {}, (), at=T0, actor=None)
