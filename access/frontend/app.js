const apiUrl = "http://localhost:5000";

function showMessage(text, kind = "danger") {
    const message = document.querySelector("#form-message");
    if (!message) return;
    message.className = `alert alert-${kind}`;
    message.textContent = text;
}

async function checkSession() {
    if (document.body.dataset.requiresAuth !== "true") return;

    try {
        const response = await fetch(`${apiUrl}/session`, { credentials: "include" });
        if (!response.ok) {
            window.location.replace("/login");
            return;
        }
        const session = await response.json();
        const currentUser = document.querySelector("#current-user");
        if (currentUser) currentUser.textContent = session.username;
    } catch {
        window.location.replace("/login");
    }
}

const authForm = document.querySelector("[data-auth-form]");
if (authForm) {
    authForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const action = authForm.dataset.authForm;
        const submitButton = authForm.querySelector("button[type='submit']");
        submitButton.disabled = true;

        try {
            const response = await fetch(`${apiUrl}/${action}`, {
                method: "POST",
                credentials: "include",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(Object.fromEntries(new FormData(authForm))),
            });
            const result = await response.json();
            if (!response.ok) {
                showMessage(result.error || "Please try again.");
                return;
            }
            window.location.assign(action === "login" ? "/" : "/login?registered=true");
        } catch {
            showMessage("The access service is unavailable. Please try again.");
        } finally {
            submitButton.disabled = false;
        }
    });
}

if (new URLSearchParams(window.location.search).has("registered")) {
    showMessage("Account created. You can now log in.", "success");
}

document.querySelector("#logout")?.addEventListener("click", async () => {
    await fetch(`${apiUrl}/logout`, { method: "POST", credentials: "include" });
    window.location.assign("/login");
});

checkSession();
