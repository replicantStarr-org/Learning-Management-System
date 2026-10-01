const backend = "http://localhost:5003/integration";
const mcpResult = document.querySelector("#mcp-result");
const ragResult = document.querySelector("#rag-result");

async function status(kind) {
    try {
        const response = await fetch(`${backend}/${kind}/status`);
        const body = await response.json();
        document.querySelector(`#${kind}-state`).textContent = body.enabled ? "Enabled" : "Disabled by configuration";
        const selectors = kind === "mcp"
            ? ["#mcp-run", "#mcp-action", "#mcp-days"]
            : ["#rag-form button", "#rag-query", "#rag-ingest"];
        for (const selector of selectors) {
            document.querySelectorAll(selector).forEach((element) => { element.disabled = !body.enabled; });
        }
        return body.enabled;
    } catch {
        document.querySelector(`#${kind}-state`).textContent = "Backend status unavailable";
        return false;
    }
}

async function showResult(target, request) {
    target.textContent = "Working...";
    try {
        const response = await request;
        const body = await response.json();
        target.textContent = JSON.stringify(body, null, 2);
    } catch {
        target.textContent = "The backend request could not be completed.";
    }
}

document.querySelector("#mcp-run").addEventListener("click", () => {
    const action = document.querySelector("#mcp-action").value;
    showResult(mcpResult, fetch(`${backend}/mcp/assignments`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-MCP-Mode": "on" },
        body: JSON.stringify({ action, days: Number(document.querySelector("#mcp-days").value) }),
    }));
});

document.querySelector("#rag-form").addEventListener("submit", (event) => {
    event.preventDefault();
    showResult(ragResult, fetch(`${backend}/rag/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-RAG-Mode": "on" },
        body: JSON.stringify({ query: document.querySelector("#rag-query").value }),
    }));
});

document.querySelector("#rag-ingest").addEventListener("click", () => {
    showResult(ragResult, fetch(`${backend}/rag/ingest`, {
        method: "POST", headers: { "X-RAG-Mode": "on" },
    }));
});

status("mcp");
status("rag");