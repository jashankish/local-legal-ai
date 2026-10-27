// Local Legal AI — static demo shell.
//
// One page per screen of the Streamlit app, routed on the hash so every deep
// link is a real file request for index.html (no server rewrite needed, which
// is why this can be hosted from a plain static bucket). All state lives in
// memory for the session; only the sign-in is remembered, under a slug-prefixed
// sessionStorage key so it cannot collide with another app on the same origin.

import { createClient } from "./api.js";
import { barChart, horizontalBarChart } from "./charts.js";
import { ENTITY_LABELS } from "./engine/insights.js";

const STORAGE_KEY = "legal-ai-demo:session";

const ACRONYMS = { nda: "NDA", msa: "MSA", sow: "SOW", llc: "LLC", pdf: "PDF" };
const ACTIVITY_LABELS = {
  "query.ask": "Questions asked", "auth.login": "Sign-ins", "document.upload": "Uploads",
  "document.delete": "Deletions", "user.create": "Users created", "analytics.export": "Report exports",
  "audit.verify": "Audit checks", "audit.export": "Audit exports",
  "auth.password_change": "Password changes", "user.update": "User updates",
  "user.password_reset": "Password resets", "integration.test": "Integration tests",
  "access.ip_denied": "Blocked by IP rules",
};

const PAGES = [
  { id: "dashboard", label: "🏠 Dashboard" },
  { id: "upload", label: "📄 Upload Documents" },
  { id: "ask", label: "💬 Ask Documents" },
  { id: "library", label: "📁 Document Library" },
  { id: "analytics", label: "📊 Analytics Dashboard", admin: true },
  { id: "audit", label: "🛡️ Audit Log", admin: true },
  { id: "users", label: "👥 Users", admin: true },
  { id: "integrations", label: "🔌 Integrations", admin: true },
  { id: "account", label: "👤 My Account" },
];

const state = {
  client: null,
  config: null,
  user: null,
  page: "dashboard",
  analyticsTab: "usage",
  chat: [],
  busy: false,
};

/* ── small helpers ──────────────────────────────────────────────────────── */

const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]
));

