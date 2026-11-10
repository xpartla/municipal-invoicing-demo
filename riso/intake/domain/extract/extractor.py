"""The field extractor (plan §8.2 steps 4–5, §8.3): a `DocumentLayout` becomes an
`InvoiceDocument` with a confidence per field, where each value was read, and warnings.

It reads labels and geometry only, never engine specifics, so any `DocumentReader` feeds it.
Confidence starts from the OCR's confidence in the value's words and how the value was found
(on the label's line, beside it, under it, or without a label), then validation moves it: a
value that passes its check (IČO check digit, IBAN mod-97, net + VAT = gross, dates in order,
an agreeing second reading) is raised to at least `TRUSTED`; one that fails is held below
`DOUBTFUL`, so the check step marks it (plan §8.5) and it never passes silently.

The handwritten date and number are not read here (P2-M5-T06): the extractor leaves them
empty, and they are never accepted without the user.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from riso.contracts import (
    Handwritten,
    Intake,
    InvoiceCustomer,
    InvoiceDocument,
    InvoiceHeader,
    InvoiceLine,
    InvoiceSupplier,
    OcrMeta,
    Totals,
)
from riso.intake.domain.extract import values
from riso.intake.domain.extract.anchors import Candidate, free, hits, values_for
from riso.intake.domain.extract.labels import (
    CREDIT_NOTE,
    CUSTOMER_HEADINGS,
    LABELS,
    LINES_END,
    LINES_HEADER,
    NOT_VAT_PAYER,
    SUPPLIER_HEADINGS,
)
from riso.intake.domain.extract.text import TextLine, iter_rows, text_lines
from riso.intake.domain.layout import Box, DocumentLayout

DOUBTFUL = 0.6
"""Below this the check step marks a field amber (plan §8.5)."""
TRUSTED = 0.9
_ID_LABELS = tuple(label for label in LABELS if label.field in ("ico", "dic", "ic_dph", "iban"))
FAILED = 0.35
"""The most a value that failed its check keeps."""


@dataclass(frozen=True, slots=True)
class Evidence:
    """Where a value was read: the page and the box of its words."""

    page: int
    box: Box
    text: str


@dataclass(frozen=True, slots=True)
class Context:
    """What the extractor is told: the acting customer, to tell its IČO from the supplier's
    and to warn when the invoice is addressed to someone else."""

    customer_ico: str | None = None
    customer_name: str | None = None


@dataclass(slots=True)
class _Field[T]:
    value: T
    confidence: float
    evidence: Evidence | None = None
    guessed: bool = False
    """Found without its label; validation never raises it."""


@dataclass(frozen=True, slots=True)
class Extracted:
    document: InvoiceDocument
    evidence: dict[str, Evidence]
    warnings: tuple[str, ...]


def _evidence(candidate: Candidate[Any]) -> Evidence:
    return Evidence(
        candidate.page, candidate.box, candidate.line.text[candidate.start : candidate.end]
    )


def _base(candidate: Candidate[Any]) -> float:
    return candidate.ocr_confidence * candidate.anchored()


@dataclass(slots=True)
class _Fields:
    found: dict[str, _Field[Any]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def put(
        self, path: str, candidate: Candidate[Any] | None, confidence: float | None = None
    ) -> None:
        if candidate is None:
            return
        self.found[path] = _Field(
            candidate.value,
            _base(candidate) if confidence is None else confidence,
            _evidence(candidate),
        )

    def value(self, path: str) -> Any:
        found = self.found.get(path)
        return None if found is None else found.value

    def trust(self, path: str) -> None:
        if path in self.found and not self.found[path].guessed:
            self.found[path].confidence = max(self.found[path].confidence, TRUSTED)

    def doubt(self, path: str, ceiling: float = FAILED) -> None:
        if path in self.found:
            self.found[path].confidence = min(self.found[path].confidence, ceiling)


def _section(line: TextLine, lines: Sequence[TextLine]) -> str | None:
    """`supplier` or `customer`: the nearest heading above the line in its column (within a
    third of the page), else None."""
    box = line.box
    best: tuple[int, str] | None = None
    for other in lines:
        if other.page != line.page or other.box.y0 > box.y0 + 2:
            continue
        kind = (
            "supplier"
            if SUPPLIER_HEADINGS.search(other.folded)
            else "customer"
            if CUSTOMER_HEADINGS.search(other.folded)
            else None
        )
        if kind is None:
            continue
        column = abs(other.box.x0 - box.x0) < line.page_width * 0.2
        distance = box.y0 - other.box.y0
        if column and distance < line.page_height / 3 and (best is None or distance < best[0]):
            best = (distance, kind)
    return best[1] if best else None


def _labelled(
    lines: Sequence[TextLine], field_name: str, parse: Any, below: int = 3
) -> list[Candidate[Any]]:
    found: list[Candidate[Any]] = []
    for hit in hits(lines, field_name):
        found.extend(values_for(hit, lines, parse, below=below))
    return found


def _ranked[T](candidates: Sequence[Candidate[T]]) -> list[Candidate[T]]:
    """Strong labels before weak ones, then by route, then reading order."""
    return sorted(
        candidates,
        key=lambda c: (
            c.label is not None and c.label.strength == "weak",
            -c.anchored(),
            c.line.order,
            c.start,
        ),
    )


class FieldExtractor:
    def extract(
        self,
        layout: DocumentLayout,
        *,
        document_id: str,
        context: Context,
        channel: Literal["scan", "digital_pdf"] = "scan",
        media: str | None = None,
    ) -> Extracted:
        lines = text_lines(layout)
        fields = _Fields()
        self._parties(lines, context, fields)
        self._payment(lines, fields)
        self._dates(lines, fields)
        self._totals(lines, fields)
        self._number(lines, fields)
        self._vs_from_number(lines, fields)
        rows = self._lines(lines)
        folded = " ".join(line.folded for line in lines)
        credit = bool(CREDIT_NOTE.search(folded))
        vat_payer: bool | None = None
        if NOT_VAT_PAYER.search(folded):
            vat_payer = False
        elif fields.value("supplier.ic_dph"):
            vat_payer = True
        self._validate(fields, context, credit)
        document = InvoiceDocument(
            id=document_id,
            supplier=InvoiceSupplier(
                name=fields.value("supplier.name"),
                ico=fields.value("supplier.ico"),
                dic=fields.value("supplier.dic"),
                ic_dph=fields.value("supplier.ic_dph"),
                iban=fields.value("supplier.iban"),
                address=fields.value("supplier.address"),
                vat_payer=vat_payer,
            ),
            customer=InvoiceCustomer(
                name=fields.value("customer.name"), ico=fields.value("customer.ico")
            ),
            invoice=InvoiceHeader(
                number=fields.value("invoice.number"),
                issue_date=fields.value("invoice.issue_date"),
                delivery_date=fields.value("invoice.delivery_date"),
                due_date=fields.value("invoice.due_date"),
                variable_symbol=fields.value("invoice.variable_symbol"),
                document_type="credit_note" if credit else "invoice",
            ),
            handwritten=Handwritten(),
            totals=Totals(
                net=fields.value("totals.net"),
                vat=fields.value("totals.vat"),
                gross=fields.value("totals.gross"),
            ),
            lines=rows,
            ocr_meta=OcrMeta(
                page_count=len(layout.pages),
                confidence={p: round(f.confidence, 3) for p, f in sorted(fields.found.items())},
            ),
            intake=Intake(channel=channel, format=media),
        )
        evidence = {p: f.evidence for p, f in fields.found.items() if f.evidence is not None}
        return Extracted(document, evidence, tuple(dict.fromkeys(fields.warnings)))

    # The parties ----------------------------------------------------------------------------

    def _parties(self, lines: Sequence[TextLine], context: Context, fields: _Fields) -> None:
        customer_ico = context.customer_ico
        supplier, customer = [], []
        for candidate in _ranked(_labelled(lines, "ico", values.icos, below=2)):
            section = _section(candidate.line, lines)
            if candidate.value == customer_ico or section == "customer":
                customer.append(candidate)
            else:
                supplier.append(candidate)
        valid = [c for c in supplier if values.ico_valid(c.value)]
        chosen = valid or supplier
        fields.put("supplier.ico", chosen[0] if chosen else None)
        if customer:
            fields.put("customer.ico", customer[0])
            if customer_ico and customer[0].value != customer_ico:
                fields.warnings.append("addressed_to_another_entity")
        for path, name, parse in (
            ("supplier.dic", "dic", values.dics),
            ("supplier.ic_dph", "ic_dph", values.ic_dphs),
        ):
            found = [
                c
                for c in _ranked(_labelled(lines, name, parse, below=2))
                if _section(c.line, lines) != "customer"
            ]
            fields.put(path, found[0] if found else None)
        self._names(lines, fields)

    def _names(self, lines: Sequence[TextLine], fields: _Fields) -> None:
        for path, heading in (("supplier", SUPPLIER_HEADINGS), ("customer", CUSTOMER_HEADINGS)):
            name, address = self._block(lines, heading)
            if name is not None:
                fields.found[f"{path}.name"] = name
            if address is not None and path == "supplier":
                fields.found["supplier.address"] = address
        if "supplier.name" not in fields.found:
            logo = self._logo(lines)
            if logo is not None:
                fields.found["supplier.name"] = logo

    def _block(
        self, lines: Sequence[TextLine], heading: Any
    ) -> tuple[_Field[str] | None, _Field[str] | None]:
        """The name and address under a party's heading: the first line after it in its
        column, then up to two lines with a postcode or a house number."""
        for line in lines:
            match = heading.search(line.folded)
            if match is None:
                continue
            rest = line.text[match.end() :].strip(" :")
            following = [
                ln
                for ln in lines
                if ln.page == line.page
                and ln.order > line.order
                and abs(ln.box.x0 - line.box.x0) < line.page_width * 0.15
                and ln.box.y0 - line.box.y1 < line.box.height * 6
            ][:4]
            name_line: TextLine | None = None
            if len(rest) > 2:
                name_text, conf, box = (
                    rest,
                    line.confidence_of(match.end(), len(line.text)),
                    line.box,
                )
            elif following:
                name_line = following[0]
                name_text, conf, box = (
                    name_line.text,
                    min(w.confidence for w in name_line.words),
                    name_line.box,
                )
            else:
                continue
            name = _Field(name_text, conf * 0.9, Evidence(line.page, box, name_text))
            address_parts = []
            for other in following[1 if name_line else 0 :]:
                if any(lab.pattern.search(other.folded) for lab in _ID_LABELS):
                    break
                if any(c.isdigit() for c in other.text):
                    address_parts.append(other.text)
                if len(address_parts) == 2:
                    break
            address = _Field(", ".join(address_parts), 0.7, None) if address_parts else None
            return name, address
        return None, None

    def _logo(self, lines: Sequence[TextLine]) -> _Field[str] | None:
        """The supplier's name as its logo: the tallest text in the top fifth of page 1."""
        top = [
            ln
            for ln in lines
            if ln.page == 0
            and ln.box.y1 < ln.page_height * 0.2
            and sum(c.isalpha() for c in ln.text) >= 3
            and sum(c.isdigit() for c in ln.text) < 0.3 * len(ln.text)
            and not any(label.pattern.search(ln.folded) for label in LABELS)
            and not CUSTOMER_HEADINGS.search(ln.folded)
            and not SUPPLIER_HEADINGS.search(ln.folded)
        ]
        if not top:
            return None
        tallest = max(top, key=lambda ln: sum(w.box.height for w in ln.words) / len(ln.words))
        conf = min(w.confidence for w in tallest.words) * 0.7
        return _Field(tallest.text, conf, Evidence(tallest.page, tallest.box, tallest.text))

    # Payment ------------------------------------------------------------------------------------

    def _payment(self, lines: Sequence[TextLine], fields: _Fields) -> None:
        labelled = [c for c in _ranked(_labelled(lines, "iban", values.ibans, below=2))]
        everywhere = free(lines, values.ibans)
        candidates = labelled + everywhere
        valid = [c for c in candidates if c.value[1]]
        chosen = valid[0] if valid else (candidates[0] if candidates else None)
        if chosen is not None:
            iban, ok = chosen.value
            confidence = _base(chosen)
            confidence = max(confidence, TRUSTED) if ok else min(confidence, FAILED)
            # Several accounts on the page (a bill lists the supplier's banks): which one the
            # invoice is paid to is the user's to confirm, as is a valid one that a misread
            # account comes before.
            accounts = {c.value[0] for c in everywhere}
            first = min(everywhere, key=lambda c: (c.line.order, c.start), default=None)
            if len(accounts) > 1 or (first is not None and not first.value[1] and ok):
                confidence = min(confidence, 0.55)
            # Found only without its label while the page labels an account: the labelled
            # one was not read, and this may be another account.
            if chosen.label is None and hits(lines, "iban"):
                confidence = min(confidence, 0.55)
            # Read under its label rather than beside it: on a list of accounts, the next
            # one down is someone else's when the labelled one was not read.
            if chosen.route == "below":
                confidence = min(confidence, 0.55)
            fields.found["supplier.iban"] = _Field(iban, confidence, _evidence(chosen))
        vs = _ranked(_labelled(lines, "vs", values.digit_runs, below=2))
        fields.put("invoice.variable_symbol", vs[0] if vs else None)

    def _vs_from_number(self, lines: Sequence[TextLine], fields: _Fields) -> None:
        """Without a variable symbol's label, a standalone number equal to the invoice
        number's last digits (the usual VS), left for the user to confirm."""
        number = fields.value("invoice.number")
        if fields.value("invoice.variable_symbol") is not None or not number:
            return
        digits = "".join(c for c in number if c.isdigit())
        for candidate in free(lines, values.digit_runs):
            value = candidate.value
            words = candidate.line.words_in(candidate.start, candidate.end)
            standalone = len(words) == 1 and words[0].text.strip(".,:;") == value
            number_box = fields.found["invoice.number"].evidence
            elsewhere = number_box is None or candidate.box != number_box.box
            if standalone and elsewhere and len(value) >= 6 and digits.endswith(value):
                fields.put("invoice.variable_symbol", candidate, min(_base(candidate), 0.55))
                fields.found["invoice.variable_symbol"].guessed = True
                return

    # Dates --------------------------------------------------------------------------------------

    def _dates(self, lines: Sequence[TextLine], fields: _Fields) -> None:
        for path, name in (
            ("invoice.issue_date", "issue_date"),
            ("invoice.delivery_date", "delivery_date"),
            ("invoice.due_date", "due_date"),
        ):
            found = _ranked(_labelled(lines, name, values.dates, below=2))
            fields.put(path, found[0] if found else None)

    # Totals -------------------------------------------------------------------------------------

    def _totals(self, lines: Sequence[TextLine], fields: _Fields) -> None:
        # A weak label ("Spolu", "Celkom") also heads a table's column, whose value below is a
        # line's: it counts only for a value on its own line or row.
        gross = [
            c
            for c in _ranked(_labelled(lines, "gross", values.amounts, below=2))
            if c.label is None or c.label.strength == "strong" or c.route != "below"
        ]
        strong_labels = [h for h in hits(lines, "gross") if h.label.strength == "strong"]
        if gross:
            strong = [c for c in gross if c.label is not None and c.label.strength == "strong"]
            pool = strong or gross
            votes = Counter(c.value for c in pool)
            best_value, count = votes.most_common(1)[0]
            chosen = next(c for c in pool if c.value == best_value)
            confidence = _base(chosen)
            if count > 1:
                confidence = max(confidence, TRUSTED)
            elif len(votes) > 1:
                confidence = min(confidence, 0.55)
            if strong_labels and not strong:
                # The total's own label was found, its value not read: the rest is a guess.
                confidence = min(confidence, 0.55)
            fields.put("totals.gross", chosen, confidence)
        if self._recap(lines, fields):
            return
        for path, name in (("totals.net", "net"), ("totals.vat", "vat")):
            found = _ranked(_labelled(lines, name, values.amounts, below=2))
            if found:
                # Unconfirmed by the total until the validation adds them up.
                fields.put(path, found[0], min(_base(found[0]), 0.55))

    def _recap(self, lines: Sequence[TextLine], fields: _Fields) -> bool:
        """Net and VAT from the totals' rows: on a row, three amounts where the first two
        add up to the third; the rows whose third amounts add up to the total (one per VAT
        rate). An item's row adds up too, so it counts only with the total."""
        gross = fields.value("totals.gross")
        if gross is None:
            return False
        triples = []
        for row in iter_rows(lines):
            amounts = [a for line in row for a, _ in values.amounts(line.text)]
            for i in range(len(amounts) - 2):
                a, b, c = amounts[i : i + 3]
                if c != 0 and abs(a + b - c) <= Decimal("0.01") and abs(b) < abs(c):
                    triples.append((a, b, c, row[0]))
                    break
        exact = [t for t in triples if t[2] == gross]
        chosen = exact[-1:] if exact else []
        if not chosen:
            # Several rates: the last rows whose totals add up to the invoice's.
            for size in (2, 3):
                for start in range(len(triples) - size, -1, -1):
                    group = triples[start : start + size]
                    if sum((t[2] for t in group), Decimal(0)) == gross:
                        chosen = group
                        break
                if chosen:
                    break
        if not chosen:
            return False
        line = chosen[0][3]
        net = sum((t[0] for t in chosen), Decimal(0))
        vat = sum((t[1] for t in chosen), Decimal(0))
        conf = min(w.confidence for w in line.words)
        # As sure as the total they add up to.
        total = fields.found["totals.gross"].confidence
        sure = max(conf, TRUSTED) if total >= TRUSTED else min(conf, total)
        evidence = Evidence(line.page, line.box, line.text)
        fields.found["totals.net"] = _Field(net, sure, evidence)
        fields.found["totals.vat"] = _Field(vat, sure, evidence)
        return True

    # The document's number ----------------------------------------------------------------------

    def _number(self, lines: Sequence[TextLine], fields: _Fields) -> None:
        found = [
            c
            for c in _ranked(_labelled(lines, "number", values.document_numbers, below=1))
            if not values.dates(c.value)
            and not values.amounts(c.value)
            and not c.value.endswith(("-", "/", "."))  # cut off: the rest was not read
            and len(c.value) >= 3
        ]
        fields.put("invoice.number", found[0] if found else None)

    # Lines (best effort) ------------------------------------------------------------------------

    def _lines(self, lines: Sequence[TextLine]) -> list[InvoiceLine]:
        """The invoice's lines, best effort (plan §8.2): under the table's header (a line
        naming two of its columns), each row with an amount until the totals begin; the
        text before the row's first number is the description, its last amount the gross."""
        header = next((ln for ln in lines if len(LINES_HEADER.findall(ln.folded)) >= 2), None)
        if header is None:
            return []
        rows: list[InvoiceLine] = []
        for row in iter_rows([ln for ln in lines if ln.page == header.page]):
            if row[0].box.y0 <= header.box.y1:
                continue
            text = " ".join(line.text for line in row)
            if LINES_END.search(" ".join(line.folded for line in row)):
                break
            amounts = values.amounts(text)
            if not amounts:
                continue
            words = text[: amounts[0][1].start].split()
            if words and words[0].rstrip(".").isdigit():
                words = words[1:]  # the row's number
            while words and any(c.isdigit() for c in words[-1]):
                words = words[:-1]  # a quantity before the amounts
            description = " ".join(words).strip(" .:-")
            if len(description) >= 2:
                rows.append(InvoiceLine(description=description, gross=amounts[-1][0]))
        return rows

    # Validation (plan §8.2 step 5) --------------------------------------------------------------

    def _validate(self, fields: _Fields, context: Context, credit: bool) -> None:
        ico = fields.value("supplier.ico")
        if ico is not None:
            if values.ico_valid(ico):
                fields.trust("supplier.ico")
            else:
                fields.doubt("supplier.ico")
                fields.warnings.append("supplier_ico_check_digit")
        dic, ic_dph = fields.value("supplier.dic"), fields.value("supplier.ic_dph")
        if dic and ic_dph:
            if ic_dph[2:] == dic:
                fields.trust("supplier.dic")
                fields.trust("supplier.ic_dph")
            else:
                fields.doubt("supplier.dic", 0.55)
                fields.doubt("supplier.ic_dph", 0.55)
        net, vat, gross = (fields.value(p) for p in ("totals.net", "totals.vat", "totals.gross"))
        if net is not None and vat is not None and gross is not None:
            if abs(net + vat - gross) <= Decimal("0.01"):
                for path in ("totals.net", "totals.vat", "totals.gross"):
                    fields.trust(path)
            else:
                fields.doubt("totals.net", 0.5)
                fields.doubt("totals.vat", 0.5)
                if fields.found["totals.gross"].confidence < TRUSTED:
                    fields.doubt("totals.gross", 0.5)
                fields.warnings.append("totals_do_not_add_up")
        if gross is not None and (gross < 0) != credit:
            fields.doubt("totals.gross", 0.5)
        issue, delivery, due = (
            fields.value(p)
            for p in ("invoice.issue_date", "invoice.delivery_date", "invoice.due_date")
        )
        if issue is not None and due is not None and due < issue:
            fields.doubt("invoice.due_date", 0.5)
            fields.doubt("invoice.issue_date", 0.55)
            fields.warnings.append("dates_out_of_order")
        if issue is not None and delivery is not None and (delivery - issue).days > 31:
            fields.doubt("invoice.delivery_date", 0.5)
            fields.warnings.append("dates_out_of_order")
        # The number has no check digit: it is trusted when the VS, read elsewhere, repeats
        # its digits; when they disagree both are doubtful, and alone it stays for the user.
        vs, number = fields.value("invoice.variable_symbol"), fields.value("invoice.number")
        if vs and number and vs == "".join(c for c in number if c.isdigit())[-len(vs) :]:
            fields.trust("invoice.variable_symbol")
            fields.trust("invoice.number")
        elif vs and number:
            fields.doubt("invoice.variable_symbol", 0.55)
            fields.doubt("invoice.number", 0.55)
        elif number:
            fields.doubt("invoice.number", 0.55)
