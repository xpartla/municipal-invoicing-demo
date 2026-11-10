"""Four invoice layouts in HTML, modelled on what Slovak municipalities receive:

- `bill`: a utility or telecom bill: dark bars for the amount due, the due date and the VS,
  the supplier's identifiers only in the footer line, several bank accounts;
- `modern`: a two-column invoice from an online billing tool, with a dark payment box;
- `classic`: a sole trader's invoice written in a word processor, framed boxes and a serif;
- `grid`: an accounting system's printout, every block in a framed cell.

Each supplier gets one layout and one `Style` (label wording, date and amount format, accent),
as a real supplier always sends the same form. Nothing is printed that the case does not hold,
except decoration and numbers that are not invoice fields (constant symbol, order number,
customer number), which the extractor must learn to ignore.
"""

import datetime as dt
import hashlib
import html
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from riso.contracts import InvoiceDocument, InvoiceLine
from riso.testdata import printed
from riso.testdata.fonts import BODY_FONTS
from riso.testdata.printed import NBSP, DateStyle
from riso.testdata.truth import LAYOUT_NAMES, LayoutName

# The customer's address as the seed gives it (riso/api/seed.py, BOLDOG_ADDRESS); the
# InvoiceDocument carries only the customer's name and IČO.
CUSTOMER_ADDRESS = {"00305863": ("Boldog 89", "925 26 Boldog")}

# Bank codes of Slovak IBANs (positions 5–8) and the banks' names and BICs, as printed.
BANKS = {
    "0200": ("Všeobecná úverová banka, a.s.", "SUBASKBX"),
    "0900": ("Slovenská sporiteľňa, a.s.", "GIBASKBX"),
    "1100": ("Tatra banka, a.s.", "TATRSKBX"),
    "1111": ("UniCredit Bank Czech Republic and Slovakia, a.s.", "UNCRSKBX"),
    "5200": ("OTP Banka Slovensko, a.s.", "OTPVSKBX"),
    "5600": ("Prima banka Slovensko, a.s.", "KOMASK2X"),
    "6500": ("Poštová banka, a.s.", "POBNSKBA"),
    "7500": ("Československá obchodná banka, a.s.", "CEKOSKBX"),
    "8180": ("Štátna pokladnica", "SPSRSKBA"),
    "8330": ("Fio banka, a.s.", "FIOZSKBX"),
}

# Label wordings per field (plan §8.2); a supplier's style picks one of each.
LABELS: Mapping[str, Sequence[str]] = {
    "supplier": ("Dodávateľ", "DODÁVATEĽ"),
    "customer": ("Odberateľ", "ODBERATEĽ", "Príjemca"),
    "ico": ("IČO",),
    "dic": ("DIČ",),
    "ic_dph": ("IČ DPH", "IČ pre DPH"),
    "iban": ("IBAN", "Číslo účtu", "Číslo účtu (IBAN)", "Bankové spojenie"),
    "vs": ("Variabilný symbol", "VS", "Var. symbol"),
    "issue": ("Dátum vystavenia", "Vystavená dňa", "Dátum vyhotovenia"),
    "delivery": ("Dátum dodania", "Dátum zdaniteľného plnenia", "DZP", "Dátum dodania služby"),
    "due": ("Dátum splatnosti", "Splatnosť", "Splatná dňa"),
    "total": (
        "Celkom k úhrade",
        "Spolu na úhradu",
        "Na úhradu",
        "Celková fakturovaná suma",
        "Suma na úhradu",
        "Celkom",
    ),
    "net": ("Základ DPH", "Spolu bez DPH", "Základ dane"),
    "vat": ("DPH", "Výška DPH"),
    "title": ("Faktúra č.", "Faktúra – daňový doklad č.", "FAKTÚRA č.", "Číslo faktúry"),
    "credit_title": ("Dobropis č.", "Opravný daňový doklad – dobropis č.", "DOBROPIS č."),
}

