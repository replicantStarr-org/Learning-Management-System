/* ---------- multi-agent mode ---------- */

// Ported from the subjects service's Multi-Agent page (subjects/frontend/
// multi-agent.js): the same run, status, lookup and human decision flow, against
// this backend's /api/multi-agent relay. main.js only shows and hides the view.

const backend = "/api/multi-agent";
const STORAGE_KEY = "resources_multi_agent_enabled";

const toggle = document.getElementById("ma-switch");
const modeState = document.getElementById("ma-mode-state");
const message = document.getElementById("ma-message");
const tools = document.getElementById("ma-tools");
const runButton = document.getElementById("ma-run");
const readButtons = document.querySelectorAll("#ma-status, #ma-lookup-form button");
const decisionFields = document.getElementById("ma-decision-fields");
const decisionSelect = document.getElementById("ma-decision");
const resourceSelect = document.getElementById("ma-resource");
const result = document.getElementById("ma-result");
const output = document.getElementById("ma-output");

let available = false;
let currentWorkflow = null;
// One run or decision at a time; reads may overlap a long run so its saved
// progress can be checked, but never another write.
let pendingMutation = null;
let readPending = false;
// Bumped by every write, so a slow read cannot overwrite a newer result.
let resultVersion = 0;

function notify(text, error = false) {
	message.className = `alert alert-${error ? "warning" : "info"}`;
	message.textContent = text;
}

function updateControls() {
	const on = available && toggle.checked;
	tools.disabled = !on;
	runButton.disabled = Boolean(pendingMutation) || readPending;
	for (const button of readButtons) {
		button.disabled = readPending || Boolean(pendingMutation && pendingMutation !== "/workflow");
	}
	decisionFields.disabled = !on || Boolean(pendingMutation) || readPending || !currentWorkflow
		|| currentWorkflow.human_decision?.status !== "pending";
}

function renderMode() {
	modeState.textContent = toggle.checked ? "ON" : "OFF";
	modeState.className = `badge ms-2 ${toggle.checked ? "text-bg-success" : "text-bg-secondary"}`;
}

/* ---------- rendering ---------- */

function element(tag, className, text) {
	const node = document.createElement(tag);
	if (className) node.className = className;
	if (text !== undefined) node.textContent = text;
	return node;
}

// One agent's contribution: its text, or why there is none. Model output is
// shown as text, never as HTML, since it is untrusted.
function agentBlock(label, agentResult, key) {
	const block = element("div", "mb-3");
	const heading = element("p", "rag-answer-label", label);
	if (agentResult?.model) heading.append(element("span", "text-secondary fw-normal text-none ms-2", agentResult.model));
	block.append(heading);

	if (agentResult?.status === "success") {
		block.append(element("div", "rag-answer ma-text", agentResult[key]));
	} else if (agentResult?.status === "error") {
		block.append(element("p", "rag-output-status is-error", agentResult.error));
	} else {
		block.append(element("p", "text-secondary small mb-0", "Skipped: an earlier stage did not complete."));
	}
	return block;
}

function evidenceBlock(evidence) {
	const block = element("div", "mb-3");
	const count = evidence?.evidence_count ?? 0;
	block.append(element("p", "rag-answer-label", `Evidence (${count} ${count === 1 ? "record" : "records"})`));

	const sources = (evidence?.evidence ?? []).map((item) => {
		const title = item.fields?.title ? ` · ${item.fields.title}` : "";
		return element("li", null, `${item.source}${title}`);
	});
	if (sources.length) {
		const list = element("ul", "rag-sources ma-sources");
		list.append(...sources);
		block.append(list);
	}

	const limitations = evidence?.limitations ?? [];
	if (limitations.length) {
		block.append(element("p", "rag-answer-heading mt-2", "Limitations"));
		const list = element("ul", "rag-sources");
		list.append(...limitations.map((text) => element("li", null, text)));
		block.append(list);
	}
	return block;
}

function decisionBlock(decision) {
	const block = element("div");
	block.append(element("p", "rag-answer-label", "Human decision"));
	if (!decision || decision.status === "pending") {
		block.append(element("p", "small mb-0", "Pending. Record a decision below."));
	} else {
		block.append(element("p", "small mb-1", `${decision.status} by ${decision.reviewer} at ${decision.timestamp}`));
		block.append(element("p", "small text-secondary mb-0", decision.reason));
	}
	return block;
}

