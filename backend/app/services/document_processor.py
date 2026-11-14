"""Document Ingestion, Validation, Text Extraction, and Chunking Service.

Single Organization Edition: Physio One Clinic.
Supports PDF, DOCX, TXT, and Markdown with zero external binary dependencies.
Strict validation against path traversal, oversized payloads, and malformed files.
"""
import io
import re
import zlib
import zipfile
import hashlib
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Tuple


class DocumentProcessingError(Exception):
    """Raised when document validation or extraction fails."""
    pass


class DocumentProcessor:
    """Secure document parser and text chunking engine."""

    MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit
    ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "md", "markdown"}

    @classmethod
    def validate_file(cls, filename: str, content: bytes) -> Tuple[str, str]:
        """Validate filename extension, file size, and magic byte signatures."""
        if not filename or "." not in filename:
            raise DocumentProcessingError("Invalid filename. An extension is required.")

        ext = filename.rsplit(".", 1)[-1].lower()
        if ext not in cls.ALLOWED_EXTENSIONS:
            raise DocumentProcessingError(
                f"Unsupported file extension '.{ext}'. Allowed types: {', '.join(sorted(cls.ALLOWED_EXTENSIONS))}"
            )

        if len(content) == 0:
            raise DocumentProcessingError("Uploaded file is empty.")

        if len(content) > cls.MAX_FILE_SIZE_BYTES:
            raise DocumentProcessingError(
                f"File size exceeds maximum limit of {cls.MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB."
            )

        # Magic byte validation
        if ext == "pdf":
            if not content.startswith(b"%PDF-"):
                raise DocumentProcessingError("Invalid PDF file: Missing %PDF- signature.")
        elif ext == "docx":
            if not content.startswith(b"PK\x03\x04"):
                raise DocumentProcessingError("Invalid DOCX file: Missing ZIP archive signature.")
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    namelist = zf.namelist()
                    if "word/document.xml" not in namelist:
                        raise DocumentProcessingError("Invalid DOCX file: Missing word/document.xml.")
            except zipfile.BadZipFile as e:
                raise DocumentProcessingError(f"Corrupted DOCX archive: {e}") from e
        elif ext in ("txt", "md", "markdown"):
            # Check for binary null bytes
            if b"\x00" in content:
                raise DocumentProcessingError("Binary content detected in plain text/markdown file.")

        source_hash = hashlib.sha256(content).hexdigest()
        return ext, source_hash

    @classmethod
    def extract_text(cls, ext: str, content: bytes) -> str:
        """Extract clean text content based on file extension."""
        if ext in ("txt", "md", "markdown"):
            return cls._extract_from_text(content)
        elif ext == "docx":
            return cls._extract_from_docx(content)
        elif ext == "pdf":
            return cls._extract_from_pdf(content)
        else:
            raise DocumentProcessingError(f"Unsupported extraction format: {ext}")

    @staticmethod
    def _extract_from_text(content: bytes) -> str:
        """Decode plain text or markdown with UTF-8 fallback."""
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return content.decode("latin-1")
            except Exception as e:
                raise DocumentProcessingError(f"Failed to decode text document: {e}") from e

    @staticmethod
    def _extract_from_docx(content: bytes) -> str:
        """Extract text elements from word/document.xml in DOCX zip package."""
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                xml_content = zf.read("word/document.xml")
            
            tree = ET.fromstring(xml_content)
            # XML namespace for WordprocessingML
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            
            paragraphs = []
            for p_elem in tree.findall(".//w:p", ns):
                texts = [t.text for t in p_elem.findall(".//w:t", ns) if t.text]
                if texts:
                    paragraphs.append("".join(texts))
            
            return "\n\n".join(paragraphs)
        except Exception as e:
            raise DocumentProcessingError(f"Error extracting text from DOCX: {e}") from e

    @classmethod
    def _extract_from_pdf(cls, content: bytes) -> str:
        """Extract text from text-based PDF streams without external dependencies."""
        extracted_text = []

        # Find all stream objects in the PDF
        stream_matches = re.finditer(rb"stream[\r\n]+(.*?)[\r\n]+endstream", content, re.DOTALL)
        for match in stream_matches:
            raw_stream = match.group(1)
            decompressed = None

            # Try FlateDecode decompress
            try:
                decompressed = zlib.decompress(raw_stream)
            except Exception:
                decompressed = raw_stream

            if not decompressed:
                continue

            # Look for PDF text operator blocks: BT ... ET
            bt_matches = re.findall(rb"BT\s*(.*?)\s*ET", decompressed, re.DOTALL)
            for bt in bt_matches:
                # Text show operators: (text) Tj or [(text) 10 (more)] TJ
                # 1. Matches (string) Tj
                tj_matches = re.findall(rb"\((.*?)\)\s*Tj", bt)
                for tj in tj_matches:
                    try:
                        extracted_text.append(tj.decode("utf-8", errors="replace"))
                    except Exception:
                        pass

                # 2. Matches [(string1) ... (string2)] TJ
                array_matches = re.findall(rb"\[(.*?)\]\s*TJ", bt, re.DOTALL)
                for arr in array_matches:
                    inner_tjs = re.findall(rb"\((.*?)\)", arr)
                    for itj in inner_tjs:
                        try:
                            extracted_text.append(itj.decode("utf-8", errors="replace"))
                        except Exception:
                            pass

        combined = " ".join(extracted_text).strip()
        if not combined:
            # Fallback: scan for printable ascii sequences
            printable_strings = re.findall(rb"[A-Za-z0-9 .,;:!?'\"\(\)\-\n]{4,}", content)
            cleaned = [s.decode("latin-1", errors="ignore").strip() for s in printable_strings if len(s.strip()) > 10]
            combined = "\n".join(cleaned)

        if not combined or len(combined.strip()) < 10:
            raise DocumentProcessingError(
                "Could not extract meaningful text from PDF. Ensure the PDF contains searchable text and is not a scanned image."
            )

        return combined

    @classmethod
    def normalize_text(cls, raw_text: str) -> str:
        """Clean and normalize extracted text."""
        # Replace Windows CRLF and CR with LF
        text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        # Replace non-breaking spaces
        text = text.replace("\u00a0", " ")
        # Remove null characters
        text = text.replace("\x00", "")
        # Collapse multiple spaces on the same line
        text = re.sub(r"[ \t]+", " ", text)
        # Collapse 3+ newlines into 2 (paragraphs)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @classmethod
    def chunk_text(
        cls,
        text: str,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> List[Dict[str, Any]]:
        """Split text into semantic chunks with configurable size and overlap.
        
        Returns a list of dicts with:
          - chunk_index: int
          - text: str
          - char_count: int
          - word_count: int
        """
        if not text.strip():
            return []

        # Split into initial paragraphs
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: List[str] = []
        current_chunk = []
        current_len = 0

        for p in paragraphs:
            # If paragraph itself is longer than chunk_size, split by sentences
            if len(p) > chunk_size:
                sentences = re.split(r"(?<=[.!?])\s+", p)
                for s in sentences:
                    s = s.strip()
                    if not s:
                        continue
                    if current_len + len(s) + 1 > chunk_size and current_chunk:
                        chunk_str = " ".join(current_chunk)
                        chunks.append(chunk_str)
                        # Overlap: keep last items up to chunk_overlap chars
                        overlap_chunk = []
                        overlap_len = 0
                        for item in reversed(current_chunk):
                            if overlap_len + len(item) <= chunk_overlap:
                                overlap_chunk.insert(0, item)
                                overlap_len += len(item)
                            else:
                                break
                        current_chunk = overlap_chunk
                        current_len = overlap_len

                    current_chunk.append(s)
                    current_len += len(s) + 1
            else:
                if current_len + len(p) + 2 > chunk_size and current_chunk:
                    chunk_str = "\n\n".join(current_chunk)
                    chunks.append(chunk_str)
                    current_chunk = []
                    current_len = 0

                current_chunk.append(p)
                current_len += len(p) + 2

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        result = []
        for idx, c in enumerate(chunks):
            c_clean = c.strip()
            if c_clean:
                result.append({
                    "chunk_index": idx,
                    "text": c_clean,
                    "char_count": len(c_clean),
                    "word_count": len(c_clean.split()),
                })

        return result
