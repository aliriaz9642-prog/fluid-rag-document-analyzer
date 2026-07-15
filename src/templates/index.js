// --- Application State ---
let selectedFile = null;
const defaultQuestions = [
    "What is the main topic of this document?",
    "What are the key conclusions or findings?",
    "What recommendations or action items are mentioned?"
];

// --- DOM Elements ---
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const filePreviewBadge = document.getElementById("file-preview-badge");
const fileNameLabel = document.getElementById("file-name-label");
const fileSizeLabel = document.getElementById("file-size-label");
const removeFileBtn = document.getElementById("remove-file-btn");
const uploadForm = document.getElementById("upload-form");
const addQuestionBtn = document.getElementById("add-question-btn");
const questionsListContainer = document.getElementById("questions-list-container");
const analyzeSubmitBtn = document.getElementById("analyze-submit-btn");

const resultsEmptyState = document.getElementById("results-empty-state");
const resultsSuccessState = document.getElementById("results-success-state");
const pipelineLoader = document.getElementById("pipeline-loader");
const loaderTitle = document.getElementById("loader-title");
const loaderSubtitle = document.getElementById("loader-subtitle");
const loaderProgressFill = document.getElementById("loader-progress-fill");
const loaderStepsList = document.getElementById("loader-steps");

const docTitleResult = document.getElementById("doc-title-result");
const docMetaResult = document.getElementById("doc-meta-result");
const summariesContainer = document.getElementById("summaries-container");
const qaContainer = document.getElementById("qa-container");
const markdownCodeContent = document.getElementById("markdown-code-content");
const jsonCodeContent = document.getElementById("json-code-content");

const copyMarkdownBtn = document.getElementById("copy-markdown-btn");
const copyJsonBtn = document.getElementById("copy-json-btn");
const toastContainer = document.getElementById("toast-container");

// --- Initialization ---
document.addEventListener("DOMContentLoaded", () => {
    // 1. Load Initial Questions
    loadDefaultQuestions();
    
    // 2. Setup File Listeners
    setupFileListeners();
    
    // 3. Setup Tab Navigation
    setupTabNavigation();
    
    // 4. Setup Form Submission
    uploadForm.addEventListener("submit", handleFormSubmit);
    
    // 5. Setup Copy Buttons
    copyMarkdownBtn.addEventListener("click", () => copyToClipboard(markdownCodeContent.textContent, "Markdown Report"));
    copyJsonBtn.addEventListener("click", () => copyToClipboard(jsonCodeContent.textContent, "JSON Output"));
});

// --- Dynamic Questions Handling ---
function loadDefaultQuestions() {
    questionsListContainer.replaceChildren(); // Safe clear
    defaultQuestions.forEach(q => addQuestionInput(q));
}

function addQuestionInput(value = "") {
    const qItem = document.createElement("div");
    qItem.classList.add("question-item");
    
    const input = document.createElement("input");
    input.setAttribute("type", "text");
    input.setAttribute("placeholder", "Enter question...");
    input.value = value;
    
    const deleteBtn = document.createElement("button");
    deleteBtn.setAttribute("type", "button");
    deleteBtn.classList.add("delete-question-btn");
    deleteBtn.textContent = "×";
    deleteBtn.addEventListener("click", () => {
        qItem.remove();
        showToast("Question removed", "info");
    });
    
    qItem.appendChild(input);
    qItem.appendChild(deleteBtn);
    questionsListContainer.appendChild(qItem);
}

addQuestionBtn.addEventListener("click", () => {
    addQuestionInput();
    // Scroll list to bottom
    questionsListContainer.scrollTop = questionsListContainer.scrollHeight;
});

// --- File Handling (Upload / Drag-and-Drop) ---
function setupFileListeners() {
    // Dropzone Click
    dropZone.addEventListener("click", () => fileInput.click());
    
    // Browse input selection
    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });
    
    // Drag & Drop event bindings
    ["dragenter", "dragover"].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add("dragover");
        }, false);
    });
    
    ["dragleave", "drop"].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove("dragover");
        }, false);
    });
    
    dropZone.addEventListener("drop", (e) => {
        const dt = e.dataTransfer;
        if (dt.files.length > 0) {
            handleFileSelect(dt.files[0]);
        }
    });
    
    // Remove selected file click
    removeFileBtn.addEventListener("click", () => {
        selectedFile = null;
        fileInput.value = "";
        filePreviewBadge.classList.add("hidden");
        dropZone.classList.remove("hidden");
        
        analyzeSubmitBtn.classList.add("disabled");
        analyzeSubmitBtn.setAttribute("disabled", "true");
        showToast("File removed", "info");
    });
}

