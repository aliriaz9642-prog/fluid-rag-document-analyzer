import re
import logging
from typing import List, Dict, Any, Optional
from src.utils import get_logger

logger = get_logger("chunker")

def chunk_document(
    pages_data: List[Dict[str, Any]],
    max_chunk_size: int = 1500,
    overlap: int = 200,
    max_chunks_limit: int = 30
) -> List[Dict[str, Any]]:
    """
    Chunks extracted document text into logical sections.
    
    Tries to split by paragraphs and headings first. If paragraphs are too large 
    or unavailable, falls back to fixed-character chunks with sliding overlap.
    
    Each chunk is a dictionary:
    {
        "chunk_id": int,          # 1-indexed identifier
        "text": str,              # The text content of the chunk
        "page_num": int or None,  # Original PDF page number, if applicable
        "section_title": str      # Detected heading or section identifier
    }
    
    Enforces a strict upper limit on the number of chunks to prevent excessive API usage.
    """
    raw_chunks: List[Dict[str, Any]] = []
    chunk_counter = 1
    current_section = "Introduction"

    # Regex pattern to match potential headings: 
    # e.g., "1. Executive Summary", "SECTION A: INTRODUCTION", "Key Findings"
    # Criteria: line is short, doesn't end with a period, and matches title formatting or numberings.
    heading_regex = re.compile(r"^(?:(?:[A-Z0-9\.\-\s]{2,15}\d*[\.\:]\s+)?([A-Z][a-zA-Z0-9\s,\-\(\)\&]{3,80})|[A-Z\s]{4,80})$")

    for doc_page in pages_data:
        text = doc_page.get("text", "")
        page_num = doc_page.get("page_num")
        
        # Split page content into paragraphs
        # Normalize line endings first
        text_normalized = text.replace("\r\n", "\n")
        paragraphs = [p.strip() for p in text_normalized.split("\n\n") if p.strip()]
        
        # If splitting by double newlines didn't yield multiple paragraphs, try single newlines
        if len(paragraphs) <= 1:
            paragraphs = [p.strip() for p in text_normalized.split("\n") if p.strip()]

        current_chunk_text_parts: List[str] = []
        current_chunk_length = 0

        for para in paragraphs:
            # Check if paragraph looks like a heading
            lines = para.split("\n")
            if len(lines) == 1 and len(para) < 100:
                match = heading_regex.match(para)
                if match:
                    # Found a section heading!
                    # First, flush the existing chunk if it has content
                    if current_chunk_text_parts:
                        chunk_text = "\n\n".join(current_chunk_text_parts)
                        raw_chunks.append({
                            "chunk_id": chunk_counter,
                            "text": chunk_text,
                            "page_num": page_num,
                            "section_title": current_section
                        })
                        chunk_counter += 1
                        current_chunk_text_parts = []
                        current_chunk_length = 0
                    
                    current_section = para
                    continue

            # If paragraph itself is larger than the max chunk size, we must slice it
            if len(para) > max_chunk_size:
                # Flush the active chunk first
                if current_chunk_text_parts:
                    chunk_text = "\n\n".join(current_chunk_text_parts)
                    raw_chunks.append({
                        "chunk_id": chunk_counter,
                        "text": chunk_text,
                        "page_num": page_num,
                        "section_title": current_section
                    })
                    chunk_counter += 1
                    current_chunk_text_parts = []
                    current_chunk_length = 0

                # Slice large paragraph using sliding window (overlap)
                sliced_chunks = _slice_text_with_overlap(para, max_chunk_size, overlap)
                for slice_text in sliced_chunks:
                    raw_chunks.append({
                        "chunk_id": chunk_counter,
                        "text": slice_text,
                        "page_num": page_num,
                        "section_title": current_section
                    })
                    chunk_counter += 1
                continue

            # If adding this paragraph exceeds the chunk size, we flush and start new chunk
            if current_chunk_length + len(para) > max_chunk_size:
                chunk_text = "\n\n".join(current_chunk_text_parts)
                raw_chunks.append({
                    "chunk_id": chunk_counter,
                    "text": chunk_text,
                    "page_num": page_num,
                    "section_title": current_section
                })
                chunk_counter += 1
                
                # Setup next chunk with overlap or just standard split
                # To overlap, we take the last paragraph if its size permits it
                if current_chunk_text_parts and len(current_chunk_text_parts[-1]) < overlap:
                    current_chunk_text_parts = [current_chunk_text_parts[-1], para]
                    current_chunk_length = sum(len(p) for p in current_chunk_text_parts) + (len(current_chunk_text_parts) - 1) * 2
                else:
                    current_chunk_text_parts = [para]
                    current_chunk_length = len(para)
            else:
                current_chunk_text_parts.append(para)
                current_chunk_length += len(para) + (2 if current_chunk_length > 0 else 0)  # account for \n\n separator

        # Flush any remaining text at the end of the page
        if current_chunk_text_parts:
            chunk_text = "\n\n".join(current_chunk_text_parts)
            raw_chunks.append({
                "chunk_id": chunk_counter,
                "text": chunk_text,
                "page_num": page_num,
                "section_title": current_section
            })
            chunk_counter += 1

    # Check for maximum chunk processing limit to control API cost
    total_raw_chunks = len(raw_chunks)
    if total_raw_chunks > max_chunks_limit:
        logger.warning(
            f"Document yielded {total_raw_chunks} chunks, which exceeds the safety limit of {max_chunks_limit}. "
            f"Truncating the document to the first {max_chunks_limit} chunks."
        )
        raw_chunks = raw_chunks[:max_chunks_limit]

    return raw_chunks


def _slice_text_with_overlap(text: str, max_chunk_size: int, overlap: int) -> List[str]:
    """Slices a large string into fixed-character sections with overlap."""
    slices = []
    start = 0
    text_len = len(text)
    
    if text_len <= max_chunk_size:
        return [text]

    while start < text_len:
        end = start + max_chunk_size
        slice_str = text[start:end]
        slices.append(slice_str)
        
        # Advance the start pointer
        start += (max_chunk_size - overlap)
        
        # Prevent infinite loop if overlap is misconfigured to be larger than chunk size
        if overlap >= max_chunk_size:
            start += max_chunk_size
            
    return slices
