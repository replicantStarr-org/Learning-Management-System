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
const CONFIDENCE_BADGES = {
    High: "text-bg-success",
    Medium: "text-bg-warning",
    Low: "text-bg-danger",
    None: "text-bg-secondary",
};

function showRagAlert(text, kind = "warning") {
    const alertBox = document.querySelector("#rag-alert");
    alertBox.className = `alert alert-${kind}`;
    alertBox.textContent = text;
    alertBox.hidden = false;
}

function setRagHealth(text, badge) {
    const health = document.querySelector("#rag-health");
    health.className = `badge ${badge}`;
    health.textContent = text;
}

async function ragRequest(path, options = {}) {
    let response;
    try {
        response = await fetch(`${RAG_URL}${path}`, options);
    } catch {
        throw new Error("The timetable backend is unavailable. Check that its container is running.");
    }

    let data;
    try {
        data = await response.json();
    } catch {
        throw new Error("The timetable backend returned an unreadable response.");
    }
    if (!response.ok || data.status === "error") {
        const serviceError = data.services?.find((service) => service.error)?.error;
        throw new Error(data.error || serviceError || "The RAG request failed.");
    }
    return data;
}

function ragPost(path, body = {}) {
    return ragRequest(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
}

async function loadRagStatus() {
    try {
        const status = await ragRequest("/status");
        if (!status.enabled) {
            setRagHealth("Disabled", "text-bg-secondary");
            showRagAlert("RAG integration is disabled by the application configuration.");
            document.querySelectorAll("[data-rag-action], [data-rag-submit]").forEach((button) => {
                button.disabled = true;
            });
            return;
        }
        await ragRequest("/health");
        setRagHealth("RAG server online", "text-bg-success");
    } catch (error) {
        setRagHealth("RAG server offline", "text-bg-danger");
        showRagAlert(error.message, "danger");
    }
}

async function runRagIndexAction(action) {
    const result = document.querySelector("#rag-index-result");
    if (action === "clear" && !window.confirm("Remove every timetable entry from the RAG index? Re-index to restore it.")) {
        return;
    }
    result.textContent = action === "ingest" ? "Re-indexing…" : "Clearing…";
    document.querySelector("#rag-alert").hidden = true;

    try {
        const data = await ragPost(`/${action}`);
        if (action === "ingest") {
            const service = data.services?.[0] || {};
            result.textContent = `Indexed ${service.chunk_count ?? 0} timetable chunks (${service.removed_count ?? 0} stale removed).`;
        } else {
            result.textContent = `Removed ${data.removed_count ?? 0} timetable chunks from the index.`;
        }
    } catch (error) {
        result.textContent = "";
        showRagAlert(error.message, "danger");
    }
}

function renderRagAnswer(data) {
    const confidence = data.confidence_category || "None";
    const badge = document.querySelector("#rag-confidence");
    badge.className = `badge ${CONFIDENCE_BADGES[confidence] || "text-bg-secondary"}`;
    badge.textContent = `Confidence: ${confidence}`;

    document.querySelector("#rag-answer-text").textContent = data.answer;

    const citations = document.querySelector("#rag-citations");
    citations.replaceChildren();
    if (!data.citations?.length) {
        const item = document.createElement("li");
        item.className = "text-secondary";
        item.textContent = "No timetable entries were close enough to the question, so no answer was generated.";
        citations.append(item);
    }
    data.citations?.forEach((citation) => {
        const item = document.createElement("li");
        item.textContent = `${citation.title} `;
        const chunkId = document.createElement("code");
        chunkId.className = "small";
        chunkId.textContent = citation.chunk_id;
        item.append(chunkId);
        citations.append(item);
    });

    document.querySelector("#rag-answer").hidden = false;
}

function renderRagResults(results) {
    const list = document.querySelector("#rag-results-list");
    list.replaceChildren();
    if (!results.length) {
        const empty = document.createElement("p");
        empty.className = "text-secondary mb-0";
        empty.textContent = "No timetable entries were close enough to the question.";
        list.append(empty);
    }
    results.forEach((result) => {
        const card = document.createElement("div");
        card.className = "border rounded p-3";

        const heading = document.createElement("div");
        heading.className = "d-flex justify-content-between gap-2 mb-2";
        const title = document.createElement("strong");
        title.textContent = `${result.rank}. ${result.title}`;
        const distance = document.createElement("span");
        distance.className = "badge text-bg-light";
        distance.textContent = `distance ${result.distance}`;
        heading.append(title, distance);

        const text = document.createElement("pre");
        text.className = "bg-light rounded p-2 mb-0 small";
        text.textContent = result.text;

        card.append(heading, text);
        list.append(card);
    });

    document.querySelector("#rag-results").hidden = false;
}

async function askRag(event) {
    event.preventDefault();
    const mode = event.submitter?.dataset.ragSubmit || "answer";
    const query = document.querySelector("#rag-query").value.trim();
    if (!query) {
        showRagAlert("Enter a question first.");
        return;
    }

    const loading = document.querySelector("#rag-loading");
    const elapsed = document.querySelector("#rag-elapsed");
    const buttons = document.querySelectorAll("[data-rag-submit]");
    const start = Date.now();
    elapsed.textContent = "0";
    const timer = setInterval(() => {
        elapsed.textContent = Math.round((Date.now() - start) / 1000);
    }, 1000);
    loading.hidden = false;
    buttons.forEach((button) => { button.disabled = true; });
    document.querySelector("#rag-alert").hidden = true;
    document.querySelector("#rag-answer").hidden = true;
    document.querySelector("#rag-results").hidden = true;

    try {
        const data = await ragPost(`/${mode}`, { query });
        if (mode === "answer") {
            renderRagAnswer(data);
        } else {
            renderRagResults(data.results || []);
        }
    } catch (error) {
        showRagAlert(error.message, "danger");
    } finally {
        clearInterval(timer);
        loading.hidden = true;
        buttons.forEach((button) => { button.disabled = false; });
    }
}

if (document.querySelector("[data-rag-page]")) {
    document.querySelectorAll("[data-rag-action]").forEach((button) => {
        button.addEventListener("click", () => runRagIndexAction(button.dataset.ragAction));
    });
    document.querySelector("#rag-form").addEventListener("submit", askRag);
    loadRagStatus();
}
