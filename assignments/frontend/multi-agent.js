const api = "/api/multi-agent";
const toggle = document.querySelector("#mode-toggle");
const message = document.querySelector("#message");
const output = document.querySelector("#output");
const decisionFields = document.querySelector("#decision-fields");
let enabled = false;
let currentWorkflow = null;
let busy = false;

function notify(text, isError = false) {
    message.className = `alert alert-${isError ? "warning" : "info"}`;
    message.textContent = text;
}

function updateControls() {
    const active = enabled && toggle.checked && !busy;
    document.querySelector("#run").disabled = !active;
    document.querySelector("#status").disabled = !active;
    document.querySelector("#lookup-form button").disabled = !active;
    decisionFields.disabled = !active || !currentWorkflow || currentWorkflow.human_decision?.status !== "pending";
}

function render(payload, path) {
    output.textContent = JSON.stringify(payload, null, 2);
    currentWorkflow = payload.workflow_id ? payload : payload.latest_workflow || null;
    document.querySelector("#summary").textContent = currentWorkflow
        ? `${currentWorkflow.workflow_id} | ${currentWorkflow.status} | Human decision: ${currentWorkflow.human_decision.status}`
        : payload.workflow_history_count !== undefined
            ? `History records: ${payload.workflow_history_count} | Audit records: ${payload.audit_record_count}`
            : `Response from ${path}`;
    if (currentWorkflow) {
        document.querySelector("#workflow-id").value = currentWorkflow.workflow_id;
        for (const option of document.querySelector("#decision").options) {
            option.disabled = currentWorkflow.status !== "success" && option.value !== "Reject";
        }
        document.querySelector("#decision").value = currentWorkflow.status === "success" ? "Accept" : "Reject";
    }
    updateControls();
}

async function call(path, payload) {
    if (!enabled || !toggle.checked || busy) return;
    busy = true;
    updateControls();
    notify(payload ? "Waiting for the workflow..." : "Loading saved workflow...");
    try {
        const response = await fetch(api + path, {
            method: payload ? "POST" : "GET",
            headers: { "Content-Type": "application/json", "X-Multi-Agent-Mode": "on" },
            body: payload ? JSON.stringify(payload) : undefined,
        });
        const body = await response.json();
        render(body, path);
        if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
        notify("Response received. The reviewer recommendation is not a human approval.");
    } catch (error) {
        notify(error.message || "The Multi-Agent request failed.", true);
    } finally {
        busy = false;
        updateControls();
    }
}

toggle.addEventListener("change", updateControls);
document.querySelector("#workflow-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const payload = { user_request: document.querySelector("#user-request").value.trim() };
    const recordId = document.querySelector("#assignment-id").value;
    if (recordId) payload.record_id = Number(recordId);
    call("/workflow", payload);
});
document.querySelector("#status").addEventListener("click", () => call("/workflow/status"));
document.querySelector("#lookup-form").addEventListener("submit", (event) => {
    event.preventDefault();
    call(`/workflow/${encodeURIComponent(document.querySelector("#workflow-id").value.trim())}`);
});
document.querySelector("#decision-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!currentWorkflow || !window.confirm("Record this human decision? It cannot be changed.")) return;
    call(`/workflow/${currentWorkflow.workflow_id}/decision`, {
        decision: document.querySelector("#decision").value,
        reviewer: document.querySelector("#reviewer").value.trim(),
        reason: document.querySelector("#reason").value.trim(),
        evidence_used: document.querySelector("#evidence-used").value.trim(),
    });
});

async function load() {
    try {
        const [statusResponse, assignmentResponse] = await Promise.all([
            fetch(`${api}/status`), fetch("/assignments"),
        ]);
        const status = await statusResponse.json();
        enabled = Boolean(status.enabled);
        toggle.checked = enabled && localStorage.getItem("assignments_multi_agent_enabled") !== "false";
        toggle.disabled = !enabled;
        if (assignmentResponse.ok) {
            for (const assignment of await assignmentResponse.json()) {
                const option = document.createElement("option");
                option.value = assignment.assignment_id;
                option.textContent = assignment.title;
                document.querySelector("#assignment-id").append(option);
            }
        }
        notify(enabled ? "Ready. Run or load an Assignment workflow." : "Multi-Agent is disabled by configuration.", !enabled);
    } catch {
        notify("The Assignments backend is unavailable.", true);
    }
    toggle.addEventListener("change", () => {
        localStorage.setItem("assignments_multi_agent_enabled", String(toggle.checked));
        updateControls();
    });
    updateControls();
}

load();