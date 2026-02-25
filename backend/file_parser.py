"""File Parser for Local LLM Chat Interface.

This module extracts text content from uploaded files.
It implements parsers for each supported format: PDF, Markdown, JSON, CSV,
and plain text. It validates file signatures (magic numbers) to confirm
actual file type matches extension and implements timeout handling for large files.

Design follows Requirements 4.1, 4.3, 4.8.
"""

import csv
import json
import logging
import struct
import time
import zipfile
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, Union

logger = logging.getLogger(__name__)


# =============================================================================
# File Signature (Magic Number) Definitions
# =============================================================================

# Magic numbers for common file types
# Format: (signature_bytes, offset, file_type)
FILE_SIGNATURES: Dict[str, Tuple[bytes, int]] = {
    # PDF: %PDF
    "pdf": (b"%PDF", 0),
    # ZIP (for .docx, .xlsx, .pptx, .odt, .ods, .odp)
    "zip": (b"PK", 0),
    # JSON
    "json": (b"{", 0),
    # CSV (starts with text or BOM)
    "csv": (b"\xef\xbb\xbf", 0),  # UTF-8 BOM
    # Plain text (no specific signature, detected by content)
    "txt": (b"", -1),  # No signature, detected by content
    # Markdown
    "md": (b"", -1),  # No signature, detected by content
}

# Additional signatures for specific formats
ZIP_BASED_FORMATS = {
    "docx": b"PK\x03\x04",
    "xlsx": b"PK\x03\x04",
    "pptx": b"PK\x03\x04",
    "odt": b"PK\x03\x04",
    "ods": b"PK\x03\x04",
    "odp": b"PK\x03\x04",
}


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass
class FileParserConfig:
    """Configuration for the file parser."""
    # Maximum file size in bytes (default: 50 MB)
    max_file_size: int = 50 * 1024 * 1024
    # Timeout in seconds for parsing (default: 5 seconds for files under 10MB)
    timeout_seconds: float = 5.0
    # Timeout for large files (default: 30 seconds)
    large_file_timeout_seconds: float = 30.0
    # Enable magic number validation
    validate_signatures: bool = True
    # Supported file extensions
    supported_extensions: Tuple[str, ...] = (
        ".txt", ".md", ".json", ".csv", ".pdf"
    )


@dataclass
class ParseResult:
    """Result of a file parsing operation."""
    success: bool
    content: str
    file_type: str
    file_extension: str
    extracted_text_length: int
    error_message: Optional[str] = None
    parsing_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "content": self.content,
            "file_type": self.file_type,
            "file_extension": self.file_extension,
            "extracted_text_length": self.extracted_text_length,
            "error_message": self.error_message,
            "parsing_time_ms": self.parsing_time_ms,
        }


# =============================================================================
# File Parser Class
# =============================================================================

