import os
import time
import json
import logging
import tempfile
from typing import List, Optional
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

from src.utils import get_logger
from src.extractor import extract_text_from_file
from src.chunker import chunk_document
from src.retriever import TFIDFRetriever
from src.summarizer import generate_section_summaries
from src.qa import answer_questions

logger = get_logger("app")

app = FastAPI(
    title="Document Insight Pipeline API",
    description="Web API backend for document analysis, summarization, and retrieval-grounded QA.",
    version="1.0.0"
)

# Enable CORS for local testing and flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure the template directory exists
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# Mount static files (HTML, CSS, JS)
app.mount("/static", StaticFiles(directory=TEMPLATES_DIR), name="static")

DEFAULT_QUESTIONS = [
    "What is the main topic of this document?",
    "What are the key conclusions or findings?",
    "What recommendations or action items are mentioned?"
]

@app.get("/")
def read_root():
    """Serves the main single-page web dashboard."""
    index_path = os.path.join(TEMPLATES_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="Frontend templates not found.")
    return FileResponse(index_path)


@app.post("/api/analyze")
async def analyze_document(
    file: UploadFile = File(...),
    questions: Optional[str] = Form(None)
):
    """
    Endpoint that handles document uploading, parsing, chunking,
    summarization, and retrieval-grounded Q&A.
    
    'questions' should be a JSON-serialized array of question strings.
    """
    start_time = time.time()
    logger.info(f"Received analysis request for file: '{file.filename}'")

    # 1. Groq API Key Check
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key.strip() == "your_api_key_here" or not api_key.strip():
        logger.error("GROQ_API_KEY environment variable is not configured on the server.")
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: Groq API key is not configured. Please check .env settings."
        )

    # 2. File validation (Type, size)
    filename = file.filename or "unknown"
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    if ext not in [".pdf", ".txt"]:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{ext}'. Only .pdf and .txt files are supported."
        )

    # Read bytes to check file size limit (20MB)
    try:
        file_bytes = await file.read()
    except Exception as e:
        logger.error(f"Error reading uploaded file: {e}")
        raise HTTPException(status_code=400, detail="Unable to read uploaded file.")

    max_size_bytes = 20 * 1024 * 1024
    if len(file_bytes) > max_size_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds the maximum size limit of 20 MB."
        )

    # 3. Parse questions
    parsed_questions = DEFAULT_QUESTIONS
    if questions:
        try:
            parsed_questions = json.loads(questions)
            if not isinstance(parsed_questions, list):
                parsed_questions = DEFAULT_QUESTIONS
        except Exception as e:
            logger.warning(f"Failed to parse custom questions: {e}. Reverting to defaults.")
            parsed_questions = DEFAULT_QUESTIONS

    # 4. Save to temporary file for pipeline processing
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        try:
            tmp.write(file_bytes)
            temp_path = tmp.name
        except Exception as e:
            logger.error(f"Failed to write temp upload file: {e}")
            raise HTTPException(status_code=500, detail="Server disk error writing temp data.")

    try:
        # Run Extraction
        pages_data = extract_text_from_file(temp_path)
        
        # Run Chunker
        chunks = chunk_document(pages_data)
        if not chunks:
            raise ValueError("Document contains no logical text chunks.")
            
        # Build TF-IDF search index
        retriever = TFIDFRetriever(chunks)
        
        # Generate section-wise summaries
        sections_summary = generate_section_summaries(chunks)
        
        # Answer questions
        qa_results = answer_questions(
            questions=parsed_questions,
            chunks=chunks,
            retriever=retriever
        )
        
        execution_time_sec = time.time() - start_time
        processing_time_str = f"{execution_time_sec:.2f} seconds"
        model_used = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

        # Compile response structure
        result = {
            "document_name": filename,
            "total_chunks": len(chunks),
            "sections_summary": sections_summary,
            "qa_results": qa_results,
            "metadata": {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "model_used": model_used,
                "processing_time": processing_time_str
            }
        }
        
        logger.info(f"Analysis completed successfully for '{filename}' in {processing_time_str}.")
        return result

    except ValueError as ve:
        logger.error(f"Validation error processing document '{filename}': {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Unexpected pipeline error while processing '{filename}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline processing failed: {str(e)}")
    finally:
        # Clean up temp file safely
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_path}: {e}")
