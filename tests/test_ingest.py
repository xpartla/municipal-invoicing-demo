import shutil

import openpyxl
import pytest

from riso import paths
from riso.ingest import EXPORT_FILES, IngestError, build_bundle


def test_the_four_exports_load(raw_dir):
    bundle = build_bundle(raw_dir)

    assert bundle.bundle_id == "00305863/2026-08"
    assert bundle.entity.name == "Obec Boldog"
    assert len(bundle.accounts) == 435
    assert len(bundle.budget_positions_expense) == 456  # 458 rows, one key three times
    assert len(bundle.budget_positions_income) == 122
    assert len(bundle.document_series) == 13
    assert len(bundle.transfers) == 47
    assert bundle.cost_centres == []
    assert [s.data_rows for s in bundle.sources] == [435, 458, 122, 13]


def test_rows_sharing_a_key_are_merged(raw_dir):
    bundle = build_bundle(raw_dir)

    position = next(p for p in bundle.budget_positions_expense if p.key == "637004 41 04 510 001")
    assert position.rows == [276, 277, 278]
    assert position.description == "popl. za uloženie odpadu"
    assert position.aliases == ["odvoz odpadu"]
    duplicates = [w for w in bundle.warnings if w.code == "duplicate_key"]
    assert [w.rows for w in duplicates] == [[276, 277, 278]]


def test_rows_without_description_are_reported(raw_dir):
    bundle = build_bundle(raw_dir)

    missing = {w.source: len(w.rows) for w in bundle.warnings if w.code == "missing_description"}
    assert missing == {"Vykaz_vydaj.xlsx": 14, "Vykaz_prijem.xlsx": 6}


def test_mock_transfers_come_from_the_grant_rows(raw_dir):
    bundle = build_bundle(raw_dir)

    transfer = next(t for t in bundle.transfers if t.id == "312001 11H 012")
    assert transfer.name == "Rekonštrukcia strechy na MŠ BSK"
    assert all(t.mock and t.zdroj != "41" for t in bundle.transfers)


def test_the_committed_bundle_is_current(raw_dir):
    bundle = build_bundle(raw_dir)

    committed = paths.BUNDLES_DIR / "00305863" / "2026-08.json"
    assert committed.read_text(encoding="utf-8") == bundle.model_dump_json(indent=2) + "\n", (
        "the exports changed; run `riso ingest`"
    )


def _copy_exports(raw_dir, tmp_path):
    for name in EXPORT_FILES:
        shutil.copyfile(raw_dir / name, tmp_path / name)
    return tmp_path


def test_a_missing_export_stops_the_build(raw_dir, tmp_path):
    copy = _copy_exports(raw_dir, tmp_path)
    (copy / "Vykaz_doklady.xlsx").unlink()

    with pytest.raises(IngestError, match="Vykaz_doklady.xlsx"):
        build_bundle(copy)


def test_a_changed_header_stops_the_build(raw_dir, tmp_path):
    copy = _copy_exports(raw_dir, tmp_path)
    workbook = openpyxl.load_workbook(copy / "Vykaz_vydaj.xlsx")
    workbook.worksheets[0]["A1"] = "EK"
    workbook.save(copy / "Vykaz_vydaj.xlsx")

    with pytest.raises(IngestError, match="expected the columns"):
        build_bundle(copy)


def test_an_unreadable_row_is_skipped_and_reported(raw_dir, tmp_path):
    copy = _copy_exports(raw_dir, tmp_path)
    workbook = openpyxl.load_workbook(copy / "Vykaz_vydaj.xlsx")
    workbook.worksheets[0]["A2"] = "61100X"
    workbook.save(copy / "Vykaz_vydaj.xlsx")

    bundle = build_bundle(copy)

    assert len(bundle.budget_positions_expense) == 455
    skipped = [w for w in bundle.warnings if w.code == "skipped_row"]
    assert [(w.source, w.rows) for w in skipped] == [("Vykaz_vydaj.xlsx", [2])]