function prettyLabel(value) {
  return String(value ?? "").replace(/_/g, " ").split(/\s+/).filter(Boolean)
    .map((word) => ACRONYMS[word.toLowerCase()] || word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

const fmtDate = (value) => String(value ?? "").slice(0, 10);
const fmtDateTime = (value) => String(value ?? "").slice(0, 19).replace("T", " ");
const fmtPercent = (value) => `${Math.round((Number(value) || 0) * 100)}%`;
const fmtSeconds = (value) => `${(Number(value) || 0).toFixed(2)}s`;
const fmtKb = (bytes) => `${((Number(bytes) || 0) / 1024).toFixed(1)} KB`;

const stripExtension = (filename) => String(filename).replace(/\.[a-z0-9]+$/i, "");

function fileIcon(filename) {
  const name = String(filename).toLowerCase();
  if (name.endsWith(".pdf")) return "📄";
  if (name.endsWith(".docx") || name.endsWith(".doc")) return "📝";
  if (name.endsWith(".txt")) return "📃";
  return "📄";
}

function toast(message) {
  let stack = document.querySelector(".toast-stack");
  if (!stack) {
    stack = document.createElement("div");
    stack.className = "toast-stack";
    document.body.appendChild(stack);
  }
  const node = document.createElement("div");
  node.className = "toast";
  node.textContent = message;
  stack.appendChild(node);
  setTimeout(() => node.remove(), 4200);
}

function metrics(items) {
  return `<div class="metrics">${items.map((item) => `
    <div>
      <div class="metric-label">${escapeHtml(item.label)}</div>
      <div class="metric-value${item.small ? " sm" : ""}">${escapeHtml(item.value)}</div>
    </div>`).join("")}</div>`;
}

function table(columns, rows, { empty = "Nothing to show." } = {}) {
  if (!rows.length) return `<p class="caption">${escapeHtml(empty)}</p>`;
  return `<div class="table-wrap"><table>
    <thead><tr>${columns.map((column) =>
      `<th class="${column.numeric ? "num" : ""}">${escapeHtml(column.header)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((row) => `<tr>${columns.map((column) => {
      const value = column.value(row);
      return `<td class="${column.numeric ? "num" : ""}${column.wrap ? " wrap" : ""}">${
        column.html ? value : escapeHtml(value)}</td>`;
    }).join("")}</tr>`).join("")}</tbody>
  </table></div>`;
}

function downloadFile(name, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function toCsv(rows) {
  if (!rows.length) return "";
  const headers = Object.keys(rows[0]);
  const cell = (value) => {
    const text = String(value ?? "");
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  return [headers.join(","), ...rows.map((row) => headers.map((key) => cell(row[key])).join(","))].join("\n");
}

/** Mount chart figures into the placeholders a page's HTML left for them. */
function mountCharts(charts) {
  for (const [id, build] of Object.entries(charts)) {
    const slot = document.getElementById(id);
    if (slot) {
      slot.replaceChildren(build());
    }
  }
}

/* ── chrome ─────────────────────────────────────────────────────────────── */

function visiblePages() {
  const isAdmin = state.user && state.user.role === "admin";
  return PAGES.filter((page) => !page.admin || isAdmin);
}

function renderSidebar() {
  const pages = visiblePages();
  return `<aside class="sidebar">
    <div class="sidebar-brand">⚖️ Local Legal AI</div>
    <div class="sidebar-tagline">Private document intelligence for legal teams</div>
    <nav aria-label="Sections">
      <div class="nav-label">Navigate to:</div>
      <ul class="nav">${pages.map((page) => `
        <li><button type="button" data-nav="${page.id}"${
          page.id === state.page ? ' aria-current="page"' : ""}>${escapeHtml(page.label)}</button></li>`).join("")}
      </ul>
    </nav>
    <hr>
    <div class="sidebar-meta"><b>User:</b> ${escapeHtml(state.user.username)}</div>
    <div class="sidebar-meta"><b>Role:</b> ${escapeHtml(prettyLabel(state.user.role))}</div>
    <div style="margin-top:1rem"><button class="btn" data-action="logout">🚪 Logout</button></div>
  </aside>`;
}

/* ── pages ──────────────────────────────────────────────────────────────── */

function loginPage(notice) {
  return `<div class="login-page">
    <div class="main-header">
      <h1>⚖️ Local Legal AI</h1>
      <p>Private, on-premise document intelligence for legal teams</p>
    </div>
    ${notice ? `<div class="note note-warn login-card">${escapeHtml(notice)}</div>` : ""}
    <div class="card login-card">
      <h4 style="margin-top:0">🔐 Sign in</h4>
      <form id="login-form">
        <label class="field"><span>Username</span>
          <input type="text" name="username" autocomplete="username" autocapitalize="none" spellcheck="false" required></label>
        <label class="field"><span>Password</span>
          <input type="password" name="password" autocomplete="current-password" required></label>
        <div id="login-error"></div>
        <button class="btn btn-primary" type="submit" style="width:100%;justify-content:center">Sign in</button>
      </form>
      <p class="caption" style="margin:.9rem 0 0">
        Runs entirely in your browser on fictional sample agreements. Ask the YapperTech team for demo access.
      </p>
    </div>
    <div class="feature-grid">
      <div>🔒 <b>Stays on this machine</b><br><span>Documents, vectors and the model never leave your network.</span></div>
      <div>🧾 <b>Cited answers</b><br><span>Every answer points to the exact passages it came from.</span></div>
      <div>🛡️ <b>Audit trail</b><br><span>Tamper-evident log of every sign-in, upload and question.</span></div>
    </div>
  </div>`;
}

async function dashboardPage() {
  const [library, health] = await Promise.all([
    state.client.listDocuments(),
    state.client.health(),
  ]);
  const services = health.services || {};
  const documents = library.documents || [];
  const recentQuestions = state.chat.slice(-3).reverse();

  const rows = documents.slice(0, 6).map((document) => ({
    Document: document.filename,
    Category: prettyLabel(document.category),
    Type: prettyLabel(document.document_type),
    Passages: document.chunk_count,
    "Uploaded by": document.uploaded_by,
    Uploaded: fmtDate(document.upload_date),
  }));

  return `<h1>🏠 Dashboard</h1>
  <p>Welcome back, <b>${escapeHtml(state.user.username)}</b>. Here's the state of your private document library.</p>
  ${metrics([
    { label: "📚 Documents", value: library.total ?? documents.length },
    { label: "🧩 Indexed passages", value: library.total_chunks ?? 0 },
    { label: "🤖 Answer engine", value: services.model === "healthy" ? "Local LLM" : "Extractive", small: true },
    { label: "🗄️ Vector store", value: services.chromadb === "healthy" ? "Online" : "Offline", small: true },
  ])}

  <h3>🗂️ Recently added</h3>
  ${table([
    { header: "Document", value: (row) => row.Document },
    { header: "Category", value: (row) => row.Category },
    { header: "Type", value: (row) => row.Type },
    { header: "Passages", value: (row) => row.Passages, numeric: true },
    { header: "Uploaded by", value: (row) => row["Uploaded by"] },
    { header: "Uploaded", value: (row) => row.Uploaded },
  ], rows, { empty: "Your library is empty — upload a document to get started." })}

  <h3>⚡ Quick Actions</h3>
  <div class="cols">
    <div>
      <h4>📄 Documents</h4>
      <div class="btn-row">
        <button class="btn btn-primary" data-nav="upload">📄 Upload New Document</button>
        <button class="btn" data-nav="ask">💬 Ask a question</button>
      </div>
    </div>
    <div>
      <h4>📈 Your recent questions</h4>
      ${recentQuestions.length
        ? `<ul style="padding-left:1.1rem;margin:.3rem 0">${recentQuestions.map((entry) =>
            `<li>${escapeHtml(entry.question.length > 70 ? `${entry.question.slice(0, 70)}…` : entry.question)}</li>`).join("")}</ul>`
        : '<p class="caption">No questions yet this session.</p>'}
    </div>
  </div>

  <hr style="border:0;border-top:1px solid var(--line);margin:2rem 0">
  <h3>ℹ️ How it works</h3>
  <div class="cols">
    <div>
      <h4>Under the hood</h4>
      <ul>
        <li>PDF, DOCX and TXT parsing with legal document-type detection</li>
        <li>Clause-aware chunking, MiniLM embeddings in an embedded ChromaDB</li>
        <li>Answers from a local OpenAI-compatible model (vLLM / Ollama)</li>
        <li>JWT sign-in, hash-chained audit log, IP allow-listing</li>
      </ul>
    </div>
    <div>
      <h4>Try asking</h4>
      <ul>
        <li><em>What notice period is required to terminate the agreement?</em></li>
        <li><em>What is the monthly retainer and when is it invoiced?</em></li>
        <li><em>How long do confidentiality obligations last?</em></li>
        <li><em>Which state's law governs the lease?</em></li>
      </ul>
    </div>
  </div>`;
}

function uploadPage() {
  return `<h1>📄 Document Upload</h1>
  <div class="cols cols-wide">
    <div>
      <label class="field"><span>Choose a legal document</span>
        <input type="file" id="upload-file" accept=".txt,.pdf,.docx,.png,.jpg,.jpeg,.tif,.tiff"></label>
      <div id="upload-details"></div>
      <div id="upload-result"></div>
    </div>
    <div>
      <h3 style="margin-top:0">ℹ️ Upload Guidelines</h3>
      <p><b>Supported formats</b></p>
      <ul>
        <li>✅ PDF — scanned pages are read with OCR when Tesseract is installed</li>
        <li>✅ Word (.docx)</li>
        <li>✅ Plain text (.txt)</li>
        <li>✅ Scanned images (PNG, JPEG, TIFF) — read with OCR</li>
      </ul>
      <p><b>What happens on upload</b></p>
      <ul>
        <li>Text is extracted and the document type is detected</li>
        <li>The document is split clause by clause ("Section 1", "Section 2", …)</li>
        <li>Each passage is embedded locally and indexed in ChromaDB</li>
        <li>The upload is recorded in the audit log</li>
      </ul>
      <div class="note note-info">
        <b>In this demo</b> a <code>.txt</code> file is genuinely parsed, split and indexed in your
        browser — upload one, then ask about it on the Ask Documents page. PDF, DOCX and scanned
        images need the server's parsers and OCR.
      </div>
    </div>
  </div>`;
}

async function askPage() {
  const stats = await state.client.documentStats();
  if (!stats.document_count) {
    return `<h1>💬 Ask Your Documents</h1>
      <div class="card"><h4 style="margin-top:0">📭 Nothing to search yet</h4>
      <p class="caption">Answers come only from documents in your library, and it's empty.</p>
      <button class="btn btn-primary" data-nav="upload">📄 Upload documents</button></div>`;
  }

  return `<h1>💬 Ask Your Documents</h1>
  <p class="em">Answers cite the exact passages they come from, with the parties, amounts and deadlines pulled out.</p>
  <div class="cols cols-ask">
    <div>
      <label class="field"><span>Your question</span>
        <textarea id="ask-input" placeholder="e.g., What notice period is required to terminate the services agreement?"></textarea></label>
    </div>
    <div>
      <label class="field"><span>Passages to retrieve: <b id="ask-count">5</b></span>
        <input type="range" id="ask-passages" min="1" max="10" value="5"></label>
      <label class="check"><input type="checkbox" id="ask-suggestions" checked> Suggest follow-ups</label>
      <label class="check"><input type="checkbox" id="ask-entities" checked> Extract key terms</label>
    </div>
  </div>
  <div class="btn-row"><button class="btn btn-primary" data-action="ask">🔍 Submit Query</button></div>
  <div id="ask-live"></div>
  <div id="ask-history">${renderHistory()}</div>`;
}

function renderHistory() {
  if (!state.chat.length) return "";
  const showSuggestions = document.getElementById("ask-suggestions");
  const showEntities = document.getElementById("ask-entities");
  const withSuggestions = !showSuggestions || showSuggestions.checked;
  const withEntities = !showEntities || showEntities.checked;

  const entries = state.chat.slice(-5).reverse().map((entry, index) => {
    const number = state.chat.length - index;
    const title = entry.question.length > 90 ? `${entry.question.slice(0, 90)}…` : entry.question;
    return `<details class="acc"${index === 0 ? " open" : ""}>
      <summary>Q${number}: ${escapeHtml(title)}</summary>
      <div class="acc-body">
        <p class="caption">Asked at: ${escapeHtml(entry.askedAt)}</p>
        ${renderAnswer(entry.result, { withSuggestions, withEntities })}
      </div>
    </details>`;
  }).join("");

  return `<hr style="border:0;border-top:1px solid var(--line);margin:1.8rem 0">${entries}
    <div class="btn-row"><button class="btn" data-action="clear-chat">🗑️ Clear Chat History</button></div>`;
}

function answerModeCaption(result) {
  if (result.mode === "generative") {
    return `Generated by local model <code>${escapeHtml(result.model || "LLM")}</code> from the cited passages.`;
  }
  if (result.mode === "no_match") {
    return "No passage matched the question's terms, so the model wasn't asked — " +
      "answers never come from outside your documents.";
  }
  return "Extractive mode: verbatim passages ranked by relevance (no local model connected).";
}

/** Turn "[1]" markers in an answer into citation chips. */
function withCitationChips(answer) {
  return escapeHtml(answer).replace(/\[(\d+)\]/g, '<span class="cite">$1</span>');
}

function renderAnswer(result, { withSuggestions = true, withEntities = true } = {}) {
  const sources = result.sources || [];
  const cited = new Set(result.citations || []);

  const entities = withEntities && result.legal_entities
    ? Object.entries(result.legal_entities).filter(([, values]) => values && values.length)
    : [];
  const suggestions = withSuggestions ? (result.query_suggestions || []) : [];

  return `
    <h3>🤖 AI Response</h3>
    <div class="answer">${withCitationChips(result.answer)}</div>
    <p class="caption" style="margin-top:.5rem">${answerModeCaption(result)}</p>
    ${metrics([
      { label: "Confidence", value: fmtPercent(result.confidence_score) },
      { label: "Passages consulted", value: sources.length },
      { label: "Response time", value: fmtSeconds(result.processing_time) },
    ])}
    ${entities.length ? `<h3>🏛️ Key Terms in the Cited Passages</h3>
      ${entities.map(([type, values]) => `<div class="terms-row"><b>${escapeHtml(ENTITY_LABELS[type] || prettyLabel(type))}:</b>
        ${values.slice(0, 10).map((value) => `<span class="term">${escapeHtml(value)}</span>`).join("")}</div>`).join("")}` : ""}
    ${suggestions.length ? `<h3>💡 Suggested Follow-ups</h3>
      <div class="suggestions">${suggestions.slice(0, 6).map((suggestion) =>
        `<button class="btn" data-suggest="${escapeHtml(suggestion)}">💭 ${escapeHtml(suggestion)}</button>`).join("")}</div>` : ""}
    ${sources.length ? `<h3>📚 Sources</h3>${sources.map((source, index) => {
      const metadata = source.metadata || {};
      const number = index + 1;
      const content = source.content || source.text || "Content not available";
      const trimmed = content.length <= 600 ? content : `${content.slice(0, 600).replace(/\s\S*$/, "")}…`;
      return `<div class="source">
        <div class="source-head">
          <b>[${number}] ${escapeHtml(metadata.source || source.document_id || "Unknown")}</b>
          · ${escapeHtml(prettyLabel(metadata.category))}
          ${metadata.section ? `· ${escapeHtml(metadata.section)}` : ""}
          · relevance ${(source.similarity_score ?? 0).toFixed(2)}
          · ${cited.has(number) ? '<span class="tag-cited">✅ cited</span>' : '<em class="subtle">retrieved</em>'}
        </div>
        <p class="caption" style="margin:0">${escapeHtml(trimmed)}</p>
      </div>`;
    }).join("")}` : ""}`;
}

async function libraryPage() {
  const [stats, library] = await Promise.all([
    state.client.documentStats(),
    state.client.listDocuments(),
  ]);
  const documents = library.documents || [];
  const search = (state.librarySearch || "").toLowerCase();
  const filtered = search
    ? documents.filter((document) => [document.filename, document.category, document.source]
      .some((field) => String(field || "").toLowerCase().includes(search)))
    : documents;

  const byCategory = new Map();
  for (const document of filtered) {
    const key = document.category || "general";
    if (!byCategory.has(key)) byCategory.set(key, []);
    byCategory.get(key).push(document);
  }

  const groups = [...byCategory.entries()].map(([category, items]) => `
    <details class="acc" open>
      <summary>📁 ${escapeHtml(prettyLabel(category))} (${items.length} ${items.length === 1 ? "file" : "files"})</summary>
      <div class="acc-body">
        <div class="file-grid">${items.map((document) => `
          <div class="file-card">
            <div class="file-icon">${fileIcon(document.filename)}</div>
            <div class="file-name" title="${escapeHtml(document.filename)}">${escapeHtml(
              document.filename.length <= 34 ? document.filename : `${document.filename.slice(0, 32)}…`)}</div>
            <div class="file-meta">
              ${escapeHtml(fmtDate(document.upload_date))}<br>
              ${document.chunk_count} passages${document.ocr ? " · OCR" : ""}${document.via_inbox ? " · via inbox" : ""}<br>
              ID: ${escapeHtml(String(document.id).slice(0, 8))}…
            </div>
            <div class="btn-row">
              <button class="btn btn-sm" data-info="${escapeHtml(document.id)}" title="View info">ℹ️</button>
              <button class="btn btn-sm" data-delete="${escapeHtml(document.id)}" title="Delete file">🗑️</button>
            </div>
          </div>`).join("")}</div>
      </div>
    </details>`).join("");

  return `<h1>📁 Document Library</h1>
  <div class="cols cols-wide">
    <p class="caption">Every document indexed for search and Q&amp;A, grouped by category.</p>
    <label class="field" style="margin:0"><span>🔍 Search files</span>
      <input type="search" id="library-search" value="${escapeHtml(state.librarySearch || "")}"
        placeholder="Search by filename, title or category"></label>
  </div>
  ${metrics([
    { label: "📄 Documents", value: stats.document_count },
    { label: "🧩 Indexed passages", value: stats.chunk_count ?? 0 },
    { label: "💾 Vector store", value: "ChromaDB", small: true },
    { label: "⚡ Status", value: prettyLabel(stats.status), small: true },
  ])}
  <div id="library-detail"></div>
  ${filtered.length ? groups : `<p class="caption">No files match “${escapeHtml(state.librarySearch || "")}”.</p>`}
  <div class="btn-row" style="margin-top:1.4rem">
    <button class="btn" data-action="export-register">📥 Export document register (CSV)</button>
  </div>`;
}

async function analyticsPage() {
  const tabs = [
    ["usage", "📈 Usage Analytics"],
    ["performance", "⚡ Performance"],
    ["similarity", "🔗 Similarity Analysis"],
    ["activity", "👥 User Activity"],
    ["reports", "📋 Reports"],
  ];
  const body = await analyticsTabBody(state.analyticsTab);
  return `<h1>📊 Analytics Dashboard</h1>
  <p class="em">Comprehensive system analytics and insights</p>
  <div class="tabs" role="tablist">${tabs.map(([id, label]) => `
    <button role="tab" data-tab="${id}" aria-selected="${id === state.analyticsTab}">${escapeHtml(label)}</button>`).join("")}</div>
  <div id="analytics-body">${body}</div>`;
}

async function analyticsTabBody(tab) {
  if (tab === "usage") {
    const { data } = await state.client.analytics("usage");
    const query = data.query_analytics;
    const documents = data.document_analytics;
    state.pendingCharts = {
      "chart-trends": () => barChart(
        data.daily_trends.map((row) => ({
          label: new Date(`${row.date}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
          value: row.queries,
        })),
        { title: "Daily Query Volume", xTitle: "Date", yTitle: "Number of Queries",
          labelHeading: "Date", valueHeading: "Queries" }),
      "chart-types": () => horizontalBarChart(
        [...data.top_query_types].sort((a, b) => b.count - a.count)
          .map((row) => ({ label: row.type, value: row.count })),
        { title: "What people ask about", xTitle: "Questions asked",
          labelWidth: 200, labelHeading: "Question type", valueHeading: "Questions" }),
    };
    return `<h2>📈 Usage Analytics</h2>
      ${metrics([
        { label: "Total Queries", value: query.total_queries },
        { label: "Unique Users", value: query.unique_users },
        { label: "Documents Uploaded", value: documents.total_documents },
        { label: "Avg Query Quality", value: query.avg_similarity_score.toFixed(3) },
      ])}
      <h3>📅 Daily Query Trends</h3><div id="chart-trends"></div>
      <h3>📄 Document Analytics</h3>
      <div class="cols">
        <div>
          <div class="panel"><strong>Average File Size:</strong> ${fmtKb(documents.avg_file_size)}</div>
          <div class="panel"><strong>Average Passages per Document:</strong> ${documents.avg_chunks_per_doc}</div>
        </div>
        <div>
          <div class="panel"><strong>Average Ingestion Time:</strong> ${fmtSeconds(documents.avg_processing_time)}</div>
          <div class="panel"><strong>Documents in Library:</strong> ${documents.library_documents}
            (${documents.library_chunks} passages)</div>
        </div>
      </div>
      <h3>🔍 Query Types Distribution</h3><div id="chart-types"></div>`;
  }

  if (tab === "performance") {
    const { data } = await state.client.analytics("performance");
    const bands = { very_fast: "< 0.1 s", fast: "0.1–0.5 s", moderate: "0.5–1 s", slow: "1–2 s", very_slow: "> 2 s" };
    const perfCounts = Object.fromEntries((data.performance_distribution || [])
      .map((row) => [row.category, row.count]));
    const qualityOrder = ["excellent", "good", "fair", "poor", "very_poor"];
    const qualityCounts = Object.fromEntries((data.quality_distribution || [])
      .map((row) => [row.category, row.count]));

    state.pendingCharts = {
      "chart-latency": () => barChart(
        Object.entries(bands).map(([key, label]) => ({ label, value: perfCounts[key] || 0 })),
        { title: "Response Time Distribution", xTitle: "Response time", yTitle: "Number of Queries",
          labelHeading: "Band", valueHeading: "Queries" }),
      "chart-quality": () => barChart(
        qualityOrder.map((key) => ({ label: prettyLabel(key), value: qualityCounts[key] || 0 })),
        { title: "Retrieval Quality (average similarity of retrieved passages)",
          xTitle: "Quality band", yTitle: "Number of Queries",
          labelHeading: "Quality band", valueHeading: "Queries" }),
    };

    return `<h2>⚡ Performance Analytics</h2>
      <h3>🚀 Query Performance Distribution</h3><div id="chart-latency"></div>
      <h3>🎯 Query Quality Distribution</h3><div id="chart-quality"></div>
      <h3>🐌 Slowest Queries</h3>
      ${(data.slowest_queries || []).slice(0, 5).map((row, index) => `
        <details class="acc"><summary>Query ${index + 1} — ${row.processing_time.toFixed(3)}s</summary>
          <div class="acc-body"><p style="margin:0">${escapeHtml(row.query)}</p>
          <p class="caption" style="margin:.4rem 0 0">Similarity score: ${row.similarity_score.toFixed(3)}</p></div>
        </details>`).join("")}
      <h3>💡 Optimization Suggestions</h3>
      ${(data.optimization_suggestions || []).map((suggestion) =>
        `<div class="panel">💡 ${escapeHtml(suggestion)}</div>`).join("")}`;
  }

  if (tab === "similarity") {
    const { data } = await state.client.analytics("similarity");
    const stats = data.overall_stats || {};
    const pairs = (data.similar_document_pairs || []).slice(0, 10);
    state.pendingCharts = {
      "chart-similarity": () => horizontalBarChart(
        pairs.map((row) => ({
          // File names alone, without extensions: the pair is what matters and
          // ".txt ↔ .pdf" adds nothing but width.
          label: `${stripExtension(row.doc1)} ↔ ${stripExtension(row.doc2)}`,
          value: row.similarity,
          display: row.similarity.toFixed(2),
        })),
        { title: "Most similar document pairs", xTitle: "Cosine similarity of document embeddings",
          max: 1, labelWidth: 300, labelHeading: "Document pair", valueHeading: "Similarity" }),
    };
    return `<h2>🔗 Document Similarity Analysis</h2>
      ${metrics([
        { label: "Average Similarity", value: (stats.avg_similarity ?? 0).toFixed(3) },
        { label: "Maximum Similarity", value: (stats.max_similarity ?? 0).toFixed(3) },
        { label: "Total Comparisons", value: stats.total_comparisons ?? 0 },
      ])}
      <h3>🔗 Most Similar Document Pairs</h3><div id="chart-similarity"></div>
      <p class="caption">Highly similar documents may be duplicates, amendments or templates of each other.</p>`;
  }

  if (tab === "activity") {
    const { data } = await state.client.analytics("activity");
    state.pendingCharts = {
      "chart-activity": () => barChart(
        (data.activity_types || []).map((row) => ({
          label: ACTIVITY_LABELS[row.type] || row.type, value: row.count,
        })),
        { title: "What people are doing", xTitle: "Activity", yTitle: "Number of Activities",
          labelHeading: "Activity", valueHeading: "Count" }),
      "chart-hourly": () => barChart(
        Array.from({ length: 24 }, (_, hour) => {
          const key = `${String(hour).padStart(2, "0")}:00`;
          const match = (data.hourly_patterns || []).find((row) => row.hour === key);
          return { label: hour % 3 === 0 ? key : "", value: match ? match.activity_count : 0 };
        }),
        { title: "Activity by Hour of Day (server time)", xTitle: "Hour of Day",
          yTitle: "Activity Count", color: "#3b82f6", labelHeading: "Hour", valueHeading: "Activities" }),
    };
    return `<h2>👥 User Activity Analytics</h2>
      ${metrics([{ label: "Active Users", value: data.active_users ?? 0 }])}
      <h3>📊 Activity Types Distribution</h3><div id="chart-activity"></div>
      <h3>🕐 Hourly Activity Patterns</h3><div id="chart-hourly"></div>
      <h3>🏆 Most Active Users</h3>
      ${(data.top_users || []).slice(0, 5).map((row) =>
        `<div class="panel">👤 <strong>${escapeHtml(row.user_id)}</strong> — ${row.activity_count} activities</div>`).join("")}`;
  }

  return `<h2>📋 Analytics Reports</h2>
    <p>Generate and export a comprehensive analytics report.</p>
    <div class="cols">
      <label class="field"><span>Report Format</span>
        <select id="report-format"><option value="json">json</option></select></label>
      <div style="align-self:end"><button class="btn btn-primary" data-action="generate-report">📥 Generate Report</button></div>
    </div>
    <div id="report-output"></div>`;
}

