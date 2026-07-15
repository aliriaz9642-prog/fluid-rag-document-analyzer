import os
import logging
from typing import List, Dict, Any, Optional
from groq import Groq
from src.retriever import TFIDFRetriever
from src.utils import get_logger, retry_api_call

logger = get_logger("qa")

def answer_questions(
    questions: List[str],
    chunks: List[Dict[str, Any]],
    retriever: TFIDFRetriever,
    model_name: Optional[str] = None,
    k: int = 2
) -> List[Dict[str, Any]]:
    """
    Answers a list of questions using retrieved document contexts via the Groq API.
    
    Returns a list of dictionaries:
    [
        {
            "question": "What is the key conclusion?",
            "answer": "The key conclusion is...",
            "source_chunk_references": ["Page 2, Section: Conclusion (Chunk 12)"]
        },
        ...
    ]
    """
    if not questions:
        logger.warning("No questions provided for QA.")
        return []

    if not model_name:
        model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key.strip() == "your_api_key_here" or not api_key.strip():
        raise ValueError(
            "Groq API key is missing. Please set GROQ_API_KEY in your .env file."
        )

    # Initialize Groq client
    client = Groq(api_key=api_key)
    qa_results = []

    for q in questions:
        q = q.strip()
        if not q:
            continue
            
        logger.info(f"Processing question: '{q}'")
        
        # Retrieve top k matching chunks
        matching_chunks = retriever.retrieve(q, k=k)
        
        # Assemble context string and references
        context_parts = []
        references = []
        
        for c in matching_chunks:
            # Build clean metadata references
            page_info = f"Page {c['page_num']}" if c.get("page_num") is not None else "Text document"
            section_info = f"Section: '{c.get('section_title')}'" if c.get("section_title") else ""
            chunk_ref = f"{page_info}, {section_info} (Chunk ID: {c['chunk_id']})"
            references.append(chunk_ref)
            
            # Format context block
            context_parts.append(
                f"[Source Reference: {chunk_ref}]\n"
                f"{c['text']}"
            )

        combined_context = "\n\n=== Context Block ===\n".join(context_parts)

        # Call Groq API using retry helper
        def _call_groq_qa():
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a precise document QA assistant.\n"
                            "You will be given contextual snippets from a document and a question.\n"
                            "Answer the question using ONLY the provided contexts. Do not use outside facts.\n"
                            "If the answer cannot be found in the provided contexts, you MUST reply "
                            "exactly: 'I cannot answer this question based on the provided document.'\n"
                            "Keep your response concise, clear, and objective. Do not speculate."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Contexts:\n{combined_context}\n\nQuestion: {q}"
                    }
                ],
                temperature=0.0,  # low temperature for maximum factual precision
                max_tokens=300
            )
            return response.choices[0].message.content

        try:
            answer = retry_api_call(_call_groq_qa)
            answer = answer.strip()
            
            qa_results.append({
                "question": q,
                "answer": answer,
                "source_chunk_reference": ", ".join(references)
            })
            
        except Exception as e:
            logger.error(f"Failed to answer question '{q}': {e}")
            qa_results.append({
                "question": q,
                "answer": f"Error attempting to generate answer: {str(e)}",
                "source_chunk_reference": "N/A"
            })

    return qa_results