function handleFileSelect(file) {
    const ext = file.name.split(".").pop().toLowerCase();
    if (ext !== "pdf" && ext !== "txt") {
        showToast("Unsupported file type! Only .pdf and .txt are supported.", "error");
        return;
    }
    
    const maxSize = 20 * 1024 * 1024; // 20MB
    if (file.size > maxSize) {
        showToast("File is too large! Maximum limit is 20MB.", "error");
        return;
    }
    
    selectedFile = file;
    fileNameLabel.textContent = file.name;
    fileSizeLabel.textContent = formatBytes(file.size);
    
    dropZone.classList.add("hidden");
    filePreviewBadge.classList.remove("hidden");
    
    analyzeSubmitBtn.classList.remove("disabled");
    analyzeSubmitBtn.removeAttribute("disabled");
    
    showToast("File selected successfully", "success");
}

function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
}

// --- Tab Controls ---
function setupTabNavigation() {
    const tabButtons = document.querySelectorAll(".tab-btn");
    const tabPanes = document.querySelectorAll(".tab-pane");
    
    tabButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const targetPaneId = btn.getAttribute("data-tab");
            
            // Toggle active classes on buttons
            tabButtons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            
            // Toggle active classes on panes
            tabPanes.forEach(pane => {
                if (pane.id === targetPaneId) {
                    pane.classList.add("active-pane");
                } else {
                    pane.classList.remove("active-pane");
                }
            });
        });
    });
}

// --- Asynchronous Form Submission & Pipeline Execution ---
async function handleFormSubmit(e) {
    e.preventDefault();
    if (!selectedFile) return;
    
    // Gather dynamic questions
    const questionInputs = questionsListContainer.querySelectorAll(".question-item input");
    const questionList = [];
    questionInputs.forEach(input => {
        const val = input.value.trim();
        if (val) questionList.push(val);
    });
    
    if (questionList.length === 0) {
        showToast("Please provide at least one valid question.", "error");
        return;
    }
    
    // Transition Views
    resultsEmptyState.classList.add("hidden");
    resultsSuccessState.classList.add("hidden");
    pipelineLoader.classList.remove("hidden");
    
    // Start loader simulation logs
    const stopLogsTimer = startLoaderLogsSimulation();
    
    // Prepare multi-part form payload
    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("questions", JSON.stringify(questionList));
    
    try {
        const response = await fetch("/api/analyze", {
            method: "POST",
            body: formData
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || "Server pipeline execution failed.");
        }
        
        // Stop simulator and trigger success loading completion
        stopLogsTimer();
        await completeLoaderLogs();
        
        // Populate results fields
        renderResults(data);
        
        // Switch view to success results card
        pipelineLoader.classList.add("hidden");
        resultsSuccessState.classList.remove("hidden");
        showToast("Analysis completed successfully!", "success");
        
    } catch (err) {
        stopLogsTimer();
        pipelineLoader.classList.add("hidden");
        resultsEmptyState.classList.remove("hidden");
        showToast(err.message, "error");
    }
}

// --- Loader Simulation ---
function startLoaderLogsSimulation() {
    loaderProgressFill.style.width = "5%";
    loaderTitle.textContent = "Initializing Pipeline...";
    loaderSubtitle.textContent = "Reading binary structure...";
    loaderStepsList.replaceChildren(); // clear steps
    
    const steps = [
        "Verifying file parameters",
        "Extracting raw document text",
        "Generating paragraph chunks",
        "Fitting TF-IDF Cosine index",
        "Summarizing section structures",
        "Answering target Q&A queries"
    ];
    
    const stepItems = [];
    steps.forEach((step, idx) => {
        const li = document.createElement("li");
        li.textContent = step;
        li.classList.add(idx === 0 ? "active" : "pending");
        loaderStepsList.appendChild(li);
        stepItems.push(li);
    });
    
    let currentStepIdx = 0;
    let progressVal = 10;
    
    const intervalId = setInterval(() => {
        if (currentStepIdx < steps.length - 1) {
            // Update active/done class
            stepItems[currentStepIdx].classList.remove("active");
            stepItems[currentStepIdx].classList.add("done");
            
            currentStepIdx++;
            stepItems[currentStepIdx].classList.remove("pending");
            stepItems[currentStepIdx].classList.add("active");
            
            progressVal += 12;
            loaderProgressFill.style.width = `${progressVal}%`;
            loaderTitle.textContent = `Running Pipeline Step ${currentStepIdx + 1}/6`;
            loaderSubtitle.textContent = `${steps[currentStepIdx]}...`;
        } else {
            // Cap at 85% until fetch returns
            progressVal = Math.min(85, progressVal + 2);
            loaderProgressFill.style.width = `${progressVal}%`;
            loaderSubtitle.textContent = "Processing Large Language Model calls...";
        }
    }, 1800);
    
    return () => {
        clearInterval(intervalId);
    };
}

async function completeLoaderLogs() {
    loaderProgressFill.style.width = "100%";
    loaderTitle.textContent = "Compilation Finished";
    loaderSubtitle.textContent = "Generating final markdown...";
    
    // Mark all steps as complete
    const steps = loaderStepsList.querySelectorAll("li");
    steps.forEach(li => {
        li.className = "done";
    });
    
    // Add brief visual delay for smooth transition
    return new Promise(resolve => setTimeout(resolve, 800));
}

