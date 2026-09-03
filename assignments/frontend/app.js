const BACKEND_BASE = "http://127.0.0.1:5003";

const queryParams = new URLSearchParams(window.location.search);
const assignmentId = queryParams.get("id");
const assignmentView = document.querySelector("[data-assignment-view]");
const pageMessage = document.querySelector("#page-message");

if (pageMessage && queryParams.has("message")) {
    pageMessage.textContent = queryParams.get("message");
    pageMessage.hidden = false;

    const cleanUrl = new URL(window.location.href);
    cleanUrl.searchParams.delete("message");
    window.history.replaceState({}, "", cleanUrl);
}

function showLoadError(message) {
    assignmentView.innerHTML = `
        <div class="alert alert-danger" role="alert">
            ${message} <a class="alert-link" href="/">Return to all assignments</a>.
        </div>
    `;
}

async function loadAssignment() {
    if (!/^\d+$/.test(assignmentId || "")) {
        showLoadError("A valid assignment was not provided.");
        return;
    }

    const suffix = assignmentView.dataset.assignmentView === "edit" ? "/edit" : "";
    try {
        // The backend answers JSON by default and hypermedia when HTMX asks for it, so this
        // hand-written fetch has to identify itself the same way HTMX would.
        const response = await fetch(`${BACKEND_BASE}/assignments/${assignmentId}${suffix}`, {
            headers: { "HX-Request": "true" },
        });
        if (!response.ok) throw new Error("Assignment request failed");

        assignmentView.innerHTML = await response.text();
        window.htmx?.process(assignmentView);
    } catch {
        showLoadError("The assignment could not be loaded. Check that the backend service is running.");
    }
}

if (assignmentView) loadAssignment();
