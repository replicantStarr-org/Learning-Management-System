// Only public configuration is fetched here; credentials remain on the backend.
(() => {
    let config;
    function apply() {
        if (!config) return;
        document.querySelectorAll("a[data-service]").forEach((link) => {
            const url = config.navigation[link.dataset.service];
            if (url) link.href = url;
        });
        // A link marked data-feature-flag="NAME" is hidden while that flag is off.
        document.querySelectorAll("[data-feature-flag]").forEach((element) => {
            element.hidden = !config.flags[element.dataset.featureFlag];
        });
        const enabled = config.flags.AI_MODE_ENABLED;
        // Each feature owns its explanation and manual alternative, rather than
        // showing a page-wide warning (including on unrelated RAG/MCP pages).
        document.querySelectorAll("[data-ai-controls]").forEach((fieldset) => {
            fieldset.disabled = !enabled;
        });
        document.querySelectorAll("[data-ai-disabled]").forEach((notice) => {
            notice.hidden = enabled;
        });
        document.querySelectorAll("[data-ai-description]").forEach((description) => {
            description.hidden = !enabled;
        });
        document.querySelectorAll("[data-ai-link]").forEach((link) => {
            link.dataset.aiHref ||= link.getAttribute("href");
            link.classList.toggle("disabled", !enabled);
            link.setAttribute("aria-disabled", String(!enabled));
            if (enabled) {
                link.setAttribute("href", link.dataset.aiHref);
                link.removeAttribute("tabindex");
            } else {
                link.removeAttribute("href");
                link.setAttribute("tabindex", "-1");
            }
        });
        document.querySelectorAll("[data-ai-launcher]").forEach((button) => {
            button.classList.toggle("btn-primary", enabled);
            button.classList.toggle("btn-outline-secondary", !enabled);
            button.textContent = enabled ? "Ask the library" : "Library assistant · AI disabled";
        });
    }
    document.addEventListener("htmx:afterSwap", apply);
    fetch("/config").then((response) => {
        if (!response.ok) throw new Error("Configuration unavailable");
        return response.json();
    }).then((value) => { config = value; apply(); }).catch(() => {
        // Leave AI controls disabled when their availability cannot be checked.
        // Manual tools and independent integrations remain usable.
        document.querySelectorAll("[data-ai-disabled]").forEach((notice) => {
            notice.hidden = false;
            notice.textContent = "AI availability could not be checked. Please refresh to try again. Manual tools remain available.";
        });
        document.querySelectorAll("[data-ai-description]").forEach((description) => {
            description.hidden = true;
        });
    });
})();
