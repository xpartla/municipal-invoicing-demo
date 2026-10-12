"""S1, invoice normalisation. Dates and amounts arrive typed from the contract; this stage
derives the gross and the entry amounts, normalises the IČO, reads the handwritten note,
folds all text into diacritics-free words and finds the knowledge base's terms in them:
concepts, functions and credit-note markers."""

import re
from decimal import ROUND_HALF_UP, Decimal

from riso.contracts import InvoiceDocument, InvoiceLine
from riso.engine.models import Hit, NormalisedInvoice, SourcedText
from riso.knowledge import KnowledgeBase
from riso.text import cased_words, words

CENT = Decimal("0.01")
LOW_OCR_CONFIDENCE = 0.6
MONTHS = {
    "januar": 1, "januara": 1, "februar": 2, "februara": 2, "marec": 3, "marca": 3,
    "april": 4, "aprila": 4, "maj": 5, "maja": 5, "jun": 6, "juna": 6, "jul": 7, "jula": 7,
    "august": 8, "augusta": 8, "september": 9, "septembra": 9, "oktober": 10, "oktobra": 10,
    "november": 11, "novembra": 11, "december": 12, "decembra": 12,
}  # fmt: skip


def normalise(document: InvoiceDocument, knowledge: KnowledgeBase) -> NormalisedInvoice:
    issues: list[str] = []
    texts = _texts(document)
    concepts, functions, credit_note_markers = [], [], []
    for text in texts:
        concepts += [
            Hit(meaning=meaning, term=term.text, source=text.source)
            for term, meaning in knowledge.concept_terms.search(text.words)
        ]
        functions += [
            Hit(meaning=meaning, term=term.text, source=text.source)
            for term, meaning in knowledge.function_terms.search(text.words)
        ]
        functions += [
            Hit(meaning=knowledge.abbreviations[word], term=word, source=text.source)
            for word in dict.fromkeys(text.cased_words)
            if word in knowledge.abbreviations
        ]
        credit_note_markers += knowledge.credit_note_terms.search(text.words)

    line_grosses = [_line_gross(line, document.supplier.vat_payer) for line in document.lines]
    gross = _gross(document, line_grosses, issues)
    written = document.handwritten.number
    number = int(written) if written is not None and written.strip().isdigit() else None
    if written is not None and number is None:
        issues.append(f"the handwritten number {written!r} is not a number")

    return NormalisedInvoice(
        document=document,
        supplier_ico=_ico(document.supplier.ico, "supplier", issues),
        customer_ico=_ico(document.customer.ico, "customer", issues),
        gross=gross,
        line_amounts=_line_amounts(line_grosses, gross),
        vat_payer=(
            document.supplier.vat_payer
            if document.supplier.vat_payer is not None
            else (True if document.supplier.ic_dph else None)
        ),
        booking_date=document.handwritten.date,
        handwritten_number=number,
        service_period=_service_period(texts, document),
        is_credit_note=(
            document.invoice.document_type == "credit_note"
            or bool(credit_note_markers)
            or (gross is not None and gross < 0)
        ),
        texts=texts,
        concepts=tuple(concepts),
        functions=tuple(functions),
        issues=tuple(issues),
        low_confidence=tuple(
            path
            for path, score in document.ocr_meta.confidence.items()
            if score < LOW_OCR_CONFIDENCE
        ),
    )


def ico_is_valid(ico: str) -> bool:
    """The check digit of an 8-digit IČO: weights 8 to 2, then (11 - sum mod 11) mod 10."""
    digits = [int(c) for c in ico]
    total = sum(weight * digit for weight, digit in zip(range(8, 1, -1), digits[:7], strict=True))
    return (11 - total % 11) % 10 == digits[7]


def cents(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def _texts(document: InvoiceDocument) -> tuple[SourcedText, ...]:
    pieces = [
        (f"lines[{i}].description", line.description) for i, line in enumerate(document.lines)
    ]
    pieces += [(f"free_text[{i}]", text) for i, text in enumerate(document.free_text)]
    if document.supplier.name:
        pieces.append(("supplier.name", document.supplier.name))
    return tuple(
        SourcedText(source=source, words=words(text), cased_words=cased_words(text))
        for source, text in pieces
    )


def _ico(raw: str | None, role: str, issues: list[str]) -> str | None:
    if raw is None:
        if role == "supplier":
            issues.append("the supplier IČO was not read")
        return None
    digits = re.sub(r"\D", "", raw)
    if not 6 <= len(digits) <= 8 or not ico_is_valid(digits.zfill(8)):
        issues.append(f"the {role} IČO {raw!r} fails its check digit")
        return None
    return digits.zfill(8)


def _line_gross(line: InvoiceLine, vat_payer: bool | None) -> Decimal | None:
    if line.gross is not None:
        return line.gross
    if line.net is not None and line.vat is not None:
        return line.net + line.vat
    if line.net is not None and line.vat_rate is not None:
        return line.net * (1 + line.vat_rate / 100)
    if vat_payer is False:
        if line.net is not None:
            return line.net
        if line.quantity is not None and line.unit_price is not None:
            return line.quantity * line.unit_price
    return None


def _gross(
    document: InvoiceDocument, line_grosses: list[Decimal | None], issues: list[str]
) -> Decimal | None:
    totals = document.totals
    entries = (
        sum(line_grosses, Decimal(0))
        if line_grosses and all(g is not None for g in line_grosses)
        else None
    )
    if totals.gross is not None:
        if entries is not None and abs(cents(entries) - totals.gross) > CENT:
            issues.append(
                f"the entries add up to {cents(entries)}, the invoice total is {totals.gross}"
            )
        return cents(totals.gross)
    if totals.net is not None and totals.vat is not None:
        return cents(totals.net + totals.vat)
    if entries is not None:
        issues.append("the invoice shows no total; the gross is the sum of its entries")
        return cents(entries)
    issues.append("the invoice shows no total")
    return None


def _line_amounts(
    line_grosses: list[Decimal | None], gross: Decimal | None
) -> tuple[Decimal | None, ...]:
    """Each entry's gross in cents, adding to the invoice gross; the rounding difference goes
    to the largest entry. None for all when the entries cannot be made to add up."""
    unknown = tuple(None for _ in line_grosses)
    if gross is None or not line_grosses or any(g is None for g in line_grosses):
        return unknown
    amounts = [cents(g) for g in line_grosses if g is not None]
    difference = gross - sum(amounts, Decimal(0))
    if abs(difference) > CENT * len(amounts):
        return unknown
    if difference:
        largest = max(range(len(amounts)), key=lambda i: abs(amounts[i]))
        amounts[largest] += difference
    return tuple(amounts)


def _service_period(
    texts: tuple[SourcedText, ...], document: InvoiceDocument
) -> tuple[int, int] | None:
    """The month the invoice is for: a month named in its text ('za mesiac apríl 2026'),
    else the delivery date's."""
    dates = (document.invoice.issue_date, document.handwritten.date, document.invoice.delivery_date)
    year = next((d.year for d in dates if d is not None), None)
    for text in texts:
        for i, word in enumerate(text.words):
            if word in MONTHS:
                after = text.words[i + 1] if i + 1 < len(text.words) else ""
                named_year = int(after) if re.fullmatch(r"20\d\d", after) else year
                if named_year is not None:
                    return named_year, MONTHS[word]
    delivery = document.invoice.delivery_date
    return (delivery.year, delivery.month) if delivery else None