async function auditPage() {
  const [summary, logs] = await Promise.all([
    state.client.auditSummary(),
    state.client.auditLogs({
      username: state.auditUser || "",
      action: state.auditAction || "All",
      status: state.auditStatus || "All",
    }),
  ]);
  const byStatus = summary.by_status || {};
  const byAction = summary.by_action || {};
  const failures = (byStatus.failure || 0) + (byStatus.denied || 0) + (byStatus.locked || 0);

  const actions = ["All", "auth.login", "document.upload", "document.delete", "query.ask",
    "user.create", "analytics.export", "audit.", "access.ip_denied"];
  const outcomes = ["All", "success", "failure", "denied", "locked"];

  return `<h1>🛡️ Audit Log</h1>
  <p class="em">Every sign-in, upload, question and deletion, hash-chained so edits are detectable.</p>
  ${metrics([
    { label: "Events (30 days)", value: Object.values(byStatus).reduce((sum, count) => sum + count, 0) },
    { label: "Sign-ins", value: byAction["auth.login"] || 0 },
    { label: "Questions", value: byAction["query.ask"] || 0 },
    { label: "Failed / denied / locked", value: failures },
  ])}
  <div class="card">
    <div class="cols cols-wide" style="align-items:center">
      <p style="margin:0"><b>Integrity check</b> — recomputes the SHA-256 chain over every stored event.</p>
      <div><button class="btn" data-action="verify-chain">🔍 Verify chain</button></div>
    </div>
    <div id="verify-result"></div>
  </div>
  <h3>Filter</h3>
  <div class="cols-3">
    <label class="field"><span>User</span>
      <input type="text" id="audit-user" value="${escapeHtml(state.auditUser || "")}" placeholder="e.g. j.ellis"></label>
    <label class="field"><span>Action</span>
      <select id="audit-action">${actions.map((action) =>
        `<option${action === (state.auditAction || "All") ? " selected" : ""}>${action}</option>`).join("")}</select></label>
    <label class="field"><span>Outcome</span>
      <select id="audit-status">${outcomes.map((outcome) =>
        `<option${outcome === (state.auditStatus || "All") ? " selected" : ""}>${outcome}</option>`).join("")}</select></label>
  </div>
  <p class="caption">Showing ${logs.events.length} of ${logs.total} matching events</p>
  ${table([
    { header: "Time (UTC)", value: (event) => fmtDateTime(event.timestamp) },
    { header: "User", value: (event) => event.username || "—" },
    { header: "Action", value: (event) => event.action },
    { header: "Outcome", value: (event) => event.status },
    { header: "Resource", value: (event) => event.resource || "" },
    { header: "IP", value: (event) => event.ip_address || "" },
    { header: "Details", value: (event) => (event.details && Object.keys(event.details).length
      ? JSON.stringify(event.details) : ""), wrap: true },
  ], logs.events, { empty: "No audit events match these filters." })}
  <div class="btn-row"><button class="btn" data-action="export-audit">💾 Export CSV</button></div>`;
}

