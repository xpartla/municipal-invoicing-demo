"""XML attached to a PDF (plan §8.4, "XML embedded in a PDF"): an ISDOC PDF carries its
ISDOC file as an embedded file, Factur-X its CII. The PDF is opened by pypdfium2 only
(plan §12). At most `MAX_ATTACHMENTS` are looked at, each at most `MAX_XML_BYTES`, in the
PDF's order; what is not XML (an image, a spreadsheet) is skipped by its first bytes.
"""

from dataclasses import dataclass

from riso.intake.domain.document import starts_as_xml
from riso.intake.infrastructure.xml.safe import MAX_XML_BYTES

MAX_ATTACHMENTS = 20


@dataclass(frozen=True, slots=True)
class Attachment:
    name: str
    data: bytes


def xml_attachments(pdf_data: bytes) -> list[Attachment]:
    """The PDF's embedded files that start as XML; empty for a PDF without any or one PDFium
    cannot open (the PDF path reports that)."""
    import pypdfium2

    try:
        pdf = pypdfium2.PdfDocument(pdf_data)
    except pypdfium2.PdfiumError:
        return []
    try:
        found: list[Attachment] = []
        for i in range(min(pdf.count_attachments(), MAX_ATTACHMENTS)):
            attachment = pdf.get_attachment(i)
            try:
                data = bytes(attachment.get_data())
            except pypdfium2.PdfiumError:
                continue
            if len(data) <= MAX_XML_BYTES and starts_as_xml(data):
                found.append(Attachment(str(attachment.get_name()), data))
        return found
    finally:
        pdf.close()