class FileParser:
    """
    Parses files and extracts text content.

    Supports multiple file formats:
    - .txt: Plain text files
    - .md: Markdown files
    - .json: JSON files
    - .csv: CSV files
    - .pdf: PDF files (using pdfplumber if available)

    Features:
    - File signature validation (magic numbers)
    - Timeout handling for large files
    - Graceful error handling with descriptive messages
    """

    def __init__(self, config: Optional[FileParserConfig] = None):
        """Initialize the file parser.

        Args:
            config: Optional configuration for the parser
        """
        self.config = config or FileParserConfig()
        self._pdfplumber_available = self._check_pdfplumber()

    def _check_pdfplumber(self) -> bool:
        """Check if pdfplumber is available for PDF parsing."""
        try:
            import pdfplumber
            return True
        except ImportError:
            logger.warning(
                "pdfplumber not installed. PDF parsing will return empty content. "
                "Install with: pip install pdfplumber"
            )
            return False

    def parse_file(
        self,
        file_path: Union[str, Path],
        timeout_seconds: Optional[float] = None,
    ) -> ParseResult:
        """Parse a file and extract its text content.

        Args:
            file_path: Path to the file to parse
            timeout_seconds: Optional timeout override

        Returns:
            ParseResult with extracted content
        """
        start_time = time.time()
        file_path = Path(file_path)

        try:
            # Validate file exists
            if not file_path.exists():
                return ParseResult(
                    success=False,
                    content="",
                    file_type="unknown",
                    file_extension=file_path.suffix.lower(),
                    extracted_text_length=0,
                    error_message=f"File not found: {file_path}",
                )

            # Validate file size
            file_size = file_path.stat().st_size
            if file_size > self.config.max_file_size:
                return ParseResult(
                    success=False,
                    content="",
                    file_type="unknown",
                    file_extension=file_path.suffix.lower(),
                    extracted_text_length=0,
                    error_message=(
                        f"File size ({file_size} bytes) exceeds maximum "
                        f"({self.config.max_file_size} bytes)"
                    ),
                )

            # Determine timeout based on file size
            if timeout_seconds is None:
                timeout_seconds = (
                    self.config.large_file_timeout_seconds
                    if file_size > 10 * 1024 * 1024
                    else self.config.timeout_seconds
                )

            # Read file content
            with open(file_path, "rb") as f:
                content_bytes = f.read()

            # Validate file signature
            if self.config.validate_signatures:
                signature_valid, detected_type = self._validate_signature(
                    content_bytes, file_path.suffix.lower()
                )
                if not signature_valid:
                    return ParseResult(
                        success=False,
                        content="",
                        file_type=detected_type or "unknown",
                        file_extension=file_path.suffix.lower(),
                        extracted_text_length=0,
                        error_message=(
                            f"File signature mismatch. Expected {file_path.suffix}, "
                            f"detected type: {detected_type or 'unknown'}"
                        ),
                    )

            # Parse based on file extension
            content = self._parse_content(
                content_bytes, file_path.suffix.lower(), timeout_seconds
            )

            parsing_time_ms = int((time.time() - start_time) * 1000)

            return ParseResult(
                success=True,
                content=content,
                file_type=self._get_file_type(file_path.suffix.lower()),
                file_extension=file_path.suffix.lower(),
                extracted_text_length=len(content),
                parsing_time_ms=parsing_time_ms,
            )

        except TimeoutError:
            parsing_time_ms = int((time.time() - start_time) * 1000)
            return ParseResult(
                success=False,
                content="",
                file_type="unknown",
                file_extension=file_path.suffix.lower(),
                extracted_text_length=0,
                error_message=f"Parsing timed out after {timeout_seconds} seconds",
                parsing_time_ms=parsing_time_ms,
            )

        except Exception as e:
            parsing_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Failed to parse file {file_path}: {e}")
            return ParseResult(
                success=False,
                content="",
                file_type="unknown",
                file_extension=file_path.suffix.lower(),
                extracted_text_length=0,
                error_message=str(e),
                parsing_time_ms=parsing_time_ms,
            )

    def parse_content(
        self,
        content: bytes,
        filename: str,
        timeout_seconds: Optional[float] = None,
    ) -> ParseResult:
        """Parse file content directly (from upload).

        Args:
            content: Raw file content
            filename: Original filename with extension
            timeout_seconds: Optional timeout override

        Returns:
            ParseResult with extracted content
        """
        start_time = time.time()
        file_extension = Path(filename).suffix.lower()

        try:
            # Validate file size
            if len(content) > self.config.max_file_size:
                return ParseResult(
                    success=False,
                    content="",
                    file_type="unknown",
                    file_extension=file_extension,
                    extracted_text_length=0,
                    error_message=(
                        f"File size ({len(content)} bytes) exceeds maximum "
                        f"({self.config.max_file_size} bytes)"
                    ),
                )

            # Determine timeout based on file size
            if timeout_seconds is None:
                timeout_seconds = (
                    self.config.large_file_timeout_seconds
                    if len(content) > 10 * 1024 * 1024
                    else self.config.timeout_seconds
                )

            # Validate file signature
            if self.config.validate_signatures:
                signature_valid, detected_type = self._validate_signature(
                    content, file_extension
                )
                if not signature_valid:
                    return ParseResult(
                        success=False,
                        content="",
                        file_type=detected_type or "unknown",
                        file_extension=file_extension,
                        extracted_text_length=0,
                        error_message=(
                            f"File signature mismatch. Expected {file_extension}, "
                            f"detected type: {detected_type or 'unknown'}"
                        ),
                    )

            # Parse based on file extension
            content_str = self._parse_content(
                content, file_extension, timeout_seconds
            )

            parsing_time_ms = int((time.time() - start_time) * 1000)

            return ParseResult(
                success=True,
                content=content_str,
                file_type=self._get_file_type(file_extension),
                file_extension=file_extension,
                extracted_text_length=len(content_str),
                parsing_time_ms=parsing_time_ms,
            )

        except TimeoutError:
            parsing_time_ms = int((time.time() - start_time) * 1000)
            return ParseResult(
                success=False,
                content="",
                file_type="unknown",
                file_extension=file_extension,
                extracted_text_length=0,
                error_message=f"Parsing timed out after {timeout_seconds} seconds",
                parsing_time_ms=parsing_time_ms,
            )

        except Exception as e:
            parsing_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Failed to parse content for {filename}: {e}")
            return ParseResult(
                success=False,
                content="",
                file_type="unknown",
                file_extension=file_extension,
                extracted_text_length=0,
                error_message=str(e),
                parsing_time_ms=parsing_time_ms,
            )

    def _validate_signature(
        self, content: bytes, file_extension: str
    ) -> Tuple[bool, Optional[str]]:
        """Validate file signature (magic number).

        Args:
            content: File content
            file_extension: Expected file extension

        Returns:
            Tuple of (is_valid, detected_type)
        """
        # Get expected signature for this extension
        expected_sig = FILE_SIGNATURES.get(file_extension)

        if expected_sig is None:
            # No signature defined for this extension, skip validation
            return True, None

        signature, offset = expected_sig

        # Handle special cases
        if file_extension == ".txt":
            # Plain text: check if content is mostly printable
            if len(content) == 0:
                return True, "txt"
            # Check if content is mostly ASCII/UTF-8 text
            try:
                text = content.decode("utf-8")
                printable_ratio = sum(
                    1 for c in text[:1000] if c.isprintable() or c in "\n\r\t"
                ) / min(len(text), 1000)
                return printable_ratio > 0.7, "txt"
            except UnicodeDecodeError:
                return False, "binary"

        elif file_extension == ".md":
            # Markdown: check for markdown syntax or text content
            if len(content) == 0:
                return True, "md"
            try:
                text = content.decode("utf-8")
                # Check for markdown indicators
                has_markdown = (
                    "#" in text[:500] or  # Headers
                    "**" in text[:500] or  # Bold
                    "*" in text[:500] or  # Lists
                    "[" in text[:500] and "]" in text[:500] or  # Links
                    "```" in text[:500]  # Code blocks
                )
                # Or just text content
                is_text = all(
                    c == 0 or (c >= 32 and c != 0x7F) or c in (10, 13, 9)
                    for c in content[:1000]
                )
                return is_text and (has_markdown or len(text) > 0), "md"
            except UnicodeDecodeError:
                return False, "binary"

        elif file_extension == ".json":
            # JSON: check for JSON structure
            if len(content) == 0:
                return False, "empty"
            try:
                # Try to parse as JSON
                json.loads(content.decode("utf-8"))
                return True, "json"
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Check if it starts with { or [
                return content.startswith(b"{") or content.startswith(b"["), "json"

        elif file_extension == ".csv":
            # CSV: check for CSV structure
            if len(content) == 0:
                return True, "csv"
            try:
                text = content.decode("utf-8")
                # Check for comma-separated values
                has_commas = "," in text[:500]
                # Or check if it's valid text
                is_text = all(
                    c == 0 or (c >= 32 and c != 0x7F) or c in (10, 13, 9)
                    for c in content[:1000]
                )
                return is_text and has_commas, "csv"
            except UnicodeDecodeError:
                return False, "binary"

        elif file_extension == ".pdf":
            # PDF: check for %PDF signature
            return content.startswith(signature), "pdf"

        elif file_extension == ".zip":
            # ZIP: check for PK signature
            return content.startswith(signature), "zip"

        return True, None

    def _parse_content(
        self, content: bytes, file_extension: str, timeout_seconds: float
    ) -> str:
        """Parse content based on file extension.

        Args:
            content: Raw file content
            file_extension: File extension
            timeout_seconds: Timeout in seconds

        Returns:
            Extracted text content

        Raises:
            TimeoutError: If parsing exceeds timeout
        """
        # Create a timeout handler
        def timeout_handler():
            raise TimeoutError("Parsing exceeded timeout")

        # For small files, parse directly
        if len(content) < 1024 * 1024:  # 1 MB
            return self._parse_content_direct(content, file_extension)

        # For larger files, use a simple timeout mechanism
        import threading
        result = {"content": "", "error": None}

        def parse_worker():
            try:
                result["content"] = self._parse_content_direct(content, file_extension)
            except Exception as e:
                result["error"] = e

        thread = threading.Thread(target=parse_worker, daemon=True)
        thread.start()
        thread.join(timeout_seconds)

        if thread.is_alive():
            raise TimeoutError("Parsing exceeded timeout")

        if result["error"]:
            raise result["error"]

        return result["content"]

    def _parse_content_direct(
        self, content: bytes, file_extension: str
    ) -> str:
        """Parse content without timeout handling.

        Args:
            content: Raw file content
            file_extension: File extension

        Returns:
            Extracted text content
        """
        # Decode content
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except UnicodeDecodeError:
                text = content.decode("utf-8", errors="replace")

        # Parse based on file type
        if file_extension == ".txt":
            return self._parse_txt(text)

        elif file_extension == ".md":
            return self._parse_md(text)

        elif file_extension == ".json":
            return self._parse_json(text)

        elif file_extension == ".csv":
            return self._parse_csv(text)

        elif file_extension == ".pdf":
            return self._parse_pdf(content)

        else:
            # Default: return raw text
            return text

    def _parse_txt(self, text: str) -> str:
        """Parse plain text file.

        Args:
            text: File content

        Returns:
            Cleaned text content
        """
        # Remove BOM if present
        if text.startswith("\ufeff"):
            text = text[1:]

        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Remove excessive whitespace
        lines = [line.rstrip() for line in text.split("\n")]
        return "\n".join(lines)

    def _parse_md(self, text: str) -> str:
        """Parse Markdown file.

        Args:
            text: File content

        Returns:
            Extracted text content (stripped of markdown syntax)
        """
        # Remove code blocks
        import re
        text = re.sub(r"```[\s\S]*?```", "", text)
        text = re.sub(r"`[^`]+`", "", text)

        # Remove headers
        text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)

        # Remove bold/italic markers
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"__([^_]+)__", r"\1", text)
        text = re.sub(r"_([^_]+)_", r"\1", text)

        # Remove images
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)

        # Remove links, keep text
        text = re.sub(r"\[([^\]]*)\]\([^)]+\)", r"\1", text)

        # Remove blockquotes
        text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)

        # Remove horizontal rules
        text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)

        # Remove list markers
        text = re.sub(r"^\s*[\*\-\+]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)

        # Normalize whitespace
        text = "\n".join(line.strip() for line in text.split("\n"))

        return text.strip()

    def _parse_json(self, text: str) -> str:
        """Parse JSON file.

        Args:
            text: File content

        Returns:
            Extracted text content as formatted string
        """
        try:
            data = json.loads(text)

            def extract_text(obj: Any, depth: int = 0) -> str:
                """Recursively extract text from JSON structure."""
                indent = "  " * depth

                if isinstance(obj, str):
                    return obj
                elif isinstance(obj, dict):
                    lines = []
                    for key, value in obj.items():
                        lines.append(f"{indent}{key}:")
                        if isinstance(value, (dict, list)):
                            lines.append(extract_text(value, depth + 1))
                        elif isinstance(value, str):
                            lines.append(f"{indent}  {value}")
                        else:
                            lines.append(f"{indent}  {value}")
                    return "\n".join(lines)
                elif isinstance(obj, list):
                    lines = []
                    for i, item in enumerate(obj):
                        lines.append(f"{indent}- [{i}]")
                        if isinstance(item, (dict, list)):
                            lines.append(extract_text(item, depth + 1))
                        elif isinstance(item, str):
                            lines.append(f"{indent}  {item}")
                        else:
                            lines.append(f"{indent}  {item}")
                    return "\n".join(lines)
                else:
                    return str(obj)

            return extract_text(data)

        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON: {e}")
            return text

    def _parse_csv(self, text: str) -> str:
        """Parse CSV file.

        Args:
            text: File content

        Returns:
            Extracted text content as formatted string
        """
        try:
            reader = csv.reader(StringIO(text))
            rows = list(reader)

            if not rows:
                return ""

            # Get column headers
            headers = rows[0]
            lines = []

            # Add header row
            lines.append(" | ".join(headers))
            lines.append("-" * len(lines[0]))

            # Add data rows
            for row in rows[1:]:
                if row:  # Skip empty rows
                    lines.append(" | ".join(str(cell) for cell in row))

            return "\n".join(lines)

        except csv.Error as e:
            logger.warning(f"CSV parsing error: {e}")
            return text

    def _parse_pdf(self, content: bytes) -> str:
        """Parse PDF file.

        Args:
            content: Raw PDF content

        Returns:
            Extracted text content
        """
        if not self._pdfplumber_available:
            logger.warning("pdfplumber not available, returning empty content")
            return ""

        try:
            import pdfplumber

            # Create a temporary file-like object
            from io import BytesIO
            pdf_file = BytesIO(content)

            with pdfplumber.open(pdf_file) as pdf:
                text_parts = []

                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)

                return "\n\n".join(text_parts)

        except ImportError:
            logger.warning("pdfplumber not installed")
            return ""
        except Exception as e:
            logger.error(f"PDF parsing error: {e}")
            return ""

    def _get_file_type(self, file_extension: str) -> str:
        """Get the MIME type for a file extension.

        Args:
            file_extension: File extension

        Returns:
            MIME type string
        """
        type_map = {
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".json": "application/json",
            ".csv": "text/csv",
            ".pdf": "application/pdf",
        }
        return type_map.get(file_extension, "application/octet-stream")

    def is_supported_file(self, filename: str) -> bool:
        """Check if a file type is supported.

        Args:
            filename: Filename with extension

        Returns:
            True if supported, False otherwise
        """
        extension = Path(filename).suffix.lower()
        return extension in self.config.supported_extensions


# =============================================================================
# Module-level convenience functions
# =============================================================================

_default_parser: Optional[FileParser] = None


def get_parser() -> FileParser:
    """Get or create the default parser instance.

    Returns:
        FileParser instance
    """
    global _default_parser
    if _default_parser is None:
        _default_parser = FileParser()
    return _default_parser


def parse_file(
    file_path: Union[str, Path],
    timeout_seconds: Optional[float] = None,
) -> ParseResult:
    """Parse a file using the default parser.

    Args:
        file_path: Path to the file
        timeout_seconds: Optional timeout override

    Returns:
        ParseResult with extracted content
    """
    return get_parser().parse_file(file_path, timeout_seconds)


def parse_content(
    content: bytes,
    filename: str,
    timeout_seconds: Optional[float] = None,
) -> ParseResult:
    """Parse file content using the default parser.

    Args:
        content: Raw file content
        filename: Original filename
        timeout_seconds: Optional timeout override

    Returns:
        ParseResult with extracted content
    """
    return get_parser().parse_content(content, filename, timeout_seconds)