ACCENTS = ("#1f3b73", "#7a1f3d", "#245a3a", "#4a4a4a", "#8a4b08", "#2d5d7b", "#5b2a86")
LAYOUT_FONTS: Mapping[LayoutName, Sequence[str]] = {
    "bill": ("sans", "office"),
    "modern": ("office", "sans"),
    "classic": ("serif",),
    "grid": ("sans", "office", "serif"),
}


def derive(seed: int, *parts: str) -> int:
    """A 64-bit number from the seed and the parts: every random choice starts from one, so a
    choice does not depend on the order cases are generated in."""
    text = "/".join((str(seed), *parts)).encode()
    return int.from_bytes(hashlib.sha256(text).digest()[:8], "big")


@dataclass(frozen=True, slots=True)
class Style:
    layout: LayoutName
    font: str
    accent: str
    labels: Mapping[str, str]
    colon: bool
    date_style: DateStyle
    currency: str
    grouped_iban: bool
    spaced_ico: bool
    top_margin_mm: float
    side_margin_mm: float
    font_pt: float


def assign_layouts(supplier_keys: Iterable[str], seed: int) -> dict[str, LayoutName]:
    """Each supplier gets a layout, the suppliers spread evenly over the four: shuffled by the
    seed, then dealt out in turn."""
    keys = sorted(set(supplier_keys), key=lambda key: derive(seed, "layout", key))
    return {key: LAYOUT_NAMES[i % len(LAYOUT_NAMES)] for i, key in enumerate(keys)}


def supplier_key(document: InvoiceDocument) -> str:
    """The supplier's identity for its style: the name, which every case has (the IČO is
    missing or misread in some)."""
    return document.supplier.name or document.id


def style_for(key: str, layout: LayoutName, seed: int) -> Style:
    rng = random.Random(derive(seed, "style", key))
    return Style(
        layout=layout,
        font=rng.choice(LAYOUT_FONTS[layout]),
        accent=rng.choice(ACCENTS),
        labels={field: rng.choice(options) for field, options in LABELS.items()},
        colon=layout != "bill" and rng.random() < 0.7,
        date_style=rng.choice(printed.DATE_STYLES),
        currency=rng.choice(("€", "EUR")),
        grouped_iban=rng.random() < 0.8,
        spaced_ico=rng.random() < 0.15,
        top_margin_mm=round(rng.uniform(15, 22), 1),
        side_margin_mm=round(rng.uniform(13, 18), 1),
        font_pt=round(rng.uniform(9.2, 10.4), 1),
    )


@dataclass(frozen=True, slots=True)
class Extras:
    """Numbers on the page that are not invoice fields, per case."""

    constant_symbol: str | None
    order_number: str | None
    customer_number: str | None
    other_accounts: tuple[str, ...]


def extras_for(document: InvoiceDocument, layout: LayoutName, seed: int) -> Extras:
    rng = random.Random(derive(seed, "extras", document.id))
    others: tuple[str, ...] = ()
    if layout == "bill" and document.supplier.iban:
        own = document.supplier.iban.replace(" ", "")[4:8]
        codes = [code for code in ("0200", "0900", "1100", "7500") if code != own]
        others = tuple(_made_up_iban(rng, code) for code in rng.sample(codes, rng.randint(1, 2)))
    return Extras(
        constant_symbol=rng.choice(("0308", "0008", "1148")) if rng.random() < 0.5 else None,
        order_number=f"OBJ-{rng.randint(1, 120):03d}/2026" if rng.random() < 0.3 else None,
        customer_number=str(rng.randint(1_000_000_000, 9_999_999_999))
        if layout == "bill" or rng.random() < 0.2
        else None,
        other_accounts=others,
    )


def _made_up_iban(rng: random.Random, bank: str) -> str:
    """A Slovak IBAN with valid check digits and a random account: a second account of the
    supplier, printed after its own."""
    bban = bank + "".join(str(rng.randint(0, 9)) for _ in range(16))
    check = 98 - int("".join(str(int(c, 36)) for c in bban + "SK00")) % 97
    return f"SK{check:02d}{bban}"


