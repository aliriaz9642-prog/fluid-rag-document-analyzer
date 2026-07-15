import os
import re
import logging
from typing import List, Dict, Any, Optional
from groq import Groq
from src.utils import get_logger, retry_api_call

logger = get_logger("summarizer")

def generate_section_summaries(
    chunks: List[Dict[str, Any]],
    model_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Groups chunks by section title and queries Groq to generate a structured, 
    bullet-point summary for each section.
    
    Returns a list of dictionaries:
    [
        {
            "section_title": "Introduction",
            "bullet_points": ["Point A", "Point B"]
        },
        ...
    ]
    """
    if not chunks:
        logger.warning("No chunks provided for summary generation.")
        return []

    # Get model name from parameter, environment, or default fallback
    if not model_name:
        model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key.strip() == "your_api_key_here" or not api_key.strip():
        raise ValueError(
            "Groq API key is missing. Please set GROQ_API_KEY in your .env file."
        )

    # Initialize Groq client
    # Do not print or log the api_key value
    client = Groq(api_key=api_key)

    # Group chunks by section title while preserving their order of appearance
    sections: Dict[str, List[str]] = {}
    section_order: List[str] = []
    
    for chunk in chunks:
        title = chunk.get("section_title") or "General Document Section"
        if title not in sections:
            sections[title] = []
            section_order.append(title)
        sections[title].append(chunk["text"])

    summaries: List[Dict[str, Any]] = []

    for section_title in section_order:
        logger.info(f"Generating summary for section: '{section_title}'")
        combined_text = "\n\n".join(sections[section_title])
        
        # Guard: limit text size per API call to avoid token limit errors
        if len(combined_text) > 12000:
            logger.warning(f"Section '{section_title}' is too large ({len(combined_text)} chars). Truncating text for summary API call.")
            combined_text = combined_text[:12000] + "\n\n[Content truncated for length constraints]"

        # Call API using the retry helper
        def _call_groq():
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert technical editor. Summarize the provided document section "
                            "content into concise, high-value bullet points. Organize findings logically.\n"
                            "Return ONLY the bullet points, one per line, starting with a hyphen (-) or asterisk (*).\n"
                            "Do NOT include any introduction, conversational response, headers, or concluding remarks."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Section Title: {section_title}\n\nContent:\n{combined_text}"
                    }
                ],
                temperature=0.3,
                max_tokens=500
            )
            return response.choices[0].message.content

        try:
            summary_content = retry_api_call(_call_groq)
            bullet_points = _parse_bullet_points(summary_content)
            
            # Fallback if LLM output was empty or failed to parse
            if not bullet_points:
                bullet_points = ["Key details could not be parsed from this section."]

            summaries.append({
                "section_title": section_title,
                "bullet_points": bullet_points
            })
            
        except Exception as e:
            logger.error(f"Failed to generate summary for section '{section_title}': {e}")
            summaries.append({
                "section_title": section_title,
                "bullet_points": [f"Error generating summary: {str(e)}"]
            })

    return summaries


def _parse_bullet_points(text: str) -> List[str]:
    """Parses raw LLM string response into clean list of bullet point strings."""
    bullets = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        
        # Remove markdown bullet characters and leading whitespace
        # Match lines starting with -, *, +, or digit numbering (e.g. 1.)
        clean_line = re.sub(r'^[\-\*\+\u2022]\s*', '', line) # remove bullets
        clean_line = re.sub(r'^\d+\.\s*', '', clean_line)     # remove numbered bullet formats
        clean_line = clean_line.strip()
        
        if clean_line:
            bullets.append(clean_line)
            
    return bullets
