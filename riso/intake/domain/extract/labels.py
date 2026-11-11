"""The labels values are anchored on (plan §8.2 step 4), with the Slovak variants invoices
print and OCR's way of losing diacritics. Patterns match folded text: lower case, without
diacritics, so `Dátum zdaniteľného plnenia`, `DATUM ZDANITELNEHO PLNENIA` and an OCR'd
`Datum zdanitelneho plnenia` are one label.

Strength orders labels of one field: a `strong` label names the field unmistakably
(`Celkom k úhrade`), a `weak` one may also head something else (`Spolu`, `Celkom`).
"""

import re
from dataclasses import dataclass
from typing import Literal

Strength = Literal["strong", "weak"]


@dataclass(frozen=True, slots=True)
class Label:
    field: str
    pattern: re.Pattern[str]
    strength: Strength = "strong"


def _label(field: str, pattern: str, strength: Strength = "strong") -> Label:
    return Label(field, re.compile(pattern), strength)


LABELS: tuple[Label, ...] = (
    # The parties' identifiers.
    _label("ico", r"(?<![a-z0-9])[i1l|]\s?c\s?o\b|\bic\b(?!\s?dph)|identifikacne cislo"),
    _label("dic", r"\bd\s?i\s?c\b"),
    _label("ic_dph", r"\bic\s?dph\b|\bic pre dph\b|\bic dph\b"),
    _label("iban", r"\biban\b|cislo uctu|bankove spojenie|c\. uctu|\bucet\b"),
    _label("vs", r"variabiln\w* symbol|\bvar\.?\s?symbol|\bv\.?\s?s\.?(?=\s|:|$)|\bvs\b"),
    # Dates.
    _label(
        "issue_date",
        r"datum vystavenia|vystaven\w* dna|datum vyhotovenia|\bvystavene\b|\bvystavena\b",
    ),
    _label(
        "delivery_date",
        r"datum zdanitelneho plnenia|zdanitelne plnenie|\bdzp\b|datum dodania"
        r"|dodanie (?:tovaru|sluzby)",
    ),
    _label("due_date", r"datum splatnosti|\bsplatnost\b|splatn\w* dna|\bsplatna\b"),
    # Totals.
    _label(
        "gross",
        r"celkom k uhrade|spolu na uhradu|suma na uhradu|\bna uhradu\b|\bk uhrade\b"
        r"|celkova fakturovana suma|celkova suma|zostava na uhradu",
    ),
    _label("gross", r"^\s*(?:celkom|spolu|suma)\b", "weak"),
    _label("net", r"zaklad dph|spolu bez dph|zaklad dane|\bbez dph\b"),
    _label("vat", r"(?<![a-z] )(?<!ic )\bvyska dph\b|^\s*dph\b(?!\s?%)"),
    # The document.
    _label(
        "number",
        r"(?<!k )(?:faktur[a-z]*|dobropis|doklad)(?:\s*[-–—]\s*danovy doklad)?\s*(?:[c¢]\.|cislo)"
        r"|cislo faktury|cislo dokladu|faktura\s+(?=\d)|^\s*[c¢]\.\s",
    ),
)

SUPPLIER_HEADINGS = re.compile(r"\bdodavatel\b|\bpredavajuci\b|\bfakturujuci\b")
CUSTOMER_HEADINGS = re.compile(
    r"\bodberatel\b|\bprijemca\b|\badresat\b|\bkupujuci\b|\bobjednavatel\b"
)
CREDIT_NOTE = re.compile(r"\bdobropis\b|opravny danovy doklad|opravna faktura")
NOT_VAT_PAYER = re.compile(
    r"nie som platca dph|nie sme platcami dph|neplatca dph|nie je platca dph"
)
LINES_HEADER = re.compile(
    r"\bpopis\b|\bnazov\b|oznacenie dodavky|\bpolozka\b|\bpolozky\b|\bmnozstvo\b|\bmj\b|cena za mj"
    r"|jedn\.?\s?cena|\bbez dph\b|\bdph\b|\bspolu\b|\bcelkom\b"
)
LINES_END = re.compile(
    r"sumarizacia|rekapitulacia|sadzba dph|celkom k uhrade|spolu na uhradu|na uhradu|\bk uhrade\b"
    r"|celkova fakturovana suma|zaklad dph"
)


def labels_of(field: str) -> tuple[Label, ...]:
    return tuple(label for label in LABELS if label.field == field)
