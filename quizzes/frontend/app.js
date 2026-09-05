const queryParams = new URLSearchParams(window.location.search);
const quizId = queryParams.get("id");
const quizView = document.querySelector("[data-quiz-view]");
const pageMessage = document.querySelector("#page-message");

if (pageMessage && queryParams.has("message")) {
    pageMessage.textContent = queryParams.get("message");
    pageMessage.hidden = false;

    const cleanUrl = new URL(window.location.href);
    cleanUrl.searchParams.delete("message");
    window.history.replaceState({}, "", cleanUrl);
}

function showLoadError(message) {
    quizView.innerHTML = `
        <div class="alert alert-danger" role="alert">
            ${message} <a class="alert-link" href="/">Return to all quizzes</a>.
        </div>
    `;
}

function getCookie(name) {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : null;
}

function fillStudentName() {
    const field = document.querySelector("#student_name");
    if (field) field.value = getCookie("username") || "Guest";
}

async function loadQuiz() {
    if (!/^\d+$/.test(quizId || "")) {
        showLoadError("A valid quiz was not provided.");
        return;
    }

    const suffix = quizView.dataset.quizView === "edit" ? "?view=edit" : "";
    try {
        const response = await fetch(
            `http://localhost:5004/quizzes/${quizId}${suffix}`
        );
        if (!response.ok) throw new Error("Quiz request failed");

        quizView.innerHTML = await response.text();
        window.htmx?.process(quizView);
        fillStudentName();
    } catch {
        showLoadError("The quiz could not be loaded. Check that the backend service is running.");
    }
}

if (quizView) loadQuiz();
document.body.addEventListener("htmx:afterSwap", fillStudentName);