# --- rendering --------------------------------------------------------------------------------


class _Page:
    """The values of one case as the style prints them, ready for a layout."""

    def __init__(self, document: InvoiceDocument, style: Style, extras: Extras) -> None:
        self.doc = document
        self.style = style
        self.extras = extras

    def label(self, field: str) -> str:
        text = self.style.labels[field]
        return f"{text}:" if self.style.colon else text

    def d(self, value: dt.date | None) -> str | None:
        return None if value is None else printed.date(value, self.style.date_style)

    def money(self, value: Decimal | None) -> str | None:
        return None if value is None else printed.money(value, self.style.currency)

    def amount(self, value: Decimal | None) -> str:
        return "" if value is None else printed.amount(value)

    @property
    def credit(self) -> bool:
        return self.doc.invoice.document_type == "credit_note"

    @property
    def title(self) -> str:
        return self.style.labels["credit_title" if self.credit else "title"]

    @property
    def iban(self) -> str | None:
        iban = self.doc.supplier.iban
        return None if iban is None else printed.iban(iban, grouped=self.style.grouped_iban)

    @property
    def bank(self) -> tuple[str, str] | None:
        iban = self.doc.supplier.iban
        return None if iban is None else BANKS.get(iban.replace(" ", "")[4:8])

    def supplier_ids(self) -> list[tuple[str, str]]:
        s = self.doc.supplier
        ids = []
        if s.ico:
            ids.append((self.label("ico"), printed.ico(s.ico, spaced=self.style.spaced_ico)))
        if s.dic:
            ids.append((self.label("dic"), s.dic))
        if s.ic_dph:
            ids.append((self.label("ic_dph"), s.ic_dph))
        return ids

    def customer_lines(self) -> list[str]:
        c = self.doc.customer
        lines = [c.name or ""]
        lines.extend(CUSTOMER_ADDRESS.get(c.ico or "", ()))
        return [line for line in lines if line]

    def customer_ico(self) -> str | None:
        ico = self.doc.customer.ico
        return None if ico is None else printed.ico(ico, spaced=self.style.spaced_ico)

    def address_lines(self) -> list[str]:
        address = self.doc.supplier.address or ""
        street, _, town = address.rpartition(", ")
        return [part for part in (street, town) if part] if street else [address]

    def dates(self) -> list[tuple[str, str]]:
        h = self.doc.invoice
        rows = [
            ("issue", self.d(h.issue_date)),
            ("delivery", self.d(h.delivery_date)),
            ("due", self.d(h.due_date)),
        ]
        return [(self.label(field), value) for field, value in rows if value is not None]

    def notes(self) -> list[str]:
        notes = list(self.doc.free_text)
        if self.doc.supplier.vat_payer is False and not any(
            "platca dph" in note.lower() for note in notes
        ):
            notes.append("Nie som platca DPH.")
        return notes

    def columns(self) -> list[str]:
        """The line table's columns: those any line fills."""
        fields = ("quantity", "unit_price", "net", "vat_rate", "vat", "gross")
        return [f for f in fields if any(getattr(line, f) is not None for line in self.doc.lines)]

    def vat_recap(self) -> list[tuple[Decimal, Decimal, Decimal, Decimal]]:
        """(rate, net, vat, gross) per rate, when the lines carry them and add up to the
        totals; otherwise nothing, and the layout prints the totals only."""
        t = self.doc.totals
        lines = self.doc.lines
        if t.net is None or t.vat is None or t.gross is None:
            return []
        if not lines or any(
            line.vat_rate is None or line.net is None or line.vat is None for line in lines
        ):
            return []
        recap: dict[Decimal, list[Decimal]] = {}
        for line in lines:
            assert line.vat_rate is not None and line.net is not None and line.vat is not None
            row = recap.setdefault(line.vat_rate, [Decimal(0), Decimal(0)])
            row[0] += line.net
            row[1] += line.vat
        net = sum((r[0] for r in recap.values()), Decimal(0))
        vat = sum((r[1] for r in recap.values()), Decimal(0))
        if net != t.net or vat != t.vat:
            return []
        return [(rate, r[0], r[1], r[0] + r[1]) for rate, r in sorted(recap.items())]


