# Mini Document Insight Pipeline

A production-quality Python pipeline that parses documents (PDFs and TXT), chunks content logically, computes similarity rankings, generates section-wise summaries, and answers questions using a localized Retrieval-Augmented Generation (RAG) pattern powered by the Groq Llama-3 API.

---

## 🗺️ Project Architecture

Here is the data flow of the Document Insight Pipeline:

```text
  [Input PDF/TXT]
         │
         ▼
 1. File Validator  ──► Check extension, readability, size limit (<20MB)
         │
         ▼
 2. Text Extractor  ──► pdfplumber / pypdf (fallback) or UTF-8 text reader
         │
         ▼
 3. Text Chunker    ──► Paragraph grouping + sliding character-window (with overlap)
         │
         ├───► Chunks (max 30 cap)
         │
         ├───► [Summarization Engine] ──► Group by Section ──► Groq API ──► Structured Summary
         │
         └───► [TF-IDF Retrieval Index] 
                     │
                     ├─► User Question
                     │        │
                     │        ▼
                     ├─► Cosine Similarity Match (Top k Chunks)
                     │        │
                     │        ▼
                     └─► [QA Engine] ──► Groq API (Context Constrained) ──► Factual Answer
                                 │
                                 ▼
                     4. Output Writer ──► result.json & result.md
```

---

## ✨ Features

- **Robust Parsing**: Extracts text from text files and PDF documents. Includes pdfplumber, falling back gracefully to pypdf for maximum portability.
- **Section & Heading Aware Chunking**: Detects headers in documents and groups text paragraphs logically under their respective headings. Slices overly large text blocks using a sliding window with overlap.
- **Section-wise Bullet Summarization**: Groups text chunks by section to provide organized, distinct bulleted summaries (never one giant paragraph).
- **Localized Context Retrieval**: Creates an in-memory TF-IDF index of the text chunks and uses Cosine Similarity (`scikit-learn`) to fetch only the relevant context chunks for QA.
- **Factual Question Answering**: Feeds retrieved contexts to Groq's Llama-3 model (`llama-3.3-70b-versatile`), enforcing strict constraints to only answer using provided facts (no hallucinations).
- **Dual Outputs**: Produces both structured `result.json` and a formatted, human-readable report in `result.md`.
- **Comprehensive Error Boundaries**: Gracefully handles scanned PDFs, empty files, corrupted structures, and network timeouts.

---

## 🛠️ Tech Stack

