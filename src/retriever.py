import logging
import numpy as np
from typing import List, Dict, Any
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from src.utils import get_logger

logger = get_logger("retriever")

class TFIDFRetriever:
    """
    A lightweight, in-memory retriever that indexes document chunks 
    using TF-IDF vectors and retrieves relevant contexts using Cosine Similarity.
    """
    def __init__(self, chunks: List[Dict[str, Any]]) -> None:
        """
        Initializes the retriever and fits TF-IDF vectorizer on the chunk texts.
        """
        if not chunks:
            raise ValueError("Retriever initialized with an empty chunk list.")
            
        self.chunks = chunks
        self.chunk_texts = [chunk["text"] for chunk in chunks]
        
        # Initialize Scikit-Learn's TF-IDF Vectorizer
        # Use english stop words and sublinear TF scaling to handle term frequency variance
        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            sublinear_tf=True,
            lowercase=True
        )
        
        # Fit vectorizer and build the document-term matrix
        self.tfidf_matrix = self.vectorizer.fit_transform(self.chunk_texts)
        logger.info(f"TF-IDF matrix built successfully with {len(self.chunks)} documents and {self.tfidf_matrix.shape[1]} vocabulary features.")

    def retrieve(self, query: str, k: int = 2) -> List[Dict[str, Any]]:
        """
        Retrieves the top k chunks most relevant to the query.
        
        Returns a list of chunk dictionaries including similarity scores in metadata.
        """
        if not query.strip():
            logger.warning("Empty query received for retrieval. Returning top chunks by default order.")
            return self.chunks[:k]

        # Vectorize query string
        query_vector = self.vectorizer.transform([query])
        
        # Compute cosine similarity between query and all chunk vectors
        # shape: (1, num_chunks)
        similarities = cosine_similarity(query_vector, self.tfidf_matrix).flatten()
        
        # Get indices of sorted similarities in descending order
        # np.argsort returns indices in ascending order, so we reverse it
        top_indices = np.argsort(similarities)[::-1][:k]
        
        retrieved_chunks = []
        for idx in top_indices:
            score = float(similarities[idx])
            chunk = self.chunks[idx].copy()
            # Attach score metadata
            chunk["similarity_score"] = score
            logger.debug(f"Retrieved chunk {chunk['chunk_id']} (Page {chunk['page_num']}) with similarity score: {score:.4f}")
            retrieved_chunks.append(chunk)

        # Log a warning if the top match has zero similarity (no overlapping terms)
        if retrieved_chunks and retrieved_chunks[0]["similarity_score"] == 0.0:
            logger.warning(
                f"No matching terms found in index for query: '{query}'. "
                "Returning best lexical match (score: 0.0)."
            )
            
        return retrieved_chunks