def _e(text: object) -> str:
    return html.escape(str(text), quote=True)


def _rows(pairs: Iterable[tuple[str, str]], cls: str = "kv") -> str:
    """Label and value rows. An IBAN is kept on one line, as billing systems print it."""
    cells = "".join(f"<tr><th>{_e(k)}</th><td{_nowrap(v)}>{_e(v)}</td></tr>" for k, v in pairs)
    return f'<table class="{cls}">{cells}</table>'


def _nowrap(value: str) -> str:
    compact = value.replace(" ", "")
    is_iban = len(compact) > 15 and compact[:2].isalpha() and compact[2:4].isdigit()
    return ' class="nw"' if is_iban else ""


def _lines(page: _Page, headers: Mapping[str, str], numbered: bool = False) -> str:
    columns = page.columns()
    head = "".join(f'<th class="n">{_e(headers[c])}</th>' for c in columns)
    first = '<th class="no">Č.</th>' if numbered else ""
    body = []
    for i, line in enumerate(page.doc.lines, start=1):
        cells = "".join(f'<td class="n">{_e(_cell(page, line, c))}</td>' for c in columns)
        number = f'<td class="no">{i}.</td>' if numbered else ""
        body.append(f"<tr>{number}<td>{_e(line.description)}</td>{cells}</tr>")
    return (
        f'<table class="lines"><thead><tr>{first}<th>{_e(headers["description"])}</th>{head}'
        f"</tr></thead><tbody>{''.join(body)}</tbody></table>"
    )


def _cell(page: _Page, line: InvoiceLine, column: str) -> str:
    value = getattr(line, column)
    if value is None:
        return ""
    if column == "quantity":
        unit = f"{NBSP}{line.unit}" if line.unit else ""
        return f"{printed.quantity(value)}{unit}"
    if column == "vat_rate":
        return printed.percent(value)
    return page.amount(value)


def _totals(page: _Page, cls: str = "totals") -> str:
    t = page.doc.totals
    recap = page.vat_recap()
    parts = []
    if recap:
        rows = "".join(
            f'<tr><td>{_e(printed.percent(rate))}</td><td class="n">{_e(page.amount(net))}</td>'
            f'<td class="n">{_e(page.amount(vat))}</td><td class="n">{_e(page.amount(gross))}</td>'
            "</tr>"
            for rate, net, vat, gross in recap
        )
        parts.append(
            f'<table class="recap"><thead><tr><th>Sadzba DPH</th><th class="n">'
            f'{_e(page.style.labels["net"])}</th><th class="n">{_e(page.style.labels["vat"])}'
            f'</th><th class="n">Spolu</th></tr></thead><tbody>{rows}</tbody></table>'
        )
    else:
        pairs = []
        if t.net is not None:
            pairs.append((page.label("net"), page.money(t.net) or ""))
        if t.vat is not None:
            pairs.append((page.label("vat"), page.money(t.vat) or ""))
        if pairs:
            parts.append(_rows(pairs, "kv sums"))
    if t.gross is not None:
        parts.append(
            f'<div class="due"><span>{_e(page.label("total"))}</span>'
            f"<strong>{_e(page.money(t.gross))}</strong></div>"
        )
    return f'<div class="{cls}">{"".join(parts)}</div>'


def _notes(page: _Page) -> str:
    return "".join(f'<p class="note">{_e(note)}</p>' for note in page.notes())


def _ids_inline(page: _Page) -> str:
    return "&emsp;".join(f"{_e(k.replace(' ', NBSP))}{NBSP}{_e(v)}" for k, v in page.supplier_ids())