async function usersPage() {
  const { users } = await state.client.listUsers();
  const roles = ["lawyer", "user", "admin"];
  const selected = state.selectedUser && users.some((user) => user.username === state.selectedUser)
    ? state.selectedUser : users[0].username;
  state.selectedUser = selected;
  const target = users.find((user) => user.username === selected);

  return `<h1>👥 Users</h1>
  <p class="em">Manage who can sign in, what they can do, and reset forgotten passwords.</p>
  ${metrics([
    { label: "Accounts", value: users.length },
    { label: "Active", value: users.filter((user) => user.is_active !== false).length },
    { label: "Administrators", value: users.filter((user) => user.role === "admin").length },
    { label: "Pending password change", value: users.filter((user) => user.must_change_password).length },
  ])}
  ${table([
    { header: "Username", value: (user) => user.username },
    { header: "Email", value: (user) => user.email || "" },
    { header: "Role", value: (user) => prettyLabel(user.role) },
    { header: "Status", value: (user) => (user.is_active !== false ? "Active" : "Disabled") +
      (user.must_change_password ? " · must change password" : "") },
    { header: "Last sign-in", value: (user) => (user.last_login ? fmtDateTime(user.last_login) : "Never") },
    { header: "Created", value: (user) => fmtDate(user.created_at) },
  ], users)}
  <div class="cols">
    <div class="card">
      <h4 style="margin-top:0">➕ Add a user</h4>
      <form id="create-user-form">
        <label class="field"><span>Username</span><input type="text" name="username" placeholder="e.g. j.ellis" required></label>
        <label class="field"><span>Email (optional)</span><input type="text" name="email"></label>
        <label class="field"><span>Role</span><select name="role">${roles.map((role) =>
          `<option value="${role}">${prettyLabel(role)}</option>`).join("")}</select></label>
        <label class="field"><span>Temporary password</span><input type="password" name="password" required></label>
        <label class="check"><input type="checkbox" name="must_change" checked> Require a new password at first sign-in</label>
        <button class="btn btn-primary" type="submit">Create user</button>
      </form>
    </div>
    <div class="card">
      <h4 style="margin-top:0">✏️ Manage a user</h4>
      <label class="field"><span>User</span>
        <select id="manage-user">${users.map((user) =>
          `<option${user.username === selected ? " selected" : ""}>${escapeHtml(user.username)}</option>`).join("")}</select></label>
      <form id="update-user-form">
        <label class="field"><span>Role</span><select name="role">${["admin", "lawyer", "user"].map((role) =>
          `<option value="${role}"${target.role === role ? " selected" : ""}>${prettyLabel(role)}</option>`).join("")}</select></label>
        <label class="check"><input type="checkbox" name="is_active"${target.is_active !== false ? " checked" : ""}> Account active</label>
        <label class="field"><span>Email</span><input type="text" name="email" value="${escapeHtml(target.email || "")}"></label>
        <button class="btn btn-primary" type="submit">Save changes</button>
      </form>
      <form id="reset-password-form" style="margin-top:1rem">
        <label class="field"><span>Temporary password for ${escapeHtml(selected)}</span>
          <input type="password" name="password" required></label>
        <button class="btn" type="submit">Reset password</button>
      </form>
      <p class="caption">Disabling an account, changing its role or resetting its password signs that user out everywhere.</p>
    </div>
  </div>`;
}

