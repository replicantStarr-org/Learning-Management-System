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