def _payment(page: _Page) -> list[tuple[str, str]]:
    rows = []
    if page.iban:
        rows.append((page.label("iban"), page.iban))
        if page.bank:
            rows.append(("SWIFT" + (":" if page.style.colon else ""), page.bank[1]))
    if page.doc.invoice.variable_symbol:
        rows.append((page.label("vs"), page.doc.invoice.variable_symbol))
    if page.extras.constant_symbol:
        rows.append(
            ("Konštantný symbol" + (":" if page.style.colon else ""), page.extras.constant_symbol)
        )
    return rows


LINE_HEADERS = {
    "description": "Popis",
    "quantity": "Množstvo",
    "unit_price": "Jedn. cena",
    "net": "Bez DPH",
    "vat_rate": "DPH %",
    "vat": "DPH",
    "gross": "Spolu",
}


def _bill(page: _Page) -> str:
    doc, style = page.doc, page.style
    payment = []
    if doc.totals.gross is not None:
        payment.append(f'<div class="bar"><span>{_e(page.style.labels["total"].upper())}</span>'
                       f"<b>{_e(page.money(doc.totals.gross))}</b></div>")  # fmt: skip
    if doc.invoice.due_date is not None:
        payment.append(f'<div class="bar"><span>{_e(style.labels["due"].upper())}</span>'
                       f"<b>{_e(page.d(doc.invoice.due_date))}</b></div>")  # fmt: skip
    if doc.invoice.variable_symbol:
        payment.append(f'<div class="bar"><span>{_e(style.labels["vs"].upper())}</span>'
                       f"<b>{_e(doc.invoice.variable_symbol)}</b></div>")  # fmt: skip
    accounts = []
    if page.iban:
        bank = page.bank[0] if page.bank else ""
        accounts.append(f"{_e(bank)}: {_e(page.label('iban'))} {_e(page.iban)}")
        for other in page.extras.other_accounts:
            other_bank = BANKS.get(other[4:8], ("",))[0]
            accounts.append(
                f"{_e(other_bank)}: {_e(printed.iban(other, grouped=style.grouped_iban))}"
            )
    footer_ids = ", ".join(f"{k} {v}" for k, v in page.supplier_ids())
    footer = ", ".join(p for p in (doc.supplier.name, doc.supplier.address, footer_ids) if p)
    ks = page.extras.constant_symbol
    customer_no = page.extras.customer_number
    return f"""
<header class="bill-head">
  <div class="logo">{_e(doc.supplier.name)}</div>
  <div class="right">
    <div class="big">{_e(page.title)} {_e(doc.invoice.number or "")}</div>
    {f"<div>Zákaznícke číslo {_e(customer_no)}</div>" if customer_no else ""}
  </div>
</header>
<div class="cols">
  <section class="box">
    <h2>ADRESNÉ ÚDAJE</h2>
    <p><b>{_e(style.labels["customer"].upper())}</b><br>{"<br>".join(_e(x) for x in page.customer_lines())}</p>
    {f"<p>IČO: {_e(page.customer_ico())}</p>" if page.customer_ico() else ""}
    <h2>FAKTURAČNÉ ÚDAJE</h2>
    {_rows(page.dates())}
  </section>
  <section class="box">
    <h2>PLATOBNÉ ÚDAJE</h2>
    {"".join(payment)}
    {f'<p class="small">Konštantný symbol: {_e(ks)}</p>' if ks else ""}
    <p class="small">Faktúru prosím uhraďte platobným príkazom na jeden z uvedených účtov.</p>
    <p class="small">{"<br>".join(accounts)}</p>
  </section>
</div>
<h2 class="band">POLOŽKY</h2>
{_lines(page, LINE_HEADERS)}
<h2 class="band">SUMARIZÁCIA</h2>
{_totals(page)}
<div class="notes">{_notes(page)}</div>
<footer class="small">{_e(footer)}. Zapísaná v Obchodnom registri Okresného súdu.</footer>
"""  # noqa: E501


