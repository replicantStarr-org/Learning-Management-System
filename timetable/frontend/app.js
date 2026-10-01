function getUsernameCookie() {
    const match = document.cookie.match(/(?:^|;\s*)username=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
}

const queryParams = new URLSearchParams(window.location.search);
const pageMessage = document.querySelector("#page-message");

if (pageMessage && queryParams.has("message")) {
    pageMessage.textContent = queryParams.get("message");
    pageMessage.hidden = false;

    const cleanUrl = new URL(window.location.href);
    cleanUrl.searchParams.delete("message");
    window.history.replaceState({}, "", cleanUrl);
}

const username = getUsernameCookie();

document.querySelectorAll("[data-username-field]").forEach((field) => {
    field.value = username;
});

function addOneHour(hhmm) {
    const [hours, minutes] = hhmm.split(":").map(Number);
    const total = (hours * 60 + minutes + 60) % (24 * 60);
    return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

const dateField = document.querySelector('#date[type="date"]');
if (dateField && !dateField.value) {
    dateField.value = queryParams.get("date") || new Date().toISOString().slice(0, 10);
}
const startField = document.querySelector('#start_time[type="time"]');
if (startField && !startField.value) {
    startField.value = queryParams.get("start_time") || "08:00";
}
const endField = document.querySelector('#end_time[type="time"]');
if (endField && !endField.value) {
    endField.value = queryParams.get("end_time") || (startField ? addOneHour(startField.value) : "09:00");
}

function syncEndTimeMin(scope) {
    scope.querySelectorAll('input[name="start_time"]').forEach((startInput) => {
        const endInput = startInput.closest("form")?.querySelector('input[name="end_time"]');
        if (endInput && startInput.value) endInput.min = startInput.value;
    });
}
syncEndTimeMin(document);

document.addEventListener("input", (event) => {
    if (!event.target.matches('input[name="start_time"]')) return;
    const endInput = event.target.closest("form")?.querySelector('input[name="end_time"]');
    if (!endInput) return;
    endInput.min = event.target.value;
    if (endInput.value && endInput.value <= event.target.value) endInput.value = "";
    if (!endInput.value && event.target.value) endInput.value = addOneHour(event.target.value);
});

const CAL_PX_PER_HOUR = 56;
const CAL_START_HOUR = 8;
const CAL_END_HOUR = 23;

function minutesToTimeString(totalMinutes) {
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

document.addEventListener("click", (event) => {
    const dayCol = event.target.closest(".cal-day-col");
    if (!dayCol || event.target.closest(".cal-entry") || dayCol.closest("#ai-plan-modal-body")) return;

    const date = dayCol.dataset.date;
    if (!date) return;

    const offsetY = event.clientY - dayCol.getBoundingClientRect().top;
    const rawMinutes = CAL_START_HOUR * 60 + (offsetY / CAL_PX_PER_HOUR) * 60;
    const startMinutes = Math.max(
        CAL_START_HOUR * 60,
        Math.min(Math.round(rawMinutes / 30) * 30, CAL_END_HOUR * 60 - 30)
    );
    const endMinutes = Math.min(startMinutes + 60, CAL_END_HOUR * 60);

    const params = new URLSearchParams({
        date,
        start_time: minutesToTimeString(startMinutes),
        end_time: minutesToTimeString(endMinutes),
    });
    window.location.href = `/create.html?${params.toString()}`;
});

function startElapsedTimer(formSelector, counterSelector, onStart) {
    const form = document.querySelector(formSelector);
    if (!form) return;

    let timer = null;
    form.addEventListener("htmx:beforeRequest", () => {
        onStart?.();
        const start = Date.now();
        clearInterval(timer);
        timer = setInterval(() => {
            const counter = document.querySelector(counterSelector);
            if (!counter) {
                clearInterval(timer);
                return;
            }
            counter.textContent = Math.round((Date.now() - start) / 1000);
        }, 1000);
    });
    form.addEventListener("htmx:afterRequest", () => clearInterval(timer));
}

startElapsedTimer("#ai-advice-form", "#advice-elapsed");

startElapsedTimer("#ai-plan-form", "#plan-elapsed", () => {
    const modalBody = document.querySelector("#ai-plan-modal-body");
    if (!modalBody) return;
    modalBody.innerHTML = `
        <div class="text-center py-5" role="status">
            <span class="spinner-border text-primary"></span>
            <p class="text-secondary mt-2">Generating your optimised plan… usually 1-2 minutes on this hardware.</p>
            <p class="text-secondary small"><span id="plan-elapsed">0</span>s elapsed</p>
        </div>
    `;
});

function htmxLoadError() {
    return `
        <div class="alert alert-danger" role="alert">
            HTMX failed to load from the CDN, so this page can't fetch live content.
            Check your internet connection or CDN access, then reload the page.
        </div>
    `;
}

if (window.htmx) {
    window.htmx.config.selfRequestsOnly = false;
}

const timetableGrid = document.querySelector("[data-timetable-view='grid']");
if (timetableGrid) {
    if (!window.htmx) {
        timetableGrid.innerHTML = htmxLoadError();
    } else {
        const weekStart = queryParams.get("week_start");
        let url = `http://localhost:5005/timetable?username=${encodeURIComponent(username)}`;
        if (weekStart) url += `&week_start=${encodeURIComponent(weekStart)}`;
        timetableGrid.setAttribute("hx-get", url);
        timetableGrid.setAttribute("hx-trigger", "load, timetableChanged from:body");
        window.htmx.process(timetableGrid);
    }
}

const entryView = document.querySelector("[data-timetable-view='edit']");
const entryId = queryParams.get("id");

async function loadEntry() {
    if (!/^\d+$/.test(entryId || "")) {
        entryView.innerHTML = `
            <div class="alert alert-danger" role="alert">
                A valid timetable entry was not provided. <a class="alert-link" href="/">Return to your timetable</a>.
            </div>
        `;
        return;
    }

    try {
        const response = await fetch(`http://localhost:5005/timetable/${entryId}/edit`);
        if (!response.ok) throw new Error("Timetable entry request failed");

        entryView.innerHTML = await response.text();
        syncEndTimeMin(entryView);
        if (window.htmx) {
            window.htmx.process(entryView);
        } else {
            entryView.insertAdjacentHTML("afterbegin", htmxLoadError());
        }
    } catch {
        entryView.innerHTML = `
            <div class="alert alert-danger" role="alert">
                The timetable entry could not be loaded. Check that the backend service is running.
            </div>
        `;
    }
}

if (entryView) loadEntry();

const RAG_URL = "http://localhost:5005/rag";
const INSUFFICIENT_EVIDENCE = "Insufficient evidence.";
const CONFIDENCE_BADGES = {
    High: "text-bg-success",
    Medium: "text-bg-warning",
    Low: "text-bg-secondary",
    None: "text-bg-secondary",
};

function showRagAlert(text, kind = "warning") {
    const alertBox = document.querySelector("#rag-alert");
    alertBox.className = `alert alert-${kind}`;
    alertBox.textContent = text;
    alertBox.hidden = false;
}

function setRagModeText() {
    document.querySelector("#mode-help").textContent = document.querySelector("#rag-toggle").checked
        ? "RAG requests are enabled for this page."
        : "RAG mode is off. Turn it on to use a RAG tool.";
}

async function loadRagStatus() {
    const toggle = document.querySelector("#rag-toggle");
    try {
        const response = await fetch(`${RAG_URL}/status`);
        const status = await response.json();
        toggle.checked = Boolean(status.enabled);
        toggle.disabled = !status.enabled;
        if (!status.enabled) showRagAlert("RAG integration is disabled by the application configuration.");
    } catch {
        toggle.checked = false;
        toggle.disabled = true;
        showRagAlert("RAG status could not be checked. The timetable backend may be unavailable.");
    }
    setRagModeText();
}

function ragStatusLine(status, text = null) {
    const line = document.createElement("p");
    const ok = status >= 200 && status < 300;
    line.className = `${ok ? "text-success" : "text-danger"} small`;
    line.textContent = `${status ? `${status} · ` : ""}${text || (ok ? "Success" : "Request failed")}`;
    return line;
}

function showRagJson(output, status, body) {
    output.replaceChildren(ragStatusLine(status));
    const pre = document.createElement("pre");
    pre.className = "mb-0 small";
    pre.textContent = JSON.stringify(body, null, 2);
    output.append(pre);
}

// Each source opens the timetable entry it came from.
function entryLink(recordId, title) {
    if (!recordId) {
        const text = document.createElement("span");
        text.textContent = title || "Untitled entry";
        return text;
    }
    const link = document.createElement("a");
    link.href = `/edit.html?id=${encodeURIComponent(recordId)}`;
    link.textContent = title || "View entry";
    link.title = "Open timetable entry";
    return link;
}

function showRagResults(output, status, body) {
    if (status < 200 || status >= 300 || !Array.isArray(body.results)) {
        showRagJson(output, status, body);
        return;
    }

    output.replaceChildren(ragStatusLine(status, `${body.results.length} result${body.results.length === 1 ? "" : "s"} found`));
    if (!body.results.length) {
        const empty = document.createElement("p");
        empty.className = "text-secondary small mb-0";
        empty.textContent = "No indexed timetable entries were close enough to that query.";
        output.append(empty);
        return;
    }

    const list = document.createElement("ol");
    list.className = "rag-results";
    for (const item of body.results) {
        const heading = document.createElement("div");
        heading.className = "rag-result-heading";
        const title = document.createElement("span");
        title.className = "rag-result-title";
        title.append(entryLink(item.record_id, item.title));
        const distance = document.createElement("span");
        distance.className = "rag-result-distance";
        distance.textContent = `match distance ${item.distance}`;
        heading.append(title, distance);

        const text = document.createElement("p");
        text.className = "rag-result-text";
        text.textContent = item.text;

        const entry = document.createElement("li");
        entry.className = "rag-result-item";
        entry.append(heading, text);
        list.append(entry);
    }
    output.append(list);
}

function showRagAnswer(output, status, body) {
    if (status < 200 || status >= 300 || typeof body.answer !== "string") {
        showRagJson(output, status, body);
        return;
    }

    output.replaceChildren(ragStatusLine(status, "Answer generated"));
    const label = document.createElement("div");
    label.className = "rag-answer-label";
    label.textContent = "Answer";
    const answer = document.createElement("p");
    answer.className = "rag-answer";
    answer.textContent = body.answer === INSUFFICIENT_EVIDENCE
        ? "The indexed timetable entries do not contain enough information to answer that question."
        : body.answer;

    const meta = document.createElement("div");
    meta.className = "rag-answer-meta mb-3";
    const confidence = document.createElement("span");
    confidence.className = `badge ${CONFIDENCE_BADGES[body.confidence_category] || "text-bg-secondary"}`;
    confidence.textContent = `${body.confidence_category || "Unknown"} match`;
    const retrieval = body.retrieval_summary || {};
    const count = retrieval.retrieved_count ?? body.citations?.length ?? 0;
    const k = retrieval.k ?? "configured";
    meta.append(confidence, `${count} of ${k} records used`);
    output.append(label, answer, meta);

    const citations = Array.isArray(body.citations) ? body.citations : [];
    if (!citations.length) return;
    const heading = document.createElement("p");
    heading.className = "text-secondary small fw-semibold mb-1";
    heading.textContent = "Sources";
    const list = document.createElement("ol");
    list.className = "rag-citations small";
    for (const citation of citations) {
        const item = document.createElement("li");
        item.append(entryLink(citation.record_id, citation.title));
        list.append(item);
    }
    output.append(heading, list);
}

async function callRag(button, path, method, payload, output, render = showRagJson) {
    if (!document.querySelector("#rag-toggle").checked) {
        const message = document.createElement("p");
        message.className = "text-secondary mb-0";
        message.textContent = "RAG mode is off. Turn it on before running a tool.";
        output.replaceChildren(message);
        showRagAlert("RAG mode is off. Turn it on before running a tool.");
        return;
    }

    // Answers can take a minute or more on a local model, so the wait is counted.
    button.disabled = true;
    const start = Date.now();
    const showWaiting = () => {
        output.textContent = `Waiting for a response… (${Math.round((Date.now() - start) / 1000)}s)`;
    };
    showWaiting();
    const timer = setInterval(showWaiting, 1000);
    try {
        const response = await fetch(`${RAG_URL}${path}`, {
            method,
            headers: payload ? { "Content-Type": "application/json" } : {},
            body: payload ? JSON.stringify(payload) : undefined,
        });
        const body = await response.json().catch(() => ({ error: "Malformed response" }));
        clearInterval(timer);
        render(output, response.status, body);
    } catch {
        clearInterval(timer);
        render(output, 0, { error: "The timetable backend or RAG server could not be reached." });
    } finally {
        button.disabled = false;
    }
}

if (document.querySelector("[data-rag-page]")) {
    const toggle = document.querySelector("#rag-toggle");
    toggle.addEventListener("change", () => {
        setRagModeText();
        if (!toggle.checked) showRagAlert("RAG mode is off. Turn it on before running a tool.");
        else document.querySelector("#rag-alert").hidden = true;
    });

    document.querySelectorAll("[data-rag-button]").forEach((button) => {
        button.addEventListener("click", () => {
            const action = button.dataset.ragButton;
            if (action === "clear"
                && !window.confirm("Clear indexed timetable entries? Ingest to restore them.")) return;
            callRag(button, `/${action}`, action === "health" ? "GET" : "POST", null,
                document.getElementById(button.dataset.ragOutput));
        });
    });

    document.querySelectorAll("[data-rag-form]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            const kind = form.dataset.ragForm;
            const query = document.getElementById(`${kind}-query`).value;
            const value = document.getElementById(`${kind}-k`).value;
            callRag(form.querySelector("button[type=submit]"), `/${kind}`, "POST",
                { query, k: value ? Number(value) : null },
                document.getElementById(`${kind}-output`),
                kind === "retrieve" ? showRagResults : showRagAnswer);
        });
    });

    loadRagStatus();
}
