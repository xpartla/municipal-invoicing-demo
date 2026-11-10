from riso.intake.application.enrich import enrich
from riso.intake.domain.extract import Context, FieldExtractor
from riso.intake.domain.layout import Box, DocumentLayout, PageLayout, Word


class Memory:
    def __init__(self, names):
        self.names, self.asked = names, []

    def name_of(self, customer_id, ico):
        self.asked.append((customer_id, ico))
        return self.names.get(ico)


def _extracted(*lines):
    words = []
    for i, text in enumerate(lines):
        x = 100
        for part in text.split():
            words.append(
                Word(part, Box(x, 100 + i * 60, x + 20 * len(part), 130 + i * 60), 0.9, 0, i)
            )
            x += 20 * len(part) + 20
    layout = DocumentLayout((PageLayout(0, 2480, 3508, 300, tuple(words)),), "t", "1")
    return FieldExtractor().extract(layout, document_id="x", context=Context("00305863"))


def test_a_known_supplier_gets_its_name_from_memory():
    memory = Memory({"35763469": "Slovak Telekom, a.s."})
    found = enrich(_extracted("IČO: 35763469"), "c1", memory)
    assert found.document.supplier.name == "Slovak Telekom, a.s."
    assert found.document.ocr_meta.confidence["supplier.name"] == 0.95
    assert "supplier_name_from_memory" in found.warnings
    assert memory.asked == [("c1", "35763469")]


def test_an_ico_failing_its_check_digit_is_not_looked_up():
    memory = Memory({"35763468": "Iná firma"})
    found = enrich(_extracted("IČO: 35763468"), "c1", memory)
    assert found.document.supplier.name is None and memory.asked == []


def test_an_unknown_supplier_or_a_name_read_well_stays_as_read():
    unknown = enrich(_extracted("IČO: 35763469"), "c1", Memory({}))
    assert unknown.document.supplier.name is None
    read = _extracted("Dodávateľ", "Slovak Telekom, a.s.", "IČO: 35763469")
    assert read.document.supplier.name == "Slovak Telekom, a.s."