def _modern(page: _Page) -> str:
    doc, style = page.doc, page.style
    supplier = "<br>".join(_e(x) for x in [doc.supplier.name or "", *page.address_lines()] if x)
    customer = "<br>".join(_e(x) for x in page.customer_lines())
    pay = [("Spôsob úhrady" + (":" if style.colon else ""), "Bankový prevod"), *_payment(page)]
    pay_html = "".join(f"<div>{_e(k)} <b>{_e(v)}</b></div>" for k, v in pay)
    order = page.extras.order_number
    headers = {
        "description": "Názov",
        "quantity": "Množstvo",
        "unit_price": "Cena bez DPH",
        "net": "Spolu bez DPH",
        "vat_rate": "DPH %",
        "vat": "DPH",
        "gross": "Spolu s DPH",
    }
    return f"""
<header class="modern-head">
  <div class="logo">{_e(doc.supplier.name)}</div>
  <div class="big">{_e(page.title)} {_e(doc.invoice.number or "")}</div>
</header>
<div class="cols">
  <section><h3>{_e(style.labels["supplier"])}</h3><p>{supplier}</p><p>{_ids_inline(page)}</p></section>
  <section><h3>{_e(style.labels["customer"])}</h3><p>{customer}</p>
    {f"<p>IČO: {_e(page.customer_ico())}</p>" if page.customer_ico() else ""}</section>
</div>
<div class="cols">
  <section>{_rows(page.dates())}{f'<p class="small">Číslo objednávky: {_e(order)}</p>' if order else ""}</section>
  <section class="paybox"><div class="sum">{_e(style.labels["total"])}<br><b>{_e(page.money(doc.totals.gross))}</b></div>{pay_html}</section>
</div>
{_lines(page, headers, numbered=True)}
{_totals(page)}
<div class="notes">{_notes(page)}</div>
<div class="sign">Pečiatka a podpis</div>
<footer class="small">Spoločnosť je zapísaná v Obchodnom registri. <span class="pageno">Strana 1/1</span></footer>
"""  # noqa: E501


def _classic(page: _Page) -> str:
    doc, style = page.doc, page.style
    left = [*page.dates(), ("Forma úhrady" + (" :" if style.colon else ""), "prevodom")]
    if page.bank:
        left.append(("Banka dodávateľa" + (" :" if style.colon else ""), page.bank[0]))
    if page.iban:
        left.append((page.label("iban"), page.iban))
    if doc.invoice.variable_symbol:
        left.append((page.label("vs"), doc.invoice.variable_symbol))
    supplier = "<br>".join(_e(x) for x in [doc.supplier.name or "", *page.address_lines()] if x)
    customer = "<br>".join(_e(x) for x in page.customer_lines())
    subtitle = "(DAŇOVÝ DOKLAD)" if doc.supplier.vat_payer else ""
    simple = page.columns() == ["gross"]
    if simple:
        body = "".join(
            f"<tr><td>{_e(line.description)}</td>"
            f'<td class="n">{_e(page.money(line.gross))}</td></tr>'
            for line in doc.lines
        )
        lines = f'<table class="plain">{body}</table>'
    else:
        lines = _lines(page, LINE_HEADERS)
    gross = page.money(doc.totals.gross) or ""
    return f"""
<div class="cols framed">
  <section>
    <div class="big">{_e(page.title)} {_e(doc.invoice.number or "")}</div>
    <div class="small">{subtitle}</div>
    {_rows(left)}
  </section>
  <section>
    <h3>{_e(style.labels["supplier"].upper())}{" :" if style.colon else ""}</h3>
    <p><b>{supplier}</b></p>
    <p>{_ids_inline(page)}</p>
    <h3>{_e(style.labels["customer"].upper())}{" :" if style.colon else ""}</h3>
    <p>{customer}</p>
    {f"<p>IČO: {_e(page.customer_ico())}</p>" if page.customer_ico() else ""}
  </section>
</div>
<div class="body">
  {"".join(f"<p>{_e(note)}</p>" for note in page.notes()[:1])}
  {lines}
  {_totals(page)}
  <div class="notes">{"".join(f'<p class="note">{_e(note)}</p>' for note in page.notes()[1:])}</div>
</div>
<div class="cols bottom">
  <section class="small">Faktúru vystavil:<br><br>Podpis a pečiatka</section>
  <section class="framed-total">{_e(style.labels["total"])} <b>{_e(gross)}</b></section>
</div>
"""  # noqa: E501