// --- DOM Rendering Results ---
function renderResults(data) {
    // 1. Banner Info
    docTitleResult.textContent = data.document_name;
    
    const modelStr = data.metadata?.model_used || "llama-3.3-70b-versatile";
    const timeStr = data.metadata?.processing_time || "N/A";
    docMetaResult.textContent = `Processed in ${timeStr} using ${modelStr}`;
    
    // 2. Summary Tab Rendering
    summariesContainer.replaceChildren(); // Clear
    const summaries = data.sections_summary || [];
    
    if (summaries.length === 0) {
        const p = document.createElement("p");
        p.textContent = "No section summaries generated.";
        summariesContainer.appendChild(p);
    } else {
        summaries.forEach(s => {
            const card = document.createElement("article");
            card.classList.add("section-summary-card");
            
            const title = document.createElement("h4");
            title.textContent = s.section_title || "General Section";
            card.appendChild(title);
            
            const ul = document.createElement("ul");
            const points = s.bullet_points || [];
            points.forEach(pt => {
                const li = document.createElement("li");
                li.textContent = pt;
                ul.appendChild(li);
            });
            
            card.appendChild(ul);
            summariesContainer.appendChild(card);
        });
    }
    
    // 3. QA Tab Rendering
    qaContainer.replaceChildren(); // Clear
    const qaResults = data.qa_results || [];
    
    if (qaResults.length === 0) {
        const p = document.createElement("p");
        p.textContent = "No QA results generated.";
        qaContainer.appendChild(p);
    } else {
        qaResults.forEach(item => {
            const card = document.createElement("article");
            card.classList.add("qa-card");
            
            const question = document.createElement("h4");
            question.classList.add("qa-card-question");
            question.textContent = item.question;
            
            const answer = document.createElement("div");
            answer.classList.add("qa-card-answer");
            answer.textContent = item.answer;
            
            const ref = document.createElement("span");
            ref.classList.add("qa-card-ref");
            ref.textContent = `Source context: ${item.source_chunk_reference || "N/A"}`;
            
            card.appendChild(question);
            card.appendChild(answer);
            card.appendChild(ref);
            qaContainer.appendChild(card);
        });
    }
    
    // 4. Raw Code Views Rendering
    markdownCodeContent.textContent = generateMarkdownReportString(data);
    jsonCodeContent.textContent = JSON.stringify(data, null, 2);
}

// Generate raw report markdown representation on Client Side
function generateMarkdownReportString(data) {
    const lines = [];
    lines.push(`# Document Insight Report: ${data.document_name}`);
    lines.push("");
    lines.push("## 📊 Processing Metadata");
    lines.push(`- **File Name**: ${data.document_name}`);
    lines.push(`- **Total logical chunks**: ${data.total_chunks}`);
    lines.push(`- **Model Used**: ${data.metadata?.model_used}`);
    lines.push(`- **Processed At**: ${data.metadata?.timestamp}`);
    lines.push(`- **Total execution time**: ${data.metadata?.processing_time}`);
    lines.push("");
    lines.push("---");
    lines.push("");
    lines.push("## 📝 Section-by-Section Summary");
    lines.push("");
    
    const summaries = data.sections_summary || [];
    summaries.forEach((s, idx) => {
        lines.push(`### 📍 ${s.section_title || `Section ${idx + 1}`}`);
        const points = s.bullet_points || [];
        points.forEach(pt => {
            lines.push(`- ${pt}`);
        });
        lines.push("");
    });
    
    lines.push("---");
    lines.push("");
    lines.push("## ❓ Document Q&A (Fact-Retrieval)");
    lines.push("");
    
    const qa = data.qa_results || [];
    qa.forEach(item => {
        lines.push(`### 💬 Q: ${item.question}`);
        lines.push(`**A**: ${item.answer}`);
        lines.push(`> **Source Reference**: _${item.source_chunk_reference}_`);
        lines.push("");
    });
    
    lines.push("---");
    lines.push("_Report auto-generated by Mini Document Insight Pipeline._");
    return lines.join("\n");
}

// --- Utilities ---
function showToast(message, type = "success") {
    const toast = document.createElement("div");
    toast.classList.add("toast", type);
    
    const icon = document.createElement("span");
    icon.textContent = type === "success" ? "✓" : type === "error" ? "⚠" : "ℹ";
    
    const text = document.createElement("span");
    text.textContent = message;
    
    toast.appendChild(icon);
    toast.appendChild(text);
    toastContainer.appendChild(toast);
    
    // Animate out and delete
    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateX(100%)";
        toast.style.transition = "all 0.4s ease";
        setTimeout(() => toast.remove(), 400);
    }, 4000);
}

function copyToClipboard(text, entityName) {
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
        showToast(`${entityName} copied to clipboard!`, "success");
    }).catch(err => {
        showToast("Failed to copy content to clipboard.", "error");
    });
}