async function integrationsPage() {
  const status = await state.client.integrationsStatus();
  const inbox = status.inbox || {};
  const notifications = status.notifications || {};
  const n8n = notifications.n8n || {};
  const slack = notifications.slack || {};

  return `<h1>🔌 Integrations</h1>
  <p class="em">Automatic ingestion from a watched folder, and event notifications to n8n and Slack.</p>
  <div class="card">
    <div class="cols cols-wide" style="align-items:start">
      <div>
        <h4 style="margin-top:0">📥 Watched inbox folder</h4>
        <p class="caption" style="margin:0">Checking <code>${escapeHtml(inbox.inbox_dir || "data/inbox")}</code>
          every ${Math.round(inbox.interval_seconds || 0)}s. Drop PDF, DOCX or TXT files in it — or in a
          sub-folder named after a category, e.g. <code>contracts/</code> — and they are indexed automatically.</p>
      </div>
      <div><button class="btn" data-action="scan-inbox">🔄 Scan now</button></div>
    </div>
    ${metrics([
      { label: "Indexed", value: inbox.processed ?? 0 },
      { label: "Failed", value: inbox.failed ?? 0 },
      { label: "Waiting", value: inbox.waiting ?? 0 },
      { label: "Last check", value: String(inbox.last_scan || "—").slice(11, 19) || "—", small: true },
    ])}
    ${table([
      { header: "Time", value: (row) => fmtDateTime(row.timestamp) },
      { header: "File", value: (row) => row.file },
      { header: "Category", value: (row) => prettyLabel(row.category) },
      { header: "Result", value: (row) => (row.ok ? `✅ ${row.passages} passages` : `❌ ${row.error}`) },
      { header: "Moved to", value: (row) => row.moved_to || "" },
    ], inbox.recent || [], { empty: "No files processed since the server started." })}
  </div>
  <div class="card">
    <div class="cols cols-wide" style="align-items:start">
      <div>
        <h4 style="margin-top:0">📣 Event notifications</h4>
        <p class="caption" style="margin:0">Uploads, deletions, user changes and security events are sent as JSON
          to n8n and/or as messages to Slack. Only metadata is sent — never document text or questions.</p>
      </div>
      <div><button class="btn" data-action="test-integration">📨 Send test event</button></div>
    </div>
    <div id="integration-result"></div>
    <div class="cols" style="margin-top:1rem">
      <div class="note note-ok"><b>n8n webhook:</b> ${escapeHtml(n8n.target || "not configured")}
        ${n8n.signed ? " · signed (HMAC-SHA256)" : ""}</div>
      <div class="note note-ok"><b>Slack:</b> ${escapeHtml(slack.target || "not configured")}</div>
    </div>
    <p><b>Events sent:</b> ${(notifications.events || []).map((event) =>
      `<code>${escapeHtml(event)}</code>`).join(" ")}</p>
    ${table([
      { header: "Time (UTC)", value: (row) => fmtDateTime(row.timestamp) },
      { header: "Event", value: (row) => row.event },
      { header: "Target", value: (row) => row.target },
      { header: "Result", value: (row) => (row.ok ? "✅ delivered" : `❌ ${row.error}`) },
      { header: "Attempts", value: (row) => row.attempts, numeric: true },
    ], notifications.recent_deliveries || [])}
    <p class="caption">Ready-made n8n workflows (Slack alerts, drop-zone ingestion, daily digest) ship in
      <code>workflows/n8n/</code>.</p>
  </div>`;
}

