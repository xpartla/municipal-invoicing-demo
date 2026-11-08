"""`riso export-openapi`: the document the frontend client is generated from."""

import json

from riso.cli import main


def test_the_openapi_document_is_written_and_checked(tmp_path, capsys):
    out = tmp_path / "frontend" / "openapi.json"
    assert main(["export-openapi", "--out", str(out)]) == 0
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["info"]["title"] == "riso"
    operations = {op["operationId"] for path in document["paths"].values() for op in path.values()}
    assert "legacy.code" in operations  # operation IDs are the route names
    assert main(["export-openapi", "--out", str(out), "--check"]) == 0

    out.write_text(out.read_text(encoding="utf-8").replace("riso", "stale", 1), encoding="utf-8")
    capsys.readouterr()
    assert main(["export-openapi", "--out", str(out), "--check"]) == 1
    assert "stale" in capsys.readouterr().out


def test_a_missing_document_is_stale(tmp_path):
    assert main(["export-openapi", "--out", str(tmp_path / "nothing.json"), "--check"]) == 1
