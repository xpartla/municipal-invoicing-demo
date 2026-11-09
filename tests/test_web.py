"""The demo's Alpine pages, until P2-M4-T10 removes them. The Slovak wording of the engine's
messages moved to the frontend (`tests/test_engine_messages.py`)."""

import re

import pytest
from fastapi.testclient import TestClient

from riso import paths
from riso.api import Settings, create_app

BOLDOG = "00305863"
PAGES = ["/", "/about.html", "/proposal.html", "/reference.html", "/eval.html"]


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    return TestClient(create_app(Settings(var_dir=tmp_path_factory.mktemp("var"))))


@pytest.mark.parametrize("page", PAGES)
def test_every_page_is_served_with_its_component(client, page):
    response = client.get(page)

    assert response.status_code == 200
    assert 'lang="sk"' in response.text
    assert "x-data=" in response.text
    assert "/vendor/alpine-3.17.4.min.js" in response.text


@pytest.mark.parametrize("asset", ["/app.js", "/app.css", "/favicon.svg"])
def test_the_assets_are_served(client, asset):
    assert client.get(asset).status_code == 200


def test_every_component_the_pages_use_is_defined():
    script = (paths.WEB_DIR / "app.js").read_text(encoding="utf-8")
    for page in PAGES[1:] + ["/index.html"]:
        html = (paths.WEB_DIR / page.lstrip("/")).read_text(encoding="utf-8")
        for component in re.findall(r'x-data="(\w+)\(\)"', html):
            assert f"function {component}()" in script, (page, component)