def _grid(page: _Page) -> str:
    doc, style = page.doc, page.style
    supplier = "<br>".join(_e(x) for x in [doc.supplier.name or "", *page.address_lines()] if x)
    customer = "<br>".join(_e(x) for x in page.customer_lines())
    ids = "<br>".join(f"{_e(k)} {_e(v)}" for k, v in page.supplier_ids())
    pay = [("Forma úhrady" + (":" if style.colon else ""), "prevodným príkazom")]
    if page.bank:
        pay.append(("Peňažný ústav" + (":" if style.colon else ""), page.bank[0]))
    pay.extend(_payment(page))
    order = page.extras.order_number
    if order:
        pay.append(("Objednávka" + (":" if style.colon else ""), order))
    headers = {
        "description": "Označenie dodávky",
        "quantity": "Množstvo",
        "unit_price": "Cena za MJ",
        "net": "Bez DPH",
        "vat_rate": "%DPH",
        "vat": "DPH",
        "gross": "Celkom",
    }
    customer_no = page.extras.customer_number
    return f"""
<header class="grid-head"><div class="big">{_e(page.title)}</div><div class="numbox">{_e(doc.invoice.number or "")}</div></header>
<div class="grid">
  <section><h3>{_e(style.labels["supplier"])}</h3><p>{supplier}</p><p>{ids}</p></section>
  <section class="thick"><h3>{_e(style.labels["customer"])}</h3><p>{customer}</p>
    {f"<p>IČO: {_e(page.customer_ico())}</p>" if page.customer_ico() else ""}
    {f'<p class="small">Číslo zákazníka: {_e(customer_no)}</p>' if customer_no else ""}</section>
  <section>{_rows(pay)}</section>
  <section>{_rows(page.dates())}</section>
</div>
{_lines(page, headers)}
<div class="recap-title">Rekapitulácia</div>
{_totals(page, "totals boxed")}
<div class="notes">{_notes(page)}</div>
<footer class="small">Vystavil: fakturácia&emsp;Prevzal:</footer>
"""  # noqa: E501


_BODIES = {"bill": _bill, "modern": _modern, "classic": _classic, "grid": _grid}

