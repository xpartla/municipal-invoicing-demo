import hashlib

import pytest
from PIL import Image

from riso.intake.application.ports import PageImage
from riso.intake.domain.layout import Box, DocumentLayout, PageLayout, ReadingFailed, Word
from riso.intake.infrastructure import tesseract
from riso.intake.infrastructure.recorded import RecordedReader, recording_name

TSV = "\t".join(
    [
        "level",
        "page_num",
        "block_num",
        "par_num",
        "line_num",
        "word_num",
        "left",
        "top",
        "width",
        "height",
        "conf",
        "text",
    ]
)
ROWS = [
    "1\t1\t0\t0\t0\t0\t0\t0\t2480\t3508\t-1\t",
    "2\t1\t1\t0\t0\t0\t100\t100\t800\t80\t-1\t",
    "5\t1\t1\t1\t1\t1\t100\t100\t180\t40\t96.5\tFaktúra",
    "5\t1\t1\t1\t1\t2\t300\t100\t40\t40\t91.0\tč.",
    "5\t1\t1\t1\t1\t3\t360\t100\t240\t40\t88.25\t2026/0012",
    "5\t1\t1\t1\t2\t1\t100\t160\t90\t40\t71.0\tIČO:",
    "5\t1\t1\t1\t2\t2\t200\t160\t200\t40\t64.0\t35823551",
    "5\t1\t2\t1\t1\t1\t1500\t100\t300\t40\t95.0\t   ",
    "5\t1\t2\t1\t1\t2\t1500\t100\t300\t40\t95.0\tDodávateľ",
]


def test_tesseract_tsv_becomes_words_grouped_in_lines():
    layout = tesseract.parse_tsv(
        "\n".join([TSV, *ROWS]) + "\n", index=0, width=2480, height=3508, dpi=300
    )
    assert [w.text for w in layout.words] == [
        "Faktúra",
        "č.",
        "2026/0012",
        "IČO:",
        "35823551",
        "Dodávateľ",
    ]
    assert layout.words[0] == Word("Faktúra", Box(100, 100, 280, 140), 0.965, 1, 0)
    assert [line.text for line in layout.lines()] == [
        "Faktúra č. 2026/0012",
        "IČO: 35823551",
        "Dodávateľ",
    ]
    assert [line.block for line in layout.lines()] == [1, 1, 2]
    line = layout.lines()[1]
    assert line.box == Box(100, 160, 400, 200) and line.confidence == pytest.approx(0.675)
    assert layout.text.splitlines()[0] == "Faktúra č. 2026/0012"


def test_a_layout_round_trips_through_json():
    page = PageLayout(
        index=1,
        width=100,
        height=200,
        dpi=150,
        words=(Word("a", Box(1, 2, 3, 4), 0.5, 0, 0), Word("b", Box(5, 6, 7, 8), 1.0, 1, 1)),
        source="text_layer",
    )
    document = DocumentLayout(pages=(page,), engine="tesseract", engine_version="5.5.3")
    assert DocumentLayout.from_json(document.to_json()) == document


def test_boxes():
    a, b = Box(0, 0, 10, 10), Box(5, 5, 20, 20)
    assert a.union(b) == Box(0, 0, 20, 20)
    assert a.intersection(b) == Box(5, 5, 10, 10)
    assert a.intersection(Box(10, 10, 12, 12)) is None
    assert Box(0, 0, 20, 20).contains(a) and not a.contains(b)
    assert a.grown(2) == Box(-2, -2, 12, 12) and a.scaled(0.5) == Box(0, 0, 5, 5)
    assert a.area == 100 and a.centre == (5, 5)
    assert Box.around([]) is None and Box.around([a, b]) == Box(0, 0, 20, 20)


def _page(sha: str = "a" * 64, index: int = 0) -> PageImage:
    return PageImage(Image.new("L", (10, 10)), index=index, dpi=300, document_sha256=sha)


def test_the_recorded_reader_replays_what_was_recorded(tmp_path):
    reader = RecordedReader(tmp_path)
    layout = PageLayout(0, 10, 10, 300, (Word("Spolu", Box(1, 1, 5, 3), 0.9, 0, 0),))
    reader.record(_page(), layout)
    assert (tmp_path / recording_name("a" * 64, 0)).is_file()
    assert reader.read(_page()) == layout
    with pytest.raises(ReadingFailed) as missing:
        reader.read(_page(index=1))
    assert missing.value.reason == "no_recording"
    assert reader.version == "unknown"
    (tmp_path / "engine.json").write_text('{"engine": "tesseract", "version": "5.5.3"}')
    assert reader.version == "tesseract 5.5.3"


def test_the_setup_fetches_the_pinned_models_and_refuses_another_file(tmp_path, monkeypatch):
    blobs = {"slk": b"slovak model", "eng": b"english model"}
    pinned = tuple(
        tesseract.Model(
            m.language, hashlib.sha256(blobs[m.language]).hexdigest(), len(blobs[m.language])
        )
        for m in tesseract.MODELS
    )
    monkeypatch.setattr(tesseract, "MODELS", pinned)
    fetched: list[str] = []

    def fetch(url: str) -> bytes:
        fetched.append(url)
        return blobs[url.rsplit("/", 1)[1].split(".")[0]]

    assert tesseract.setup_models(tmp_path, fetch) == [("slk", "downloaded"), ("eng", "downloaded")]
    assert all("tessdata_best/4.1.0/" in url for url in fetched)
    assert tesseract.models_ready(tmp_path)
    assert tesseract.setup_models(tmp_path, fetch) == [("slk", "present"), ("eng", "present")]
    (tmp_path / "eng.traineddata").write_bytes(b"tampered")
    assert tesseract.setup_models(tmp_path, fetch)[1] == ("eng", "downloaded")

    with pytest.raises(RuntimeError, match="slk model's SHA-256"):
        tesseract.setup_models(tmp_path / "other", lambda url: b"something else")
    assert not (tmp_path / "other" / "slk.traineddata").exists()


def test_without_the_models_the_reader_says_so(tmp_path):
    reader = tesseract.TesseractReader(tmp_path, in_process=True)
    with pytest.raises(ReadingFailed) as missing:
        reader.read(_page())
    assert missing.value.reason == "no_models"