function renderWorkflow(workflow, payload = workflow, path = "/workflow") {
	currentWorkflow = workflow;
	document.getElementById("ma-route").textContent = backend + path;
	document.getElementById("ma-summary").textContent = workflow
		? `${workflow.workflow_id} · ${workflow.status} · ${workflow.duration_ms} ms · Human decision: ${workflow.human_decision.status}`
		: "No workflow recorded yet.";
	output.textContent = payload ? JSON.stringify(payload, null, 2) : "";

	if (workflow) {
		const children = [];
		if (workflow.error) children.push(element("p", "rag-output-status is-error", workflow.error));
		children.push(
			element("p", "small mb-3", `Task: ${workflow.user_request}`
				+ (workflow.record_id ? ` · Resource ${workflow.record_id}` : " · Whole catalogue")),
			evidenceBlock(workflow.evidence_result),
			agentBlock("Planner", workflow.planner_result, "plan"),
			agentBlock("Worker", workflow.worker_result, "output"),
			agentBlock("Reviewer", workflow.reviewer_result, "review"),
			decisionBlock(workflow.human_decision),
		);
		result.replaceChildren(...children);
		document.getElementById("ma-workflow-id").value = workflow.workflow_id;
	} else {
		result.replaceChildren();
	}

	// A failed workflow can only be rejected, matching the server's rule.
	for (const option of decisionSelect.options) {
		option.disabled = workflow?.status !== "success" && option.value !== "Reject";
	}
	decisionSelect.value = workflow?.status === "success" ? "Accept" : "Reject";
	updateControls();
}

function renderStatus(payload) {
	renderWorkflow(payload.latest_workflow, payload, "/workflow/status");
	const latest = payload.latest_workflow;
	document.getElementById("ma-summary").textContent =
		`History records: ${payload.workflow_history_count} · Audit records: ${payload.audit_record_count} · `
		+ (latest ? `Latest saved workflow: ${latest.workflow_id} · ${latest.status} · Human decision: ${latest.human_decision.status}`
			: "No workflow recorded yet.");
}

/* ---------- requests ---------- */

async function call(path, payload) {
	const isRead = !payload;
	if (!available || !toggle.checked) return;
	if (isRead ? readPending || (pendingMutation && pendingMutation !== "/workflow")
		: pendingMutation || readPending) return;
	if (isRead) readPending = true;
	else pendingMutation = path;
	const version = resultVersion;
	updateControls();
	notify(isRead ? "Loading saved workflow…" : "Waiting for the server… Model calls can take a few minutes.");
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
		if (response.status === 403 && body.enabled === false) {
			disable("Multi-Agent integration is disabled by the application configuration.");
			return;
		}
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

function disable(text) {
	available = false;
	toggle.checked = false;
	toggle.disabled = true;
	renderMode();
	notify(text, true);
	updateControls();
}

/* ---------- wiring ---------- */

toggle.addEventListener("change", () => {
	localStorage.setItem(STORAGE_KEY, String(toggle.checked));
	renderMode();
	notify(toggle.checked ? "Multi-Agent mode is on." : "Multi-Agent mode is off. Turn it on to run workflows.");
	updateControls();
});

for (const button of document.querySelectorAll("[data-ma-sample]")) {
	button.addEventListener("click", () => {
		const input = document.getElementById("ma-request");
		input.value = button.dataset.maSample;
		input.focus();
	});
}

document.getElementById("ma-workflow-form").addEventListener("submit", (event) => {
	event.preventDefault();
	const payload = { user_request: document.getElementById("ma-request").value.trim() };
	if (resourceSelect.value) payload.record_id = Number(resourceSelect.value);
	call("/workflow", payload);
});

document.getElementById("ma-status").addEventListener("click", () => call("/workflow/status"));

document.getElementById("ma-lookup-form").addEventListener("submit", (event) => {
	event.preventDefault();
	call(`/workflow/${encodeURIComponent(document.getElementById("ma-workflow-id").value.trim())}`);
});

document.getElementById("ma-decision-form").addEventListener("submit", (event) => {
	event.preventDefault();
	if (!currentWorkflow || !window.confirm("Record this final human decision? It cannot be overwritten.")) return;
	call(`/workflow/${currentWorkflow.workflow_id}/decision`, {
		decision: decisionSelect.value,
		reviewer: document.getElementById("ma-reviewer").value.trim(),
		reason: document.getElementById("ma-reason").value.trim(),
		evidence_used: document.getElementById("ma-evidence-used").value.trim(),
	});
});

// The same catalogue the shared server's connector reads, so every option is a
// resource the agents can be given.
async function loadResources() {
	try {
		const response = await fetch("/api/resources/catalogue");
		if (!response.ok) return;
		for (const resource of await response.json()) {
			const option = element("option", null, resource.title);
			option.value = resource.l_resource_id;
			resourceSelect.append(option);
		}
	} catch {
		// The whole-catalogue option still works without the list.
	}
}

async function loadMode() {
	updateControls();
	try {
		const response = await fetch(backend + "/status");
		if (!response.ok) throw new Error("Mode check failed");
		const body = await response.json();
		available = Boolean(body.enabled);
		toggle.checked = available && localStorage.getItem(STORAGE_KEY) !== "false";
		toggle.disabled = !available;
		if (available) {
			notify(toggle.checked ? "Ready. Run a workflow or load its status."
				: "Multi-Agent mode is off. Turn it on to run workflows.");
		} else {
			notify("Multi-Agent integration is disabled by the application configuration.", true);
		}
	} catch {
		available = false;
		notify("Multi-Agent availability could not be checked. The backend may be unavailable.", true);
	}
	renderMode();
	updateControls();
}

loadResources();
loadMode();