_CSS = """
@font-face{{font-family:Body;src:url({regular});font-weight:400}}
@font-face{{font-family:Body;src:url({bold});font-weight:700}}
@page{{size:A4;margin:0}}
*{{box-sizing:border-box}}
html,body{{margin:0;padding:0;background:#fff}}
body{{font-family:Body;color:#111;font-size:calc({pt}pt * var(--fit, 1));line-height:1.3}}
.page{{width:210mm;height:297mm;overflow:hidden;padding:{top}mm {side}mm 12mm {side}mm}}
.content{{height:100%;overflow:hidden;display:flex;flex-direction:column;gap:3.2mm}}
h2,h3{{margin:0;font-size:1em}}
p{{margin:0 0 1mm 0}}
table{{border-collapse:collapse;width:100%}}
th{{text-align:left;font-weight:700}}
.kv th{{font-weight:400;padding:0.3mm 3mm 0.3mm 0;white-space:nowrap;width:1%}}
.kv td{{padding:0.3mm 0}}
.n,.nw{{text-align:right;white-space:nowrap}} .nw{{text-align:left}}
.no{{width:7mm}}
.small{{font-size:0.82em}}
.big{{font-size:1.65em;font-weight:700}}
.logo{{font-size:1.8em;font-weight:700;color:{accent}}}
.cols{{display:flex;gap:6mm}} .cols>section{{flex:1}}
.lines{{font-size:0.9em}} .lines th,.lines td{{padding:0.8mm 1.2mm;vertical-align:top}}
.lines thead th{{border-bottom:0.4mm solid #333}}
.lines tbody td{{border-bottom:0.15mm solid #bbb}}
.recap{{width:70%;margin-left:auto;font-size:0.9em}} .recap td,.recap th{{padding:0.6mm 1.5mm}}
.sums{{width:auto;margin-left:auto}}
.due{{display:flex;justify-content:space-between;margin-left:auto;width:70%;padding:1.5mm 2mm;
     font-size:1.2em;border-top:0.5mm solid #111}}
.notes .note{{font-size:0.85em;margin:0}}
footer{{margin-top:auto;color:#333}}
.pageno{{float:right}}
/* bill */
.bill-head{{display:flex;justify-content:space-between;align-items:flex-end}}
.bill-head .right{{text-align:right}}
.box{{border:0.3mm solid #999}} .box h2{{background:{accent};color:#fff;padding:1mm 2mm;margin-bottom:1.5mm}}
.box>p,.box>table{{padding:0 2mm}}
.bar{{display:flex;justify-content:space-between;background:#333;color:#fff;padding:1.2mm 2mm;margin:0 0 1mm 0}}
.band{{background:{accent};color:#fff;padding:0.8mm 2mm}}
/* modern */
.modern-head{{display:flex;justify-content:space-between;align-items:center}}
.modern-head .big{{font-weight:400}}
.layout-modern h3,.cols h3{{color:#555;font-weight:400;text-transform:uppercase;letter-spacing:0.05em}}
.paybox{{background:#4d4d4d;color:#f4f4f4;padding:2.5mm 3mm}}
.paybox .sum b{{font-size:1.5em}}
.sign{{margin-left:55%;border-top:0.2mm solid #555;padding-top:1mm;font-size:0.85em;width:40%}}
/* classic */
.framed{{border:0.3mm solid #111}} .framed>section{{padding:2.5mm}}
.framed>section+section{{border-left:0.3mm solid #111}}
.body{{border:0.3mm solid #111;border-top:0;padding:3mm;flex:1;display:flex;flex-direction:column;gap:3mm}}
.plain td{{padding:1.5mm 0}}
.bottom .framed-total{{border:0.3mm solid #111;padding:3mm;text-align:right}}
/* grid */
.grid-head{{display:flex;justify-content:space-between;align-items:center;border-bottom:0.6mm solid {accent}}}
.numbox{{border:0.4mm solid #111;padding:1mm 4mm;font-size:1.3em;font-weight:700}}
.grid{{display:grid;grid-template-columns:1fr 1fr;border:0.3mm solid #111}}
.grid>section{{padding:2mm;border:0.15mm solid #111}}
.grid .thick{{border:0.6mm solid #111}}
.grid h3{{font-size:0.85em;color:#333}}
.recap-title{{font-weight:700}}
.boxed{{border:0.3mm solid #111;padding:2mm}}
"""  # noqa: E501 - CSS, one rule per line


def page_html(document: InvoiceDocument, style: Style, extras: Extras, font_url: str) -> str:
    """The invoice as one A4 page of HTML. `font_url` is the base the vendored fonts are
    served from (the renderer intercepts it)."""
    font = BODY_FONTS[style.font]
    css = _CSS.format(
        regular=f"{font_url}/{font.regular}",
        bold=f"{font_url}/{font.bold}",
        pt=style.font_pt,
        top=style.top_margin_mm,
        side=style.side_margin_mm,
        accent=style.accent,
    )
    body = _BODIES[style.layout](_Page(document, style, extras))
    return (
        f'<!doctype html><html lang="sk"><head><meta charset="utf-8"><title>{_e(document.id)}'
        f'</title><style>{css}</style></head><body><div class="page"><div class="content '
        f'layout-{style.layout}">{body}</div></div></body></html>'
    )
