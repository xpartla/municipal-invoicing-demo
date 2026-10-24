"""End-to-end click-through of the five pages in a headless browser: the M3 exit criterion.

It starts the app on a free port with its own empty runtime state, so it leaves var/ alone and
runs the same on a fresh clone. Playwright is not a project dependency; run it with

    uv run --with playwright python tests/e2e/clickthrough.py [screenshot dir]

after `uv run --with playwright playwright install chromium`, or point RISO_CHROME at an
installed Chromium. It exits with 1 on any failed step, console error or page wider than a
phone screen."""

import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import uvicorn
from playwright.sync_api import expect, sync_playwright

from riso.api import Settings, create_app
from riso.store import StateStore

SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else None
problems: list[str] = []


def shot(page, name):
    if SHOTS is not None:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def step(name):
    print(f"-- {name}", flush=True)


def serve() -> str:
    """The app on a free local port, with fresh runtime state; returns its base URL."""
    var_dir = Path(tempfile.mkdtemp(prefix="riso-e2e-"))
    StateStore(var_dir=var_dir).reset()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = uvicorn.Config(create_app(Settings(var_dir=var_dir)), port=port, log_level="warning")
    threading.Thread(target=uvicorn.Server(config).run, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(f"{base}/api/entities")
            return base
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("the app did not start")


BASE = serve()

with sync_playwright() as p:
    chrome = os.environ.get("RISO_CHROME")
    browser = p.chromium.launch(executable_path=chrome) if chrome else p.chromium.launch()
    context = browser.new_context(viewport={"width": 1280, "height": 900}, locale="sk-SK")
    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE)
    page = context.new_page()
    page.on(
        "console",
        lambda m: m.type in ("error", "warning") and problems.append(f"console {m.type}: {m.text}"),
    )
    page.on("pageerror", lambda e: problems.append(f"page error: {e}"))

    step("how it works shows the OCR's JSON of the Telekom invoice")
    page.goto(f"{BASE}/about.html")
    example = page.locator("pre.json").first
    expect(example).to_contain_text('"number": "144"')
    page.get_by_role("button", name="Kopírovať JSON").click()
    served = json.load(urllib.request.urlopen(f"{BASE}/api/invoices/anchor-telekom"))
    assert json.loads(page.evaluate("navigator.clipboard.readText()")) == served
    shot(page, "00-about")

    step("picker lists the dataset")
    page.goto(f"{BASE}/")
    expect(page.locator("tbody tr")).to_have_count(74)
    page.fill("input[type=search]", "telekom")
    expect(page.locator("tbody tr")).to_have_count(3)
    shot(page, "01-picker")
    page.fill("input[type=search]", "")

    step("proposal of the Telekom anchor")
    page.goto(f"{BASE}/proposal.html?id=anchor-telekom")
    expect(page.get_by_role("heading", name="Zaúčtovanie záväzku")).to_be_visible()
    expect(page.locator(".badge", has_text="Bez kontroly")).to_be_visible()
    expect(page.locator(".key").first).to_contain_text("632005")
    page.locator(".budget-line .copy").first.click()
    copied = page.evaluate("navigator.clipboard.readText()")
    assert copied == "632005 41 01 110 000", copied
    page.locator(".budget-line .copy-line").first.click()
    row = page.evaluate("navigator.clipboard.readText()")
    assert row == "632005 41 01 110 000\t93,71\ttelefon,fax", repr(row)
    page.locator("summary", has_text="Prečo práve toto").click()
    page.locator("summary", has_text="Vstup z OCR").click()
    expect(page.locator(".ocr-input pre.json")).to_contain_text('"ico": "35763469"')
    page.locator(".ocr-input").get_by_role("button", name="Kopírovať JSON").click()
    assert json.loads(page.evaluate("navigator.clipboard.readText()"))["id"] == "anchor-telekom"
    shot(page, "02-proposal-telekom")

    step("an alternative swaps the whole line, and back")
    select = page.locator(".alternatives select").first
    select.select_option(index=1)
    expect(page.get_by_role("button", name="Prijať so zmenou")).to_be_visible()
    swapped = page.locator(".key").first.inner_text()
    page.get_by_role("button", name="Pôvodný návrh").click()
    expect(page.get_by_role("button", name="Prijať", exact=True)).to_be_visible()
    expect(page.locator(".key").first).to_contain_text("632005")
    print("   swapped to", " ".join(swapped.split()))

    step("accept, then re-propose: the number is used now")
    page.get_by_role("button", name="Prijať", exact=True).click()
    expect(page.get_by_text("Návrh prijatý.")).to_be_visible()
    expect(page.locator(".good-notice")).to_contain_text("FD/144/26")
    shot(page, "03-accepted")
    page.get_by_role("button", name="Navrhnúť znova").click()
    expect(page.locator(".badge", has_text="Na kontrolu")).to_be_visible()
    expect(page.locator(".notice")).to_contain_text("je už použité")

    step("correct a wrong proposal with the dictionary pickers")
    page.goto(f"{BASE}/proposal.html?id=heldout-19-telekom-phone")
    expect(page.get_by_role("heading", name="Rozpočet záväzku")).to_be_visible()
    page.get_by_role("button", name="Opraviť a prijať").click()
    position = page.locator(".editor input[list=positions]").first
    position.fill("633003 41 01 110 000")
    position.dispatch_event("change")
    md = page.locator(".editor input[list=accounts]").first
    expect(md).to_have_value("501 000")
    expect(page.locator(".editor .hint").first).to_contain_text("Telekomunikačná technika")
    page.locator("textarea").fill("nákup telefónov, nie poplatky")
    shot(page, "04-correcting")
    page.get_by_role("button", name="Uložiť opravu").click()
    expect(page.get_by_text("Oprava uložená.")).to_be_visible()
    page.get_by_role("button", name="Navrhnúť znova").click()
    expect(page.locator(".key").first).to_contain_text("633003")
    shot(page, "05-learned")

    step("a picked code outside the dictionaries blocks saving")
    page.goto(f"{BASE}/proposal.html?id=heldout-20-kvetinarstvo-wreath")
    page.get_by_role("button", name="Opraviť a prijať").click()
    page.locator(".editor input[list=accounts]").first.fill("518 999")
    expect(page.locator(".notice.bad")).to_contain_text("518 999")
    expect(page.get_by_role("button", name="Uložiť opravu")).to_be_disabled()
    page.get_by_role("button", name="Zrušiť").click()

    step("a credit note goes to manual entry")
    page.goto(f"{BASE}/proposal.html?id=heldout-35-metro-credit-note")
    expect(page.get_by_role("heading", name="Ručné zaúčtovanie")).to_be_visible()
    expect(page.locator(".notice")).to_contain_text("dobropis")
    shot(page, "06-credit-note")

    step("a split proposal and Slovak review reasons")
    page.goto(f"{BASE}/proposal.html?id=heldout-13-o2-ocu-ms")
    expect(page.locator(".budget-line")).to_have_count(2)
    expect(page.locator(".notice")).to_contain_text("rozdelené podľa položiek")
    shot(page, "07-split")

    step("the picker shows what was processed")
    page.goto(f"{BASE}/")
    expect(page.locator("tr", has_text="Slovak Telekom").locator(".badge").first).to_be_visible()
    shot(page, "08-picker-status")

    step("a pasted invoice")
    invoice = json.load(urllib.request.urlopen(f"{BASE}/api/invoices/anchor-dpo"))
    invoice["id"] = "pasted-dpo"
    page.locator("textarea").fill(json.dumps(invoice, ensure_ascii=False))
    page.get_by_role("button", name="Navrhnúť").click()
    expect(page.locator(".key").first).to_contain_text("637004")
    page.goto(f"{BASE}/")
    page.locator("textarea").fill("{not json")
    page.get_by_role("button", name="Navrhnúť").click()
    expect(page.locator("section.card p.error")).to_contain_text("JSON")

    step("reference browser")
    page.goto(f"{BASE}/reference.html")
    expect(page.locator("tbody tr")).to_have_count(456)
    page.fill("input[type=search]", "telefon")
    expect(page.locator("tbody tr").first).to_contain_text("telefon")
    page.fill("input[type=search]", "")
    expect(page.locator(".key-anatomy")).to_contain_text("Analytika")
    page.get_by_role("tab", name="Upozornenia").click()
    expect(page.locator("tbody")).to_contain_text("zlúčené")
    shot(page, "09-reference")

    step("the series tab shows the counters the feedback moved")
    page.get_by_role("tab", name="Číselné rady").click()
    counters = page.locator("table.counters tbody tr").first
    expect(counters).to_contain_text("FD/253/26")  # after FD/252/26, the corrected heldout-19
    expect(counters).to_contain_text("FD/144/26")
    shot(page, "09b-numbering")

    step("evaluation")
    page.goto(f"{BASE}/eval.html")
    expect(page.locator(".target")).to_have_count(3)
    expect(page.locator(".target").nth(2)).to_contain_text("splnený")
    page.get_by_role("button", name="Tiché chyby").click()
    shot(page, "10-eval")

    step("phone width")
    phone = context.new_page()
    phone.set_viewport_size({"width": 390, "height": 844})
    phone.goto(f"{BASE}/proposal.html?id=anchor-dpo")
    expect(phone.get_by_role("heading", name="Rozpočet záväzku")).to_be_visible()
    phone.locator("summary", has_text="Vstup z OCR").click()
    shot(phone, "11-phone")
    phone.goto(f"{BASE}/about.html")
    expect(phone.locator("pre.json").first).to_contain_text("Slovak Telekom")
    shot(phone, "12-phone-about")
    phone.goto(f"{BASE}/reference.html?tab=series")
    expect(phone.locator("table.counters")).to_be_visible()
    shot(phone, "13-phone-numbering")
    for url in ("/proposal.html?id=anchor-dpo", "/about.html", "/reference.html?tab=series"):
        phone.goto(f"{BASE}{url}")
        phone.wait_for_load_state("networkidle")
        if url.startswith("/proposal"):
            phone.locator("summary", has_text="Vstup z OCR").click()
        width = phone.evaluate("document.documentElement.scrollWidth")
        if width > 390:
            problems.append(f"phone: {url} is {width}px wide")
    browser.close()

for problem in problems:
    print("PROBLEM", problem)
print("click-through done" if not problems else f"{len(problems)} problems")
sys.exit(1 if problems else 0)
