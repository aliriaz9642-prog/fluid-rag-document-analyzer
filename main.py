import os
import sys
import time
import argparse
from datetime import datetime
from dotenv import load_dotenv

# Load env variables from .env file before importing packages
load_dotenv()

from src.utils import get_logger, validate_file
from src.extractor import extract_text_from_file
from src.chunker import chunk_document
from src.retriever import TFIDFRetriever
from src.summarizer import generate_section_summaries
from src.qa import answer_questions
from src.output_writer import write_outputs

logger = get_logger("main")

DEFAULT_QUESTIONS = [
    "What is the main topic of this document?",
    "What are the key conclusions or findings?",
    "What recommendations or action items are mentioned?"
]

def main() -> None:
    """
    CLI Entry Point for the Document Insight Pipeline.
    """
    parser = argparse.ArgumentParser(
        description="Mini Document Insight Pipeline - Extracts, summarizes, and answers questions from PDF/TXT documents."
    )
    parser.add_argument(
        "--file", 
        type=str, 
        required=False, 
        help="Path to the PDF or TXT input document (required for CLI mode)."
    )
    parser.add_argument(
        "--questions", 
        type=str, 
        nargs="+", 
        default=DEFAULT_QUESTIONS,
        help="Custom questions to answer using the document content."
    )
    parser.add_argument(
        "--model", 
        type=str, 
        default=None,
        help="Groq API LLM model. Falls back to GROQ_MODEL in env or 'llama-3.3-70b-versatile'."
    )
    parser.add_argument(
        "--output-dir", 
        type=str, 
        default="outputs",
        help="Directory where result.json and result.md will be saved."
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Launch the pipeline as a web application dashboard."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the web server on (defaults to 8000)."
    )
    
    args = parser.parse_args()

    # If web flag is passed, launch FastAPI server
    if args.web:
        import uvicorn
        logger.info("Initializing Web Server environment...")
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key or api_key.strip() == "your_api_key_here" or not api_key.strip():
            logger.error(
                "GROQ_API_KEY environment variable is not configured. "
                "Please configure a '.env' file in the root directory containing 'GROQ_API_KEY=gsk_...'."
            )
            sys.exit(1)
        logger.info(f"Starting server at http://127.0.0.1:{args.port} ...")
        uvicorn.run("src.app:app", host="127.0.0.1", port=args.port)
        return

    # Validate that --file is provided for CLI mode
    if not args.file:
        parser.error("the following arguments are required: --file (or use --web to run the dashboard)")
    
    start_time = time.time()
    logger.info("Initializing Mini Document Insight Pipeline...")
    
    # 1. Check for API key availability
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key.strip() == "your_api_key_here" or not api_key.strip():
        logger.error(
            "GROQ_API_KEY environment variable is not configured. "
            "Please create a '.env' file in the root directory containing 'GROQ_API_KEY=gsk_...'."
        )
        sys.exit(1)

    # 2. Resolve paths and execute pipeline
    file_path = args.file
    try:
        # Validate path and attributes
        validate_file(file_path)
        logger.info(f"File validated successfully: '{file_path}'")
        
        # Extract text page-by-page
        logger.info("Extracting text from document...")
        pages_data = extract_text_from_file(file_path)
        logger.info(f"Successfully extracted text from {len(pages_data)} pages/sources.")

        # Chunk the document text
        logger.info("Splitting text into logical chunks...")
        chunks = chunk_document(pages_data)
        logger.info(f"Created {len(chunks)} logical chunks for processing.")
        
        if not chunks:
            raise ValueError("No logical chunks generated from document.")

        # Initialize TF-IDF retriever for Q&A step
        logger.info("Building TF-IDF search index...")
        retriever = TFIDFRetriever(chunks)

        # Generate section summaries using Groq API
        logger.info("Generating section summaries via Groq...")
        sections_summary = generate_section_summaries(chunks, model_name=args.model)

        # Answer questions using retrieved chunks
        logger.info("Answering user questions using similarity retrieval...")
        qa_results = answer_questions(
            questions=args.questions,
            chunks=chunks,
            retriever=retriever,
            model_name=args.model
        )

        # Compute pipeline statistics
        execution_time_sec = time.time() - start_time
        processing_time_str = f"{execution_time_sec:.2f} seconds"
        
        # Prepare structured results
        model_used = args.model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        
        output_data = {
            "document_name": os.path.basename(file_path),
            "total_chunks": len(chunks),
            "sections_summary": sections_summary,
            "qa_results": qa_results,
            "metadata": {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "model_used": model_used,
                "processing_time": processing_time_str
            }
        }

        # Write results to output directory (JSON & Markdown)
        logger.info(f"Writing outputs to directory: '{args.output_dir}'")
        write_outputs(
            data=output_data,
            output_dir=args.output_dir
        )
        
        logger.info("====================================================")
        logger.info("PIPELINE COMPLETED SUCCESSFULLY!")
        logger.info(f"Total processing time: {processing_time_str}")
        logger.info(f"JSON outputs: {os.path.join(args.output_dir, 'result.json')}")
        logger.info(f"Markdown report: {os.path.join(args.output_dir, 'result.md')}")
        logger.info("====================================================")

    except (FileNotFoundError, PermissionError, ValueError) as ve:
        # User error / Bad input
        logger.error(f"Execution Error: {ve}")
        sys.exit(1)
    except Exception as e:
        # Unexpected transient pipeline or API error
        logger.error(f"Pipeline crashed due to unexpected error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