function accountPage() {
  const previous = state.user.previous_login;
  return `<h1>👤 My Account</h1>
  ${metrics([
    { label: "Username", value: state.user.username, small: true },
    { label: "Role", value: prettyLabel(state.user.role), small: true },
    { label: "Previous sign-in", value: previous ? fmtDateTime(previous).slice(0, 16) : "First sign-in", small: true },
  ])}
  ${state.user.email ? `<p class="caption">Email: ${escapeHtml(state.user.email)}</p>` : ""}
  <h3>🔑 Change password</h3>
  <p class="caption">Changing your password signs out every other session for your account.</p>
  <div class="card" style="max-width:430px">
    <form id="change-password-form">
      <label class="field"><span>Current password</span><input type="password" name="current" required></label>
      <label class="field"><span>New password</span><input type="password" name="next" required></label>
      <label class="field"><span>Confirm new password</span><input type="password" name="confirm" required></label>
      <button class="btn btn-primary" type="submit">Update password</button>
    </form>
    <div id="password-result"></div>
  </div>`;
}

/* ── rendering ──────────────────────────────────────────────────────────── */

const PAGE_BUILDERS = {
  dashboard: dashboardPage,
  upload: uploadPage,
  ask: askPage,
  library: libraryPage,
  analytics: analyticsPage,
  audit: auditPage,
  users: usersPage,
  integrations: integrationsPage,
  account: accountPage,
};

async function render() {
  const root = document.getElementById("app");
  if (!state.user) {
    root.innerHTML = loginPage(state.notice);
    document.getElementById("login-form").addEventListener("submit", onLogin);
    return;
  }

  if (!visiblePages().some((page) => page.id === state.page)) state.page = "dashboard";
  state.pendingCharts = null;

  root.innerHTML = `<div class="shell">${renderSidebar()}<main class="main" id="main"></main></div>`;
  const main = document.getElementById("main");
  main.innerHTML = '<p class="caption">Loading…</p>';

  try {
    main.innerHTML = await PAGE_BUILDERS[state.page]();
  } catch (error) {
    main.innerHTML = `<div class="note note-err">Could not load this page: ${escapeHtml(error.message)}</div>`;
    return;
  }

  if (state.pendingCharts) mountCharts(state.pendingCharts);
  wirePage();
  document.title = `${PAGES.find((page) => page.id === state.page).label.replace(/^\S+\s/, "")} — Local Legal AI`;
}

function navigate(page) {
  state.page = page;
  window.location.hash = `#/${page}`;
}

/* ── interaction ────────────────────────────────────────────────────────── */

async function onLogin(event) {
  event.preventDefault();
  const form = event.target;
  const target = document.getElementById("login-error");
  target.innerHTML = '<p class="caption">Authenticating…</p>';
  try {
    const result = await state.client.login(form.username.value.trim(), form.password.value);
    state.user = result.user;
    state.client.username = result.user.username;
    state.notice = null;
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(result.user));
    } catch { /* private mode: the session simply isn't remembered */ }
    navigate("dashboard");
    await render();
  } catch (error) {
    target.innerHTML = `<div class="note note-err">❌ ${escapeHtml(error.message)}</div>`;
  }
}

function signOut() {
  state.user = null;
  state.chat = [];
  try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* nothing to clear */ }
  render();
}

async function runQuery(question) {
  if (!question.trim() || state.busy) return;
  state.busy = true;
  const live = document.getElementById("ask-live");
  const passages = Number((document.getElementById("ask-passages") || {}).value || 5);

  live.innerHTML = `<p><b>Q: ${escapeHtml(question)}</b></p>
    <div class="answer"><span id="ask-stream" class="streaming"></span></div>`;

  try {
    const result = await state.client.query(question, passages);
    // The product streams the answer token by token; mirror that here so the
    // demo behaves the way the real UI does.
    await typeOut(document.getElementById("ask-stream"), result.answer);
    state.chat.push({
      question,
      result,
      askedAt: new Date().toISOString().slice(0, 19).replace("T", " "),
    });
    live.innerHTML = "";
    document.getElementById("ask-history").innerHTML = renderHistory();
    const input = document.getElementById("ask-input");
    if (input) input.value = "";
  } catch (error) {
    live.innerHTML = `<div class="note note-err">${escapeHtml(error.message)}</div>`;
  } finally {
    state.busy = false;
  }
}

