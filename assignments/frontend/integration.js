const backend = "http://127.0.0.1:5003/integration";
const mcpResult = document.querySelector("#mcp-result");
const ragResult = document.querySelector("#rag-result");

const INSUFFICIENT_EVIDENCE = "Insufficient evidence.";

function showJson(target, body, status = null) {
    const output = document.createElement("pre");
    output.className = "small mb-0 overflow-auto";
    output.textContent = JSON.stringify(body, null, 2);
    target.replaceChildren();
    if (status !== null) {
        const line = document.createElement("p");
        line.className = `small ${status < 400 ? "text-success" : "text-danger"}`;
        line.textContent = `HTTP ${status}`;
        target.append(line);
    }
    target.append(output);
}

function showMessage(target, message, kind = "secondary") {
    const line = document.createElement("p");
    line.className = `text-${kind} mb-0`;
    line.textContent = message;
    target.replaceChildren(line);
}

async function requestJson(path, options = {}) {
    const response = await fetch(`${backend}${path}`, options);
    const body = await response.json().catch(() => ({ error: "Backend returned invalid JSON." }));
    return { response, body };
}

async function loadStatus(kind) {
    const state = document.querySelector(`#${kind}-state`);
    try {
        const { response, body } = await requestJson(`/${kind}/status`);
        if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
        state.textContent = body.enabled ? "Enabled" : "Disabled by configuration";
        document.querySelectorAll(`[data-${kind}-control]`).forEach((control) => {
            control.disabled = !body.enabled;
        });
        return body.enabled;
    } catch {
        state.textContent = "Backend status unavailable";
        document.querySelectorAll(`[data-${kind}-control]`).forEach((control) => {
            control.disabled = true;
        });
        return false;
    }
}

function setMode(mode) {
    for (const name of ["mcp", "rag"]) {
        const active = name === mode;
        document.querySelector(`#${name}-view`).hidden = !active;
        document.querySelector(`#mode-${name}`).checked = active;
    }
}

document.querySelectorAll('input[name="integration-mode"]').forEach((control) => {
    control.addEventListener("change", () => setMode(control.value));
});

const mcpAction = document.querySelector("#mcp-action");
function updateMcpFields() {
    const action = mcpAction.value;
    document.querySelector("#mcp-days-field").hidden = action !== "upcoming";
    document.querySelector("#mcp-id-field").hidden = action !== "get";
}
mcpAction.addEventListener("change", updateMcpFields);
updateMcpFields();

document.querySelector("#mcp-run").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const action = mcpAction.value;
    const body = { action };
    if (action === "upcoming") body.days = Number(document.querySelector("#mcp-days").value);
    if (action === "get") body.assignment_id = Number(document.querySelector("#mcp-id").value);
    button.disabled = true;
    showMessage(mcpResult, "Calling the shared MCP tool...");
    try {
        const { response, body: result } = await requestJson("/mcp/assignments", {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-MCP-Mode": "on" },
            body: JSON.stringify(body),
        });
        showJson(mcpResult, result, response.status);
    } catch {
        showMessage(mcpResult, "The assignments backend could not be reached.", "danger");
    } finally {
        button.disabled = !(await loadStatus("mcp"));
    }
});

