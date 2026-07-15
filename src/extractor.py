import os
import logging
from typing import List, Dict, Tuple, Any
from src.utils import get_logger, validate_file

logger = get_logger("extractor")

def extract_text_from_file(file_path: str) -> List[Dict[str, Any]]:
    """
    Extracts text from a validated PDF or TXT file.
    
    Returns a list of dictionaries, where each dictionary represents a block of text
    with metadata:
    [
        {
            "text": "extracted text content",
            "page_num": 1,         # 1-indexed for PDFs, None for TXT
            "source_type": "pdf"   # 'pdf' or 'txt'
        },
        ...
    ]
    
    Raises:
        ValueError: If file is empty or has no extractable text.
        RuntimeError: For file reading or parsing failures.
    """
    # 1. Run common file validations (exists, readable, extension, size limit)
    validate_file(file_path)

    # Check for empty file (0 bytes) before parsing
    if os.path.getsize(file_path) == 0:
        raise ValueError("No content found: file is empty (0 bytes).")

    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    try:
        if ext == ".txt":
            return _extract_from_txt(file_path)
        elif ext == ".pdf":
            return _extract_from_pdf(file_path)
        else:
            raise ValueError(f"Unsupported file format: {ext}")
    except ValueError as ve:
        # Re-raise user-facing validation errors directly
        logger.error(f"Validation error during extraction: {ve}")
        raise
    except Exception as e:
        logger.error(f"Error extracting text from {file_path}: {e}", exc_info=True)
        raise RuntimeError(f"Failed to process file: {str(e)}")


def _extract_from_txt(file_path: str) -> List[Dict[str, Any]]:
    """Reads text from a TXT file using UTF-8 (with fallback to latin-1)."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
    except UnicodeDecodeError:
        logger.warning("UTF-8 decoding failed, falling back to ISO-8859-1 (Latin-1).")
        with open(file_path, "r", encoding="iso-8859-1") as f:
            text = f.read()

    # Check for whitespace-only text
    if not text.strip():
        raise ValueError("No content found: file contains only whitespace.")

    return [{
        "text": text,
        "page_num": None,
        "source_type": "txt"
    }]


def _extract_from_pdf(file_path: str) -> List[Dict[str, Any]]:
    """Extracts text page-by-page from a PDF using pdfplumber, falling back to pypdf."""
    pages_data = []
    
    # 1. Try pdfplumber
    try:
        import pdfplumber
        logger.debug("Attempting to parse PDF using pdfplumber.")
        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages:
                raise ValueError("Corrupted PDF: No pages found in the document.")
            
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if text and text.strip():
                    pages_data.append({
                        "text": text.strip(),
                        "page_num": i,
                        "source_type": "pdf"
                    })
    except ImportError:
        logger.warning("pdfplumber not installed. Falling back to pypdf.")
        pages_data = _extract_from_pdf_fallback(file_path)
    except Exception as e:
        # Handle case where pdfplumber itself fails to parse the file (corrupted)
        logger.warning(f"pdfplumber parsing failed: {e}. Trying pypdf fallback...")
        try:
            pages_data = _extract_from_pdf_fallback(file_path)
        except Exception as fallback_err:
            raise ValueError(f"Corrupted or unreadable PDF file. Details: {fallback_err}") from e

    # 2. Check if text was successfully extracted
    total_text = "".join([p["text"] for p in pages_data]).strip()
    if not total_text:
        raise ValueError(
            "No extractable text found. The document may be a scanned image-only PDF, "
            "or it may be password-protected/corrupted."
        )

    return pages_data


def _extract_from_pdf_fallback(file_path: str) -> List[Dict[str, Any]]:
    """Fallback parser using pypdf."""
    from pypdf import PdfReader
    pages_data = []
    
    try:
        reader = PdfReader(file_path)
        # If reader has zero pages or metadata error, it might be corrupted
        if len(reader.pages) == 0:
            raise ValueError("No pages found.")
            
        for i, page in enumerate(reader.pages, start=1):
            text = page.extract_text()
            if text and text.strip():
                pages_data.append({
                    "text": text.strip(),
                    "page_num": i,
                    "source_type": "pdf"
                })
    except Exception as e:
        raise ValueError(f"Fallback PDF parsing failed: {e}")
    
    return pages_data
