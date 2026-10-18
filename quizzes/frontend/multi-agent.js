const backend = "http://localhost:5004/multi-agent";
const toggle = document.querySelector("#mode-toggle");
const message = document.querySelector("#message");
const output = document.querySelector("#output");
const decisionFields = document.querySelector("#decision-fields");
let currentWorkflow = null;
let pendingMutation = null;
let readPending = false;
let resultVersion = 0;

function notify(text, error = false) {
    message.className = `alert alert-${error ? "warning" : "info"}`;
    message.textContent = text;
}

function updateControls() {
    document.querySelector("#run").disabled = Boolean(pendingMutation) || readPending || !toggle.checked;
    document.querySelectorAll("#status, #lookup-form button").forEach((button) => {
        button.disabled = readPending || !toggle.checked
            || Boolean(pendingMutation && pendingMutation !== "/workflow");
    });
    decisionFields.disabled = Boolean(pendingMutation) || readPending || !toggle.checked || !currentWorkflow
        || currentWorkflow.human_decision.status !== "pending";
}

function renderWorkflow(workflow, payload = workflow, path = "/workflow") {
    currentWorkflow = workflow;
    document.querySelector("#summary").textContent = workflow
        ? `${workflow.workflow_id} · ${workflow.status} · Human decision: ${workflow.human_decision.status}`
        : "No workflow recorded yet.";
    document.querySelector("#response-heading").textContent = `Multi-Agent API: /multi-agent${path}`;
    output.textContent = payload ? JSON.stringify(payload, null, 2) : "";
    document.querySelectorAll("#decision option").forEach((option) => {
        option.disabled = workflow?.status !== "success" && option.value !== "Reject";
    });
    document.querySelector("#decision").value = workflow?.status === "success" ? "Accept" : "Reject";
    if (workflow) document.querySelector("#workflow-id").value = workflow.workflow_id;
    updateControls();
}

function renderStatus(payload) {
    renderWorkflow(payload.latest_workflow, payload, "/workflow/status");
    const latest = payload.latest_workflow;
    document.querySelector("#summary").textContent =
        `History records: ${payload.workflow_history_count} · Audit records: ${payload.audit_record_count} · `
        + (latest ? `Latest saved workflow: ${latest.workflow_id} · ${latest.status} · Human decision: ${latest.human_decision.status}`
            : "No workflow recorded yet.");
}

function renderMode() {
    document.querySelector("#mode-state").textContent = toggle.checked ? "ON" : "OFF";
}

async function call(path, payload) {
    const isRead = !payload;
    if (!toggle.checked) return;
    if (isRead ? readPending || (pendingMutation && pendingMutation !== "/workflow")
        : pendingMutation || readPending) return;
    if (isRead) readPending = true;
    else pendingMutation = path;
    const version = resultVersion;
    updateControls();
    notify(isRead ? "Loading saved workflow status…" : "Waiting for the server… Model calls can take a few minutes.");
    try {
        const response = await fetch(backend + path, {
            method: payload ? "POST" : "GET",
            headers: { "Content-Type": "application/json", "X-Multi-Agent-Mode": "on" },
            body: payload ? JSON.stringify(payload) : undefined,
        });
        const body = await response.json();
        if (isRead && version !== resultVersion) return;
        if (!isRead) resultVersion += 1;
        if (body.workflow_id) renderWorkflow(body, body, path);
        else if (response.ok && Object.hasOwn(body, "latest_workflow")) renderStatus(body);
        else renderWorkflow(null, body, path);
        if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
        notify(isRead && pendingMutation === "/workflow"
            ? "Workflow still running. Showing the latest saved workflow; the current run appears after completion."
            : "Response received. Human decisions are recorded separately from model recommendations.");
    } catch (error) {
        if (!isRead || version === resultVersion) {
            notify(error.message || "Request failed. Check workflow status before retrying.", true);
        }
    } finally {
        if (isRead) readPending = false;
        else pendingMutation = null;
        updateControls();
    }
}

toggle.addEventListener("change", () => {
    localStorage.setItem("quizzes_multi_agent_enabled", String(toggle.checked));
    renderMode();
    notify(toggle.checked ? "Multi-Agent mode is on." : "Multi-Agent mode is off.");
    updateControls();
});
document.querySelectorAll("[data-sample-request]").forEach((button) => {
    button.addEventListener("click", () => {
        const input = document.querySelector("#user-request");
        input.value = button.dataset.sampleRequest;
        input.focus();
    });
});
document.querySelector("#workflow-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const quizId = document.querySelector("#quiz-id").value.trim();
    call("/workflow", {
        user_request: document.querySelector("#user-request").value.trim(),
        ...(quizId ? { quiz_id: Number(quizId) } : {}),
    });
});
document.querySelector("#status").addEventListener("click", () => call("/workflow/status"));
document.querySelector("#lookup-form").addEventListener("submit", (event) => {
    event.preventDefault();
    call(`/workflow/${encodeURIComponent(document.querySelector("#workflow-id").value.trim())}`);
});
document.querySelector("#decision-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!currentWorkflow || !window.confirm("Record this final human decision? It cannot be overwritten.")) return;
    call(`/workflow/${currentWorkflow.workflow_id}/decision`, {
        decision: document.querySelector("#decision").value,
        reviewer: document.querySelector("#reviewer").value.trim(),
        reason: document.querySelector("#reason").value.trim(),
        evidence_used: document.querySelector("#evidence-used").value.trim(),
    });
});

async function loadMode() {
    updateControls();
    try {
        const response = await fetch(backend + "/status");
        if (!response.ok) throw new Error("Mode check failed");
        const body = await response.json();
        toggle.checked = body.enabled && localStorage.getItem("quizzes_multi_agent_enabled") !== "false";
        toggle.disabled = !body.enabled;
        notify(body.enabled ? "Ready. Run a workflow or load its status." : "Multi-Agent integration is disabled by the application.");
    } catch {
        notify("The quiz backend is unavailable.", true);
    }
    renderMode();
    updateControls();
}
loadMode();
