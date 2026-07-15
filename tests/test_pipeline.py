import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from src.utils import validate_file, retry_api_call
from src.extractor import extract_text_from_file
from src.chunker import chunk_document
from src.retriever import TFIDFRetriever
from src.summarizer import generate_section_summaries, _parse_bullet_points
from src.qa import answer_questions


def test_validate_file_nonexistent():
    """Verifies that validate_file raises FileNotFoundError for missing files."""
    with pytest.raises(FileNotFoundError):
        validate_file("nonexistent_file_xyz.txt")


def test_validate_file_invalid_ext():
    """Verifies that validate_file raises ValueError for unsupported extensions."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_name = tmp.name
    try:
        with pytest.raises(ValueError, match="Unsupported file extension"):
            validate_file(tmp_name)
    finally:
        os.remove(tmp_name)


def test_validate_file_too_large():
    """Verifies that validate_file raises ValueError when the file size exceeds limit."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        tmp.write(b"a" * (2 * 1024 * 1024))  # 2MB file
        tmp_name = tmp.name
    try:
        # Enforce a tight size limit of 1MB (1.0)
        with pytest.raises(ValueError, match="exceeds the maximum allowed limit"):
            validate_file(tmp_name, max_size_mb=1.0)
    finally:
        os.remove(tmp_name)


def test_empty_file_extraction():
    """Verifies that extract_text_from_file raises ValueError for empty (0 bytes) files."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        tmp_name = tmp.name
    try:
        with pytest.raises(ValueError, match="file is empty"):
            extract_text_from_file(tmp_name)
    finally:
        os.remove(tmp_name)


def test_whitespace_only_file_extraction():
    """Verifies that extract_text_from_file raises ValueError for whitespace-only text files."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        tmp.write(b"   \n  \n\t  ")
        tmp_name = tmp.name
    try:
        with pytest.raises(ValueError, match="contains only whitespace"):
            extract_text_from_file(tmp_name)
    finally:
        os.remove(tmp_name)


def test_non_pdf_renamed_as_pdf():
    """Verifies that a plain text file renamed with .pdf causes a parsing error."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(b"This is just plain text, not a valid PDF binary structure.")
        tmp_name = tmp.name
    try:
        # pdfplumber and pypdf will fail to parse this, raising ValueError or RuntimeError
        with pytest.raises(ValueError, match="Corrupted or unreadable PDF file"):
            extract_text_from_file(tmp_name)
    finally:
        os.remove(tmp_name)


@patch("pdfplumber.open")
def test_scanned_pdf_no_text(mock_pdf_open):
    """Verifies image-only PDF detection (no text extractable)."""
    # Mock pdfplumber returning pages, but text extraction is empty
    mock_pdf = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "  "  # whitespace only
    mock_pdf.pages = [mock_page]
    mock_pdf_open.return_value.__enter__.return_value = mock_pdf

    # Create dummy pdf file structure path
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(b"%PDF-1.4 dummy contents")
        tmp_name = tmp.name
    try:
        with pytest.raises(ValueError, match="No extractable text found"):
            extract_text_from_file(tmp_name)
    finally:
        os.remove(tmp_name)


def test_chunker_limit_truncation():
    """Verifies that chunker truncates output if the number of chunks exceeds max_chunks_limit."""
    # Build 15 pages of text
    pages_data = [
        {"text": f"This is page {i} content. It contains enough text to form a chunk.", "page_num": i}
        for i in range(1, 16)
    ]
    
    # Process with a safety cap of 5 chunks
    chunks = chunk_document(pages_data, max_chunk_size=100, max_chunks_limit=5)
    assert len(chunks) == 5
    assert chunks[0]["chunk_id"] == 1
    assert chunks[4]["chunk_id"] == 5


def test_chunker_fallback_no_headings():
    """Verifies that chunker falls back to default section names when no headings exist."""
    pages_data = [{
        "text": "Paragraph one is here.\n\nParagraph two is there.\n\nParagraph three is far away.",
        "page_num": 1
    }]
    
    # Run with small max size to split paragraphs
    chunks = chunk_document(pages_data, max_chunk_size=50, overlap=10)
    for c in chunks:
        assert c["section_title"] == "Introduction"  # default section title


def test_tfidf_retrieval():
    """Verifies TFIDFRetriever indexes chunks correctly and retrieves matching terms."""
    chunks = [
        {"chunk_id": 1, "text": "The quick brown fox jumps over the lazy dog.", "page_num": 1, "section_title": "Sec A"},
        {"chunk_id": 2, "text": "Deep Learning models are trained using gradient descent.", "page_num": 2, "section_title": "Sec B"},
        {"chunk_id": 3, "text": "Security scanning prevents package supply chain injection.", "page_num": 3, "section_title": "Sec C"}
    ]
    
    retriever = TFIDFRetriever(chunks)
    
    # Query matching chunk 2
    results = retriever.retrieve("gradient descent models", k=1)
    assert len(results) == 1
    assert results[0]["chunk_id"] == 2
    assert results[0]["similarity_score"] > 0.0

    # Query matching chunk 3
    results = retriever.retrieve("supply chain security", k=1)
    assert len(results) == 1
    assert results[0]["chunk_id"] == 3
    assert results[0]["similarity_score"] > 0.0


def test_bullet_points_parser():
    """Verifies that _parse_bullet_points splits lines and strips bullet marks."""
    raw_llm_out = "* Point one with star\n- Point two with dash\n+ Point three with plus\n1. Numbered point\nNo bullet point"
    parsed = _parse_bullet_points(raw_llm_out)
    assert parsed == [
        "Point one with star",
        "Point two with dash",
        "Point three with plus",
        "Numbered point",
        "No bullet point"
    ]


@patch("time.sleep", return_value=None)  # avoid delaying tests
def test_api_retry_exponential_backoff(mock_sleep):
    """Verifies retry_api_call retries failing functions and raises RuntimeError after limit."""
    mock_func = MagicMock(side_effect=Exception("Transient Groq API rate limit error"))
    
    with pytest.raises(RuntimeError, match="API call failed permanently"):
        retry_api_call(mock_func, max_retries=3, initial_delay=0.1)
        
    assert mock_func.call_count == 3
    assert mock_sleep.call_count == 2  # sleep between attempts 1-2 and 2-3


@patch("time.sleep", return_value=None)
def test_api_retry_success_on_third_attempt(mock_sleep):
    """Verifies retry_api_call succeeds if a transient error resolves on a subsequent retry."""
    # Fail twice, then succeed
    mock_func = MagicMock(side_effect=[
        Exception("Error 1"),
        Exception("Error 2"),
        "API Success Response"
    ])
    
    result = retry_api_call(mock_func, max_retries=3, initial_delay=0.1)
    assert result == "API Success Response"
    assert mock_func.call_count == 3
    assert mock_sleep.call_count == 2