const TYPE_DURATION_MS = 900;

/**
 * Reveal the answer word by word, the way the product streams tokens.
 * Driven by elapsed time rather than a tick count, so a throttled background
 * tab (or a slow frame) finishes in the same ~900ms instead of crawling.
 */
function typeOut(node, text) {
  if (!node) return Promise.resolve();
  const words = text.split(" ");
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    node.textContent = text;
    node.classList.remove("streaming");
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const started = performance.now();
    // setTimeout rather than requestAnimationFrame: a background tab stops
    // painting frames entirely, which would leave the answer half-written.
    // Timers still fire there (throttled), and progress is measured in elapsed
    // time, so a throttled tab simply completes on its first late tick.
    const step = () => {
      const progress = Math.min(1, (performance.now() - started) / TYPE_DURATION_MS);
      node.textContent = words.slice(0, Math.max(1, Math.ceil(progress * words.length))).join(" ");
      if (progress >= 1) {
        node.classList.remove("streaming");
        resolve();
      } else {
        setTimeout(step, 16);
      }
    };
    step();
  });
}

async function handleUploadFile(file) {
  const details = document.getElementById("upload-details");
  if (!file) {
    details.innerHTML = "";
    return;
  }
  const isText = file.type === "text/plain" || file.name.toLowerCase().endsWith(".txt");
  const preview = isText ? (await file.text()).slice(0, 500) : null;

  details.innerHTML = `<h3>📋 Document Details</h3>
    <label class="field"><span>Document Title</span>
      <input type="text" id="upload-title" value="${escapeHtml(file.name)}"></label>
    <label class="field"><span>Category</span>
      <select id="upload-category">${["general", "contracts", "employment", "nda", "real_estate", "litigation", "corporate"]
        .map((category) => `<option value="${category}">${prettyLabel(category)}</option>`).join("")}</select></label>
    ${preview !== null ? `<h3>👀 Document Preview</h3>
      <textarea readonly style="min-height:150px">${escapeHtml(preview)}${
        preview.length >= 500 ? "…" : ""}</textarea>` : ""}
    <div class="btn-row" style="margin-top:.8rem">
      <button class="btn btn-primary" data-action="do-upload">🚀 Upload and Process</button></div>`;
  state.uploadFile = file;
}

async function doUpload() {
  const file = state.uploadFile;
  const output = document.getElementById("upload-result");
  if (!file) return;
  output.innerHTML = '<p class="caption">Processing document…</p>';

  const isText = file.type === "text/plain" || file.name.toLowerCase().endsWith(".txt");
  try {
    const result = await state.client.uploadDocument({
      file,
      text: isText ? await file.text() : null,
      filename: file.name,
      title: document.getElementById("upload-title").value || file.name,
      category: document.getElementById("upload-category").value,
      contentType: file.type,
    });
    output.innerHTML = `<div class="note note-ok">✅ Document uploaded successfully!</div>
      <div class="panel"><strong>Document ID:</strong> ${escapeHtml(result.document_id)}</div>
      <div class="panel"><strong>Passages indexed:</strong> ${result.chunks_processed}</div>
      <div class="panel"><strong>Processing time:</strong> ${fmtSeconds(result.processing_time)}</div>
      <div class="btn-row" style="margin-top:.8rem">
        <button class="btn btn-primary" data-nav="ask">💬 Ask about it</button>
        <button class="btn" data-nav="library">📁 Open the library</button></div>`;
  } catch (error) {
    output.innerHTML = `<div class="note note-warn">${escapeHtml(error.message)}</div>`;
  }
}

async function generateReport() {
  const output = document.getElementById("report-output");
  output.innerHTML = '<p class="caption">Generating…</p>';
  const report = await state.client.report();
  const usage = report.usage_analytics || {};
  const query = usage.query_analytics || {};
  const documents = usage.document_analytics || {};
  state.lastReport = report;

  output.innerHTML = `<div class="note note-ok">✅ Report generated successfully!</div>
    <details class="acc"><summary>📄 Report Summary</summary><div class="acc-body">
      <pre class="mono" style="white-space:pre-wrap;margin:0">${escapeHtml(JSON.stringify({
        generated_at: report.generated_at,
        report_type: report.report_type,
        sections: Object.keys(report),
      }, null, 2))}</pre></div></details>
    <div class="btn-row"><button class="btn" data-action="download-report">💾 Download Full Report</button></div>
    <h3>🔍 Key Insights</h3>
    <div class="panel">📊 Total questions: ${query.total_queries ?? 0}</div>
    <div class="panel">⚡ Average processing time: ${(query.avg_processing_time ?? 0).toFixed(3)}s</div>
    <div class="panel">🎯 Average similarity score: ${(query.avg_similarity_score ?? 0).toFixed(3)}</div>
    <div class="panel">📄 Documents in library: ${documents.library_documents ?? 0}</div>
    <div class="panel">🧩 Average passages per document: ${documents.avg_chunks_per_doc ?? 0}</div>`;
}

/**
 * Delegated handlers, bound once to the app root. They must live above #main:
 * the sidebar's navigation and sign-out sit outside it, and binding per render
 * would stack a new listener on every page change.
 */