- **Core**: Python 3.10+
- **LLM API Provider**: [Groq Cloud SDK](https://github.com/groq/groq-python) (Default Model: `llama-3.3-70b-versatile`)
- **PDF Extraction**: `pdfplumber` (Primary), `pypdf` (Fallback)
- **Vector Retrieval**: `scikit-learn` (TF-IDF Vectorizer & Cosine Similarity)
- **Environment Management**: `python-dotenv`
- **Testing**: `pytest`, `pytest-mock`

---

## ⚙️ Setup & Installation

Follow these steps to run the pipeline locally:

### 1. Clone the repository and navigate to its folder
```bash
cd document-insight-pipeline
```

### 2. Create and activate a Virtual Environment
**On Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```
**On macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Required Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy the `.env.example` file to create your own `.env` file:
```bash
cp .env.example .env
```
Open `.env` and configure your Groq API Key:
```env
GROQ_API_KEY=gsk_your_real_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
LOG_LEVEL=INFO
```
*(You can obtain a free Groq API key by signing in at [console.groq.com](https://console.groq.com/))*

---

## 🚀 Usage / How to Run

You can run the pipeline in two modes: **Web App Dashboard (Interactive)** or **CLI mode (Scripted)**.

### 🌐 Mode A: Web Application Dashboard (Recommended)
Launch the interactive local web server to access the premium graphical user interface:
```bash
python main.py --web
```
By default, the server listens on: **`http://127.0.0.1:8000`**

To customize the port:
```bash
python main.py --web --port 8080
```
Open the URL in any modern browser. You can drag and drop your `.pdf` or `.txt` file, customize questions, hit **"Analyze Document"**, and explore structured summaries, context-grounded Q&A, raw markdown reports, or pretty-printed JSON tabs interactively!

### 💻 Mode B: Command Line Interface (CLI)
Run the pipeline directly from your terminal:

#### Default Run (Uses 3 default QA questions)
```bash
python main.py --file sample_docs/sample.txt
```

#### Custom Questions Run
```bash
python main.py --file sample_docs/sample.txt --questions "Who developed the Antigravity framework?" "What are the core security measures?"
```

#### Model Override & Custom Output Dir
```bash
python main.py --file path/to/document.pdf --model llama-3.3-70b-versatile --output-dir outputs/my_report
```

---

## 🔒 Security Considerations

1. **API Key Isolation**: The application strictly loads the API key from environment variables (`os.getenv("GROQ_API_KEY")`). It is never hardcoded.
2. **Repository Protection**: A thorough `.gitignore` explicitly prevents `.env`, local caches, virtual environments, and generated output files from being committed to version control.
3. **Input Validation & Capping**:
   - Limits file types strictly to `.pdf` and `.txt`.
   - Rejects files exceeding **20MB** prior to parsing to avoid memory overflows.
   - Detects empty (0 bytes) or whitespace-only files and halts immediately with clear messages.
4. **Sanitized Error Logging**: Exception messages and log outputs are checked for API keys or token prefixes (`gsk_`), replacing them with censored placeholders to prevent key leakages in system logs.
5. **LLM Cost & Context Protection**: Limits the pipeline to processing a maximum of **30 chunks**. Large paragraphs are sliced, and excessive inputs trigger truncation warnings to control API billing.
6. **Robust Network Resilience**: Every external Groq call is wrapped in a retry handler with **exponential backoff** (max 3 retries) for transient rate limits (HTTP 429) or network hiccups.

---

## 💡 Approach & Key Design Decisions

- **Why Scikit-Learn TF-IDF?**
  Using dedicated Vector Databases (like Chroma or FAISS) requires large binary dependencies and increases installation failure rates on client machines. TF-IDF paired with Cosine Similarity provides high-quality keyword and semantic-lexical matching at near-zero execution overhead without requiring external databases or downloading heavy local sentence transformer weights (which would block offline runs).
- **Why Heading-Aware Paragraph Chunking?**
  Standard character-slicing splitters break sentences and context mid-phrase. Our chunker searches for logical paragraph breaks (`\n\n`) and preserves layout headings to group similar thoughts, resulting in higher-quality summarization blocks.
- **Why Section-Wise Summaries?**
  Sending a giant text block to an LLM for a general summary often results in the loss of granular details (the "needle in a haystack" problem). Grouping chunks by detected headings and summarizing each section individually ensures the final Markdown report reflects the document's actual structure.

---

## ⚠️ Edge Cases Handled

- **Scanned PDFs**: Triggers an alert and stops processing if no text can be extracted from a PDF.
- **Mislabeled Files**: Detects if a text file has been renamed with a `.pdf` extension by catching structure errors during parsing.
- **Transient API Outages**: Simulates connection dropouts and retries with backoff delays.
- **Oversized Documents**: Restricts processing to safety limits and warns the user about truncation.
- **Missing Section Headers**: Reverts to default page-based indexing or fallback labels if no titles are parsed.

---

## 🚧 Limitations & What I'd Improve

With more development time, I would:
1. **Add a Vector Database**: Integrate ChromaDB or FAISS to support persistent embeddings, enabling cross-document querying and scalable RAG operations.
2. **Add a Web UI**: Build a clean React/Next.js frontend with drag-and-drop file upload capabilities.
3. **Extend File Formats**: Support `.docx`, `.csv`, `.xlsx`, and `.html` extraction.
4. **OCR Capability**: Integrate `pytesseract` or OCR libraries to parse scanned PDF images.
5. **Streaming Output**: Stream the LLM response in real-time to the console or web UI for a better user experience.

---

## 📸 Screenshots and Demo

### CLI Execution
<!-- TODO: Add CLI screenshot here -->

### Generated Markdown Report
<!-- TODO: Add Markdown output screenshot here -->

### Demo Video
- [Watch the Video Demo (Placeholder link)]()

---

## 📂 Sample Output

A sample test document is stored in [sample.txt](file:///e:/Desktop/Projects/intern%20assign%20make%20pdf%20to%20summary/sample_docs/sample.txt). 
Generated pipeline outputs are exported to:
- [result.json](file:///e:/Desktop/Projects/intern%20assign%20make%20pdf%20to%20summary/outputs/result.json)
- [result.md](file:///e:/Desktop/Projects/intern%20assign%20make%20pdf%20to%20summary/outputs/result.md)
