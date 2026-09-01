const subjectId = new URLSearchParams(window.location.search).get("id");
const subjectView = document.querySelector("[data-subject-view]");

function showLoadError(message) {
    subjectView.innerHTML = `
        <div class="alert alert-danger" role="alert">
            ${message} <a class="alert-link" href="/">Return to all subjects</a>.
        </div>
    `;
}

async function loadSubject() {
    if (!/^\d+$/.test(subjectId || "")) {
        showLoadError("A valid subject was not provided.");
        return;
    }

    const suffix = subjectView.dataset.subjectView === "edit" ? "/edit" : "";
    try {
        const response = await fetch(
            `http://localhost:5001/subjects/${subjectId}${suffix}`
        );
        if (!response.ok) throw new Error("Subject request failed");

        subjectView.innerHTML = await response.text();
        window.htmx?.process(subjectView);
    } catch {
        showLoadError("The subject could not be loaded. Check that the backend service is running.");
    }
}

if (subjectView) loadSubject();
