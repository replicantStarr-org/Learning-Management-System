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

// Prefill the add-entry form: date defaults to today and start time to 8am, unless specific
// values were passed in via the URL (as they are when the calendar's click-to-create sends you
// here with a slot already chosen - see the .cal-day-col click handler below).
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
    // Leaving this genuinely blank isn't actually blank in practice: Chromium/Edge seeds an
    // empty time input's picker from the current system clock the moment you interact with it,
    // which looks like a random, undeliberate default - so it always gets a real value: one hour
    // after start_time, same rule the reactive listener below applies on every later change.
    endField.value = queryParams.get("end_time") || (startField ? addOneHour(startField.value) : "09:00");
}

// Keep end_time's minimum in sync with whatever start_time currently holds, both for a form
// already on the page and for one injected later (the edit page's fragment).
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
    // As soon as a start time is set, if end time is (now, or already) empty, default it to one
    // hour later rather than leaving it blank for Chromium/Edge to improvise from the system clock.
    if (!endInput.value && event.target.value) endInput.value = addOneHour(event.target.value);
});

// Click-to-create: clicking empty space in a day column jumps to the add-entry form with that
// day and a snapped-to-the-half-hour time slot already filled in. Clicks on an existing entry
// (or its edit/delete icons) are left alone so those keep working normally.
const CAL_PX_PER_HOUR = 56; // must match --cal-hour-height in calendar.css / PX_PER_HOUR in views/html.py
const CAL_START_HOUR = 8;
const CAL_END_HOUR = 23;

function minutesToTimeString(totalMinutes) {
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

document.addEventListener("click", (event) => {
    const dayCol = event.target.closest(".cal-day-col");
    // The AI-plan preview calendar (inside the modal) is read-only except for its own "Add"
    // buttons on suggestion blocks - clicking its empty space should not jump to create a
    // new, unrelated entry.
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

// Live "Ns elapsed" counters for the two AI actions, since generation can take a minute or more
// on this CPU-only setup and a static "please wait" message gives no sense that it's progressing.
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

// The plan modal's counter lives inside #ai-plan-modal-body, the same element hx-target swaps
// into - so after a first successful generation that element no longer exists (it got replaced
// by the result). Re-clicking "Generate" later has to put the loading skeleton back first, or
// the counter would have nothing to find and never appear on any run after the first.
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
    // The <meta name="htmx-config" content='{"selfRequestsOnly": false}'> tag is only read
    // inside htmx's own internal ready()/DOMContentLoaded handler. This script sits at the
    // bottom of <body> and runs synchronously *before* that event fires, so any htmx.process()
    // call below would race that handler and lose, leaving selfRequestsOnly at its default
    // `true` - which silently blocks every cross-origin request to the backend (:5005) with an
    // htmx:invalidPath error and never sends anything. Setting it directly here is synchronous
    // and always wins that race.
    window.htmx.config.selfRequestsOnly = false;
}

// The grid needs the student's username, which is only known client-side (cookie), so its
// hx-get URL is set dynamically here rather than declared statically in index.html.
const timetableGrid = document.querySelector("[data-timetable-view='grid']");
if (timetableGrid) {
    if (!window.htmx) {
        // Without this check, a failed htmx.org script load fails silently here (optional
        // chaining swallows it) and the "Loading…" spinner is left stuck forever with no
        // request ever sent - this turns that into a visible, diagnosable error instead.
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
