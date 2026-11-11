from datetime import UTC, datetime

import pytest

from riso.intake.domain import (
    MAX_BYTES,
    Document,
    DocumentUploaded,
    MediaType,
    check_upload,
    safe_filename,
    sniff,
)
from riso.shared.errors import ValidationFailed

T0 = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("head", "media_type"),
    [
        (b"%PDF-1.7\n%\xe2\xe3", MediaType.PDF),
        (b"\x00\x00junk before the header %PDF-1.4", MediaType.PDF),
        (b"\xff\xd8\xff\xe0\x00\x10JFIF", MediaType.JPEG),
        (b"\x89PNG\r\n\x1a\n\x00\x00", MediaType.PNG),
        (b"II*\x00\x08\x00", MediaType.TIFF),
        (b"MM\x00*\x00\x00", MediaType.TIFF),
        (b"<?xml version='1.0'?><Invoice/>", MediaType.XML),
        (b"\xef\xbb\xbf\n <Invoice xmlns='urn:x'/>", MediaType.XML),
    ],
)
def test_the_type_comes_from_the_first_bytes(head, media_type):
    assert sniff(head) is media_type


@pytest.mark.parametrize(
    "head",
    [
        b"<!DOCTYPE html><html></html>",
        b"PK\x03\x04 a zip or an xlsx",
        b"GIF89a",
        b"MZ\x90\x00 an executable",
        b"plain text that mentions a pdf",
        b"",
        b" " * 2000 + b"%PDF-1.4",
    ],
)
def test_anything_else_is_not_taken_whatever_its_name(head):
    assert sniff(head) is None


@pytest.mark.parametrize(
    ("size", "media_type", "pages", "code"),
    [
        (0, MediaType.PDF, 1, "file_empty"),
        (MAX_BYTES + 1, MediaType.PDF, 1, "file_too_large"),
        (100, None, None, "file_type"),
        (100, MediaType.PDF, 6, "too_many_pages"),
    ],
)
def test_refusals_carry_their_reason(size, media_type, pages, code):
    with pytest.raises(ValidationFailed) as refused:
        check_upload(size, media_type, pages)
    assert refused.value.errors[0].code == code


def test_the_limits_themselves_are_taken():
    assert check_upload(MAX_BYTES, MediaType.TIFF, 5) is MediaType.TIFF
    assert check_upload(1, MediaType.PDF, None) is MediaType.PDF  # pages unknown: damaged


@pytest.mark.parametrize(
    ("name", "safe"),
    [
        ("faktura.pdf", "faktura.pdf"),
        ("C:\\Users\\x\\Faktúra 12.pdf", "Faktúra 12.pdf"),
        ("../../etc/passwd", "passwd"),
        ("a\x00b\r\nc.jpg", "abc.jpg"),
        ("", "dokument"),
        (None, "dokument"),
        ("...", "dokument"),
        ("x" * 300 + ".pdf", "x" * 200),
    ],
)
def test_file_names_are_made_harmless(name, safe):
    assert safe_filename(name) == safe


def test_an_uploaded_document_records_its_event_and_checks_its_limits():
    document = Document.uploaded(
        "d1",
        "c1",
        sha256="a" * 64,
        filename="sken.jpg",
        media_type=MediaType.JPEG,
        size=1000,
        pages=1,
        storage_key="c1/2026/11/" + "a" * 64 + ".jpg",
        at=T0,
        actor_id="u1",
    )
    assert document.events == [DocumentUploaded("d1", "c1", MediaType.JPEG, T0)]
    assert MediaType.JPEG.extension == "jpg" and MediaType.TIFF.is_image
    assert not MediaType.PDF.is_image
    with pytest.raises(ValidationFailed):
        Document.uploaded(
            "d2",
            "c1",
            sha256="short",
            filename="x.pdf",
            media_type=MediaType.PDF,
            size=10,
            pages=1,
            storage_key="k",
            at=T0,
            actor_id=None,
        )


def test_xml_has_no_pages_and_is_not_an_image():
    assert MediaType.XML.extension == "xml" and not MediaType.XML.is_image


def test_a_pdf_carrying_an_e_invoice_is_taken_whatever_its_pages():
    with pytest.raises(ValidationFailed):
        check_upload(1000, MediaType.PDF, 7)
    assert check_upload(1000, MediaType.PDF, 7, einvoice=True) is MediaType.PDF