function wireGlobal() {
  const main = document.getElementById("app");

  main.addEventListener("click", async (event) => {
    const button = event.target.closest("button, [data-nav]");
    if (!button) return;

    if (button.dataset.nav) { navigate(button.dataset.nav); await render(); return; }
    if (button.dataset.suggest) {
      const input = document.getElementById("ask-input");
      if (input) { input.value = button.dataset.suggest; input.focus(); input.scrollIntoView({ block: "center" }); }
      return;
    }
    if (button.dataset.tab) {
      state.analyticsTab = button.dataset.tab;
      await render();
      return;
    }
    if (button.dataset.info) {
      const library = await state.client.listDocuments();
      const document_ = library.documents.find((candidate) => candidate.id === button.dataset.info);
      document.getElementById("library-detail").innerHTML = `<div class="note note-info">
        <b>File:</b> ${escapeHtml(document_.filename)}<br>
        <b>Title:</b> ${escapeHtml(document_.source)}<br>
        <b>Category:</b> ${escapeHtml(prettyLabel(document_.category))} ·
        <b>Type:</b> ${escapeHtml(prettyLabel(document_.document_type))}<br>
        <b>Words:</b> ${document_.word_count} · <b>Passages:</b> ${document_.chunk_count}<br>
        <b>Uploaded:</b> ${escapeHtml(fmtDateTime(document_.upload_date))} by ${escapeHtml(document_.uploaded_by)}<br>
        <b>ID:</b> <code>${escapeHtml(document_.id)}</code></div>`;
      return;
    }
    if (button.dataset.delete) {
      if (button.dataset.confirmed === "yes") {
        await state.client.deleteDocument(button.dataset.delete);
        toast("Document deleted from the index.");
        await render();
      } else {
        button.dataset.confirmed = "yes";
        button.textContent = "Confirm?";
        button.classList.add("btn-primary");
      }
      return;
    }

    const action = button.dataset.action;
    if (!action) return;

    if (action === "logout") signOut();
    else if (action === "ask") await runQuery(document.getElementById("ask-input").value);
    else if (action === "clear-chat") { state.chat = []; await render(); }
    else if (action === "do-upload") await doUpload();
    else if (action === "generate-report") await generateReport();
    else if (action === "download-report") {
      downloadFile(`analytics_report_${Date.now()}.json`, JSON.stringify(state.lastReport, null, 2), "application/json");
    } else if (action === "export-register") {
      const { documents } = await state.client.listDocuments();
      downloadFile(`document_register_${new Date().toISOString().slice(0, 10)}.csv`, toCsv(documents.map((row) => ({
        "Document ID": row.id, "File name": row.filename, Title: row.source,
        Category: prettyLabel(row.category), Type: prettyLabel(row.document_type),
        Words: row.word_count, Passages: row.chunk_count,
        "Uploaded by": row.uploaded_by, Uploaded: fmtDateTime(row.upload_date),
      }))), "text/csv");
    } else if (action === "export-audit") {
      const logs = await state.client.auditLogs({
        username: state.auditUser || "", action: state.auditAction || "All", status: state.auditStatus || "All",
      });
      downloadFile(`audit_log_${new Date().toISOString().slice(0, 10)}.csv`, toCsv(logs.events.map((event) => ({
        Timestamp: event.timestamp, User: event.username || "", Action: event.action,
        Outcome: event.status, Resource: event.resource || "", IP: event.ip_address || "",
        Details: event.details ? JSON.stringify(event.details) : "",
      }))), "text/csv");
    } else if (action === "verify-chain") {
      const target = document.getElementById("verify-result");
      target.innerHTML = '<p class="caption">Recomputing the chain…</p>';
      const result = await state.client.auditVerify();
      target.innerHTML = result.valid
        ? `<div class="note note-ok">Intact — ${result.checked} events verified</div>`
        : `<div class="note note-err">Tampering detected at event #${result.first_invalid_id}</div>`;
    } else if (action === "scan-inbox") {
      const result = await state.client.scanInbox();
      toast(`Scan complete — indexed ${result.counts.processed}, failed ${result.counts.failed}.`);
    } else if (action === "test-integration") {
      const target = document.getElementById("integration-result");
      target.innerHTML = '<p class="caption">Sending…</p>';
      const result = await state.client.testIntegration();
      target.innerHTML = result.deliveries.map((delivery) => delivery.ok
        ? `<div class="note note-ok">${escapeHtml(delivery.target)}: delivered (HTTP ${delivery.status_code})</div>`
        : `<div class="note note-err">${escapeHtml(delivery.target)}: failed — ${escapeHtml(delivery.error)}</div>`).join("");
    }
  });

  main.addEventListener("change", async (event) => {
    const node = event.target;
    if (node.id === "upload-file") await handleUploadFile(node.files[0]);
    else if (node.id === "manage-user") { state.selectedUser = node.value; await render(); }
    else if (node.id === "audit-action") { state.auditAction = node.value; await render(); }
    else if (node.id === "audit-status") { state.auditStatus = node.value; await render(); }
    else if (node.id === "ask-suggestions" || node.id === "ask-entities") {
      document.getElementById("ask-history").innerHTML = renderHistory();
    }
  });

  // Search and the audit user filter re-render on a pause, not on every
  // keystroke. "input" rather than "keyup" so pasting, the clear button and
  // autofill all count as typing.
  let debounce;
  main.addEventListener("input", (event) => {
    const node = event.target;
    if (node.id === "ask-passages") {
      document.getElementById("ask-count").textContent = node.value;
      return;
    }
    if (node.id !== "library-search" && node.id !== "audit-user") return;
    clearTimeout(debounce);
    const value = node.value;
    const caret = node.selectionStart;
    debounce = setTimeout(async () => {
      if (node.id === "library-search") state.librarySearch = value;
      else state.auditUser = value;
      await render();
      const restored = document.getElementById(node.id);
      if (restored) { restored.focus(); restored.setSelectionRange(caret, caret); }
    }, 320);
  });

  main.addEventListener("keydown", (event) => {
    if (event.target.id === "ask-input" && (event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      runQuery(event.target.value);
    }
  });

}

/** Handlers that must attach to the freshly rendered elements of one page. */
function wirePage() {
  const createUser = document.getElementById("create-user-form");
  if (createUser) {
    createUser.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.target;
      try {
        await state.client.createUser({
          username: form.username.value.trim(),
          email: form.email.value.trim(),
          role: form.role.value,
          password: form.password.value,
          must_change_password: form.must_change.checked,
        });
        toast(`Created ${form.username.value.trim()}.`);
        await render();
      } catch (error) { toast(error.message); }
    });
  }

  const updateUser = document.getElementById("update-user-form");
  if (updateUser) {
    updateUser.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.target;
      const result = await state.client.updateUser(state.selectedUser, {
        role: form.role.value, is_active: form.is_active.checked, email: form.email.value.trim(),
      });
      toast(result.message);
      await render();
    });
  }

  const resetPassword = document.getElementById("reset-password-form");
  if (resetPassword) {
    resetPassword.addEventListener("submit", async (event) => {
      event.preventDefault();
      const result = await state.client.resetPassword(state.selectedUser, event.target.password.value);
      toast(result.message);
      event.target.reset();
    });
  }

  const changePassword = document.getElementById("change-password-form");
  if (changePassword) {
    changePassword.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.target;
      const output = document.getElementById("password-result");
      if (form.next.value !== form.confirm.value) {
        output.innerHTML = '<div class="note note-err">The new passwords don\'t match.</div>';
        return;
      }
      await state.client.changePassword(form.current.value, form.next.value);
      output.innerHTML = '<div class="note note-ok">Password updated. Other sessions have been signed out.</div>';
      form.reset();
    });
  }
}

/* ── boot ───────────────────────────────────────────────────────────────── */

function readHash() {
  const match = window.location.hash.match(/^#\/([a-z-]+)/);
  return match && PAGE_BUILDERS[match[1]] ? match[1] : "dashboard";
}

export async function start(config) {
  state.config = config;
  const banner = document.getElementById("demo-banner");
  if (banner && config.apiBaseUrl) banner.remove();

  try {
    state.client = await createClient(config);
  } catch (error) {
    document.getElementById("app").innerHTML =
      `<div class="login-page"><div class="note note-err">Could not start the demo: ${
        escapeHtml(error.message)}</div></div>`;
    return;
  }

  try {
    const saved = sessionStorage.getItem(STORAGE_KEY);
    if (saved && state.client.mode === "demo") {
      state.user = JSON.parse(saved);
      state.client.username = state.user.username;
    }
  } catch { /* no stored session */ }

  wireGlobal();
  state.page = readHash();
  window.addEventListener("hashchange", async () => {
    const page = readHash();
    if (page !== state.page) { state.page = page; await render(); }
  });

  await render();
}
