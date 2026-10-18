// Public deployment configuration only; never put credentials in this response.
let runtimeConfig;
function applyRuntimeConfig() {
    if (!runtimeConfig) return;
    document.querySelectorAll('a[href^="http://localhost:300"]').forEach((link) => {
        const names = {3000: "access", 3002: "resources", 3003: "assignments", 3004: "quizzes", 3005: "timetable"};
        const name = names[new URL(link.href).port];
        if (runtimeConfig.navigation[name]) link.href = runtimeConfig.navigation[name];
    });
    if (!runtimeConfig.flags.AI_MODE_ENABLED) {
        const summary = document.querySelector("#summary-result");
        if (summary) {
            summary.removeAttribute("hx-post");
            summary.textContent = "AI mode is disabled in this deployment.";
        }
        document.querySelectorAll('form[hx-post="/subjects/questions"] button, form[hx-post="/subjects/questions"] textarea')
            .forEach((control) => { control.disabled = true; });
    }
    const nav = document.querySelector("nav .container");
    if (nav && !document.querySelector("#deployment-profile")) {
        const badge = document.createElement("span");
        badge.id = "deployment-profile";
        badge.className = "badge text-bg-secondary ms-2";
        badge.textContent = `Profile: ${runtimeConfig.profile}`;
        badge.title = Object.entries(runtimeConfig.flags).map(([name, value]) => `${name}: ${value}`).join(" · ");
        nav.append(badge);
    }
}
document.addEventListener("htmx:afterSwap", applyRuntimeConfig);
fetch("/config").then((response) => response.json()).then((config) => {
    runtimeConfig = config;
    applyRuntimeConfig();
}).catch(() => {});
