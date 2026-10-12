import json

from riso import paths
from riso.cli import main


def test_riso_code_reproduces_the_anchors(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("RISO_VAR_DIR", str(tmp_path))
    files = sorted(str(p) for p in (paths.INVOICES_DIR / "anchor").glob("*.json"))

    assert main(["code", *files]) == 0

    out = capsys.readouterr().out
    assert out.count("expected: matches") == 4
    assert "MD 518 003  DAL 321 000  632005 41 01 110 000  93.71" in out


def test_riso_code_prints_the_full_proposal_as_json(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("RISO_VAR_DIR", str(tmp_path))

    assert main(["code", "--json", str(paths.INVOICES_DIR / "anchor" / "anchor-dpo.json")]) == 0

    assert json.loads(capsys.readouterr().out)["budget"][0]["key"] == "637004 41 01 110 006"


def test_riso_check_passes(capsys):
    assert main(["check"]) == 0
    assert "FAIL" not in capsys.readouterr().out