function showAnswer(body, status) {
    if (status < 200 || status >= 300 || typeof body.answer !== "string") {
        showJson(ragResult, body, status);
        return;
    }

    const answer = document.createElement("p");
    answer.className = "mb-2";
    const hasEvidence = body.answer.trim() !== INSUFFICIENT_EVIDENCE;
    answer.textContent = hasEvidence
        ? body.answer
        : "The indexed assignment records do not contain enough evidence to answer this question.";

    const confidence = document.createElement("span");
    const level = body.confidence_category || "Unknown";
    const badgeClass = { High: "success", Medium: "warning", Low: "secondary", None: "secondary" }[level] || "secondary";
    confidence.className = `badge text-bg-${badgeClass} me-2`;
    confidence.textContent = `${level} match`;

    const summary = body.retrieval_summary || {};
    const meta = document.createElement("p");
    meta.className = "small text-secondary mb-2";
    meta.append(confidence, document.createTextNode(`${summary.retrieved_count ?? 0} of ${summary.k ?? "?"} records retrieved`));

    ragResult.replaceChildren(answer, meta);
    const citations = Array.isArray(body.citations) ? body.citations : [];
    if (!citations.length) return;
    const heading = document.createElement("h3");
    heading.className = "h6 mt-3";
    heading.textContent = hasEvidence ? "Sources" : "Closest records found";
    const list = document.createElement("ol");
    for (const citation of citations) {
        const item = document.createElement("li");
        item.textContent = citation.title || `${citation.entity || "Record"} ${citation.record_id || ""}`;
        list.append(item);
    }
    ragResult.append(heading, list);
}

function showRetrieved(body, status) {
    if (status < 200 || status >= 300 || !Array.isArray(body.results)) {
        showJson(ragResult, body, status);
        return;
    }

    const statusLine = document.createElement("p");
    statusLine.className = "small text-success";
    statusLine.textContent = `${body.results.length} matching record${body.results.length === 1 ? "" : "s"} (top ${body.k})`;
    ragResult.replaceChildren(statusLine);
    if (!body.results.length) {
        showMessage(ragResult, "No indexed assignment records were close enough to this query.");
        return;
    }

    const list = document.createElement("ol");
    for (const result of body.results) {
        const item = document.createElement("li");
        item.className = "mb-3";
        const title = document.createElement("strong");
        title.textContent = result.title || "Assignment record";
        const match = document.createElement("span");
        match.className = "small text-secondary ms-2";
        match.textContent = `match distance ${result.distance}`;
        const text = document.createElement("p");
        text.className = "small text-secondary mb-0 mt-1";
        text.textContent = result.text || "";
        item.append(title, match, text);
        list.append(item);
    }
    ragResult.append(list);
}

async function runRag(path, payload, render = (body, status) => showJson(ragResult, body, status)) {
    const controls = document.querySelectorAll("[data-rag-control]");
    controls.forEach((control) => { control.disabled = true; });
    showMessage(ragResult, "Contacting the shared RAG service...");
    try {
        const { response, body } = await requestJson(path, {
            method: "POST",
            headers: {
                "X-RAG-Mode": "on",
                ...(payload ? { "Content-Type": "application/json" } : {}),
            },
            ...(payload ? { body: JSON.stringify(payload) } : {}),
        });
        render(body, response.status);
    } catch {
        showMessage(ragResult, "The assignments backend or RAG server could not be reached.", "danger");
    } finally {
        const enabled = await loadStatus("rag");
        controls.forEach((control) => { control.disabled = !enabled; });
    }
}

document.querySelector("#rag-form").addEventListener("submit", (event) => {
    event.preventDefault();
    runRag("/rag/answer", { query: document.querySelector("#rag-query").value }, showAnswer);
});

document.querySelector("#rag-retrieve").addEventListener("click", () => {
    runRag("/rag/retrieve", { query: document.querySelector("#rag-query").value }, showRetrieved);
});

document.querySelector("#rag-ingest").addEventListener("click", () => {
    runRag("/rag/ingest", { service: "assignments" });
});

document.querySelector("#rag-health").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    showMessage(ragResult, "Checking RAG server health...");
    try {
        const { response, body } = await requestJson("/rag/health", {
            headers: { "X-RAG-Mode": "on" },
        });
        showJson(ragResult, body, response.status);
    } catch {
        showMessage(ragResult, "The assignments backend or RAG server could not be reached.", "danger");
    } finally {
        button.disabled = !(await loadStatus("rag"));
    }
});

setMode("mcp");
loadStatus("mcp");
loadStatus("rag");
