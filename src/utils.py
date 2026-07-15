import os
import logging
import time
from typing import Callable, Any

# Configure logging format and default level
log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)

logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger("document-pipeline")

def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger configured as a child of the main pipeline logger.
    """
    return logging.getLogger(f"document-pipeline.{name}")


def validate_file(file_path: str, max_size_mb: float = 20.0) -> None:
    """
    Validates that a file:
    1. Exists and is a file.
    2. Is readable.
    3. Has a valid extension (.pdf or .txt).
    4. Does not exceed the maximum allowed file size.

    Raises FileNotFoundError, PermissionError, or ValueError on failure.
    """
    # 1. Check existence
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    if not os.path.isfile(file_path):
        raise ValueError(f"Path is not a file: {file_path}")

    # 2. Check extension
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()
    if ext not in [".pdf", ".txt"]:
        raise ValueError(f"Unsupported file extension '{ext}'. Only .pdf and .txt are supported.")

    # 3. Check readability
    if not os.access(file_path, os.R_OK):
        raise PermissionError(f"File is not readable (permission denied): {file_path}")

    # 4. Check file size
    file_size_bytes = os.path.getsize(file_path)
    max_size_bytes = max_size_mb * 1024 * 1024
    if file_size_bytes > max_size_bytes:
        raise ValueError(
            f"File size ({file_size_bytes / (1024 * 1024):.2f} MB) exceeds "
            f"the maximum allowed limit of {max_size_mb} MB."
        )


def retry_api_call(
    func: Callable[..., Any], 
    *args: Any, 
    max_retries: int = 3, 
    initial_delay: float = 1.0, 
    backoff_factor: float = 2.0, 
    **kwargs: Any
) -> Any:
    """
    Executes a callable with exponential backoff on failure.
    Prevents leaking sensitive data in logs by censoring details if needed.
    """
    log = get_logger("retry")
    delay = initial_delay
    last_exception = None

    for attempt in range(1, max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            # Strip any API keys from the error message for safety
            err_msg = str(e)
            if "api_key" in err_msg or "gsk_" in err_msg:
                # GSK is the standard Groq API key prefix, censor it
                err_msg = "[Censored API Error containing sensitive token information]"

            log.warning(
                f"API call failed on attempt {attempt}/{max_retries} with error: {err_msg}. "
                f"Retrying in {delay:.2f} seconds..."
            )
            
            if attempt < max_retries:
                time.sleep(delay)
                delay *= backoff_factor

    # If it reached here, all retries failed
    final_err_msg = str(last_exception)
    if "api_key" in final_err_msg or "gsk_" in final_err_msg:
         final_err_msg = "[Censored API Error containing sensitive token information]"
    
    log.error(f"API call failed permanently after {max_retries} attempts.")
    raise RuntimeError(f"API call failed permanently: {final_err_msg}") from last_exception
