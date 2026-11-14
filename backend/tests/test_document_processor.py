"""Tests for Document Processor: Validation, Text Extraction, Normalization, and Chunking."""
import io
import zipfile
import pytest

from app.services.document_processor import DocumentProcessor, DocumentProcessingError


def test_validate_allowed_extensions():
    # Valid TXT
    ext, hash_val = DocumentProcessor.validate_file("notes.txt", b"Hello clinic world")
    assert ext == "txt"
    assert len(hash_val) == 64

    # Valid Markdown
    ext, hash_val = DocumentProcessor.validate_file("guide.md", b"# Clinic Guide\nDetails here")
    assert ext == "md"

    # Unsupported extension
    with pytest.raises(DocumentProcessingError, match="Unsupported file extension"):
        DocumentProcessor.validate_file("script.exe", b"binary content")

    # Empty file
    with pytest.raises(DocumentProcessingError, match="Uploaded file is empty"):
        DocumentProcessor.validate_file("empty.txt", b"")

    # Oversized file
    big_content = b"x" * (11 * 1024 * 1024)
    with pytest.raises(DocumentProcessingError, match="File size exceeds"):
        DocumentProcessor.validate_file("large.txt", big_content)


def test_docx_magic_bytes_and_extraction():
    # Invalid DOCX magic bytes
    with pytest.raises(DocumentProcessingError, match="Missing ZIP archive signature"):
        DocumentProcessor.validate_file("report.docx", b"Not a real docx file")

    # Create a real in-memory DOCX zip package
    docx_buf = io.BytesIO()
    with zipfile.ZipFile(docx_buf, "w") as zf:
        xml_content = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:body>
                <w:p><w:r><w:t>Physio One Clinic Rehabilitation Protocol</w:t></w:r></w:p>
                <w:p><w:r><w:t>Appointments are 45 minutes long.</w:t></w:r></w:p>
            </w:body>
        </w:document>
        """
        zf.writestr("word/document.xml", xml_content.encode("utf-8"))

    valid_docx_bytes = docx_buf.getvalue()
    ext, h = DocumentProcessor.validate_file("rehab.docx", valid_docx_bytes)
    assert ext == "docx"

    text = DocumentProcessor.extract_text("docx", valid_docx_bytes)
    assert "Physio One Clinic Rehabilitation Protocol" in text
    assert "Appointments are 45 minutes long." in text


def test_pdf_magic_bytes():
    # Non-PDF header
    with pytest.raises(DocumentProcessingError, match="Missing %PDF- signature"):
        DocumentProcessor.validate_file("fake.pdf", b"Not a pdf")

    # Text extraction from a minimal text-based PDF
    minimal_pdf = b"%PDF-1.4\n1 0 obj\n<< /Length 40 >>\nstream\nBT /F1 12 Tf (Physio One Guidelines) Tj ET\nendstream\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
    ext, h = DocumentProcessor.validate_file("sample.pdf", minimal_pdf)
    assert ext == "pdf"
    text = DocumentProcessor.extract_text("pdf", minimal_pdf)
    assert "Physio One Guidelines" in text


def test_normalize_and_chunk():
    raw_text = "Physio One Clinic.\r\n\r\nOperating Hours:\r\nMonday to Saturday 9 AM to 8 PM.\r\n\r\n\r\n\r\nClosed on Sundays."
    normalized = DocumentProcessor.normalize_text(raw_text)
    assert "\r" not in normalized
    assert "\n\n\n" not in normalized

    chunks = DocumentProcessor.chunk_text(normalized, chunk_size=50, chunk_overlap=10)
    assert len(chunks) >= 2
    for c in chunks:
        assert "chunk_index" in c
        assert "text" in c
        assert len(c["text"]) > 0
        assert c["word_count"] > 0
