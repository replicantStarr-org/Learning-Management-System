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

const RAG_URL = "http://localhost:5004/rag";
const INSUFFICIENT_EVIDENCE = "Insufficient evidence.";
const CONFIDENCE_BADGES = {
    High: "text-bg-success",
    Medium: "text-bg-warning",
    Low: "text-bg-secondary",
    None: "text-bg-secondary",
};

function showRagAlert(text, kind = "warning") {
    const alertBox = document.querySelector("#rag-alert");
    alertBox.className = `alert alert-${kind}`;
    alertBox.textContent = text;
    alertBox.hidden = false;
}

function setRagModeText() {
    document.querySelector("#mode-help").textContent = document.querySelector("#rag-toggle").checked
        ? "RAG requests are enabled for this page."
        : "RAG mode is off. Turn it on to use a RAG tool.";
}

async function loadRagStatus() {
    const toggle = document.querySelector("#rag-toggle");
    try {
        const response = await fetch(`${RAG_URL}/status`);
        const status = await response.json();
        toggle.checked = Boolean(status.enabled);
        toggle.disabled = !status.enabled;
        if (!status.enabled) showRagAlert("RAG integration is disabled by the application configuration.");
    } catch {
        toggle.checked = false;
        toggle.disabled = true;
        showRagAlert("RAG status could not be checked. The quiz backend may be unavailable.");
    }
    setRagModeText();
}

function ragStatusLine(status, text = null) {
    const line = document.createElement("p");
    const ok = status >= 200 && status < 300;
    line.className = `${ok ? "text-success" : "text-danger"} small`;
    line.textContent = `${status ? `${status} · ` : ""}${text || (ok ? "Success" : "Request failed")}`;
    return line;
}

function showRagJson(output, status, body) {
    output.replaceChildren(ragStatusLine(status));
    const pre = document.createElement("pre");
    pre.className = "mb-0 small";
    pre.textContent = JSON.stringify(body, null, 2);
    output.append(pre);
}

const SOURCE_LABELS = {
    quiz: "Quiz",
    quiz_question: "Question",
};

// A quiz source opens that quiz. Questions have no page of their own, so they
// are labelled with their kind instead.
function sourceLink(source) {
    const label = SOURCE_LABELS[source.entity];
    const prefix = label ? `${label}: ` : "";
    if (source.entity !== "quiz" || !source.record_id) {
        const text = document.createElement("span");
        text.textContent = `${prefix}${source.title || "Untitled record"}`;
        return text;
    }
    const link = document.createElement("a");
    link.href = `/quiz.html?id=${encodeURIComponent(source.record_id)}`;
    link.textContent = `${prefix}${source.title || "View quiz"}`;
    link.title = "Open quiz";
    return link;
}

function showRagResults(output, status, body) {
    if (status < 200 || status >= 300 || !Array.isArray(body.results)) {
        showRagJson(output, status, body);
        return;
    }

    output.replaceChildren(ragStatusLine(status, `${body.results.length} result${body.results.length === 1 ? "" : "s"} found`));
    if (!body.results.length) {
        const empty = document.createElement("p");
        empty.className = "text-secondary small mb-0";
        empty.textContent = "No indexed quiz records were close enough to that query.";
        output.append(empty);
        return;
    }

    const list = document.createElement("ol");
    list.className = "rag-results";
    for (const item of body.results) {
        const heading = document.createElement("div");
        heading.className = "rag-result-heading";
        const title = document.createElement("span");
        title.className = "rag-result-title";
        title.append(sourceLink(item));
        const distance = document.createElement("span");
        distance.className = "rag-result-distance";
        distance.textContent = `match distance ${item.distance}`;
        heading.append(title, distance);

        const text = document.createElement("p");
        text.className = "rag-result-text";
        text.textContent = item.text;

        const entry = document.createElement("li");
        entry.className = "rag-result-item";
        entry.append(heading, text);
        list.append(entry);
    }
    output.append(list);
}

function showRagAnswer(output, status, body) {
    if (status < 200 || status >= 300 || typeof body.answer !== "string") {
        showRagJson(output, status, body);
        return;
    }

    output.replaceChildren(ragStatusLine(status, "Answer generated"));
    const label = document.createElement("div");
    label.className = "rag-answer-label";
    label.textContent = "Answer";
    const answer = document.createElement("p");
    answer.className = "rag-answer";
    answer.textContent = body.answer === INSUFFICIENT_EVIDENCE
        ? "Insufficient context: the indexed quizzes do not contain enough information to answer that question."
        : body.answer;

    const meta = document.createElement("div");
    meta.className = "rag-answer-meta mb-3";
    const confidence = document.createElement("span");
    confidence.className = `badge ${CONFIDENCE_BADGES[body.confidence_category] || "text-bg-secondary"}`;
    confidence.textContent = `${body.confidence_category || "Unknown"} match`;
    const retrieval = body.retrieval_summary || {};
    const count = retrieval.retrieved_count ?? body.citations?.length ?? 0;
    const k = retrieval.k ?? "configured";
    meta.append(confidence, `${count} of ${k} records used`);
    output.append(label, answer, meta);

    const citations = Array.isArray(body.citations) ? body.citations : [];
    if (!citations.length) return;
    const heading = document.createElement("p");
    heading.className = "text-secondary small fw-semibold mb-1";
    heading.textContent = "Sources";
    const list = document.createElement("ol");
    list.className = "rag-citations small";
    for (const citation of citations) {
        const item = document.createElement("li");
        item.append(sourceLink(citation));
        list.append(item);
    }
    output.append(heading, list);
}

async function callRag(button, path, method, payload, output, render = showRagJson) {
    if (!document.querySelector("#rag-toggle").checked) {
        const message = document.createElement("p");
        message.className = "text-secondary mb-0";
        message.textContent = "RAG mode is off. Turn it on before running a tool.";
        output.replaceChildren(message);
        showRagAlert("RAG mode is off. Turn it on before running a tool.");
        return;
    }

    // Answers can take a minute or more on a local model, so the wait is counted.
    button.disabled = true;
    const start = Date.now();
    const showWaiting = () => {
        output.textContent = `Waiting for a response… (${Math.round((Date.now() - start) / 1000)}s)`;
    };
    showWaiting();
    const timer = setInterval(showWaiting, 1000);
    try {
        const response = await fetch(`${RAG_URL}${path}`, {
            method,
            headers: payload ? { "Content-Type": "application/json" } : {},
            body: payload ? JSON.stringify(payload) : undefined,
        });
        const body = await response.json().catch(() => ({ error: "Malformed response" }));
        clearInterval(timer);
        render(output, response.status, body);
    } catch {
        clearInterval(timer);
        render(output, 0, { error: "The quiz backend or RAG server could not be reached." });
    } finally {
        button.disabled = false;
    }
}

if (document.querySelector("[data-rag-page]")) {
    const toggle = document.querySelector("#rag-toggle");
    toggle.addEventListener("change", () => {
        setRagModeText();
        if (!toggle.checked) showRagAlert("RAG mode is off. Turn it on before running a tool.");
        else document.querySelector("#rag-alert").hidden = true;
    });

    document.querySelectorAll("[data-rag-button]").forEach((button) => {
        button.addEventListener("click", () => {
            const action = button.dataset.ragButton;
            if (action === "clear"
                && !window.confirm("Clear indexed quizzes? Ingest to restore them.")) return;
            callRag(button, `/${action}`, action === "health" ? "GET" : "POST", null,
                document.getElementById(button.dataset.ragOutput));
        });
    });

    document.querySelectorAll("[data-rag-form]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            const kind = form.dataset.ragForm;
            const query = document.getElementById(`${kind}-query`).value;
            const value = document.getElementById(`${kind}-k`).value;
            callRag(form.querySelector("button[type=submit]"), `/${kind}`, "POST",
                { query, k: value ? Number(value) : null },
                document.getElementById(`${kind}-output`),
                kind === "retrieve" ? showRagResults : showRagAnswer);
        });
    });

    loadRagStatus();
}

const MCP_URL = "http://localhost:5004/mcp";
const MCP_ROUTES = {
    quizzes: "/quizzes",
    quiz: "/quiz",
    practice: "/practice",
    search: "/search",
};
const MCP_DIFFICULTY_BADGES = {
    Easy: "text-bg-success",
    Medium: "text-bg-warning",
    Hard: "text-bg-danger",
};

function showMcpAlert(text, kind = "warning") {
    const alertBox = document.querySelector("#mcp-alert");
    alertBox.className = `alert alert-${kind}`;
    alertBox.textContent = text;
    alertBox.hidden = false;
}

function setMcpModeText() {
    document.querySelector("#mode-help").textContent = document.querySelector("#mcp-toggle").checked
        ? "MCP requests are enabled for this page."
        : "MCP mode is off. Turn it on to run a tool.";
}

async function loadMcpStatus() {
    const toggle = document.querySelector("#mcp-toggle");
    try {
        const response = await fetch(`${MCP_URL}/status`);
        const status = await response.json();
        toggle.checked = Boolean(status.enabled);
        toggle.disabled = !status.enabled;
        if (!status.enabled) showMcpAlert("MCP integration is disabled by the application configuration.");
    } catch {
        toggle.checked = false;
        toggle.disabled = true;
        showMcpAlert("MCP status could not be checked. The quiz backend may be unavailable.");
    }
    setMcpModeText();
}

function mcpStatusLine(status, text) {
    const line = document.createElement("p");
    const ok = status >= 200 && status < 300;
    line.className = `${ok ? "text-success" : "text-danger"} small`;
    line.textContent = `${status ? `${status} · ` : ""}${text}`;
    return line;
}

function mcpRawResult(body, label = "Raw tool result") {
    const details = document.createElement("details");
    details.className = "mcp-raw";
    const summary = document.createElement("summary");
    summary.textContent = label;
    const pre = document.createElement("pre");
    pre.className = "small mt-2 mb-0";
    pre.textContent = JSON.stringify(body, null, 2);
    details.append(summary, pre);
    return details;
}

function mcpElement(tag, className, text) {
    const element = document.createElement(tag);
    element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
}

function mcpItem(titleNode, metaText, bodyText, badge = null) {
    const heading = mcpElement("div", "mcp-item-heading");
    heading.append(titleNode);
    if (badge) heading.append(badge);
    heading.append(mcpElement("span", "mcp-item-meta", metaText));
    const item = mcpElement("li", "mcp-item");
    item.append(heading);
    if (bodyText) item.append(mcpElement("p", "mcp-item-text", bodyText));
    return item;
}

function mcpQuizTitle(quizId, title) {
    const link = mcpElement("a", "mcp-item-title text-decoration-none", title);
    link.href = `/quiz.html?id=${encodeURIComponent(quizId)}`;
    return link;
}

function mcpDifficulty(difficulty) {
    return mcpElement("span", `badge ${MCP_DIFFICULTY_BADGES[difficulty] || "text-bg-secondary"}`, difficulty);
}

function mcpList(items) {
    const list = mcpElement("ol", "mcp-items");
    list.append(...items);
    return list;
}

let mcpAnswerCount = 0;

// The correct answer and explanation start hidden behind a button, so the
// lookup can be read as a quiz without giving the answers away.
function mcpAnswerReveal(item, question) {
    const answer = mcpElement("p", "mcp-item-text mcp-answer mt-2",
        `Correct answer: ${question.correct_answer || "none set"}. ${question.explanation}`);
    answer.id = `mcp-answer-${++mcpAnswerCount}`;
    answer.hidden = true;

    const button = mcpElement("button", "btn btn-sm btn-link px-0 mt-1", "Show answer");
    button.type = "button";
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-controls", answer.id);
    const setRevealed = (reveal) => {
        answer.hidden = !reveal;
        button.setAttribute("aria-expanded", String(reveal));
        button.textContent = reveal ? "Hide answer" : "Show answer";
    };
    button.addEventListener("click", () => setRevealed(answer.hidden));

    item.append(button, answer);
    return setRevealed;
}

// Fills the quiz lookup with this quiz and runs it, so a listed quiz can be opened in one click.
function lookUpQuiz(quizId) {
    const form = document.querySelector("[data-mcp-form=quiz]");
    form.querySelector("[name=quiz_id]").value = quizId;
    form.requestSubmit();
    form.scrollIntoView({ behavior: "smooth", block: "start" });
}

// One question to answer before seeing whether it was right, with the explanation.
function mcpPracticeQuestion(result) {
    const heading = mcpElement("p", "fw-semibold mb-2", result.question_text);
    const source = mcpElement("p", "text-secondary small mb-3",
        `${result.quiz_title}, question ${result.number} · ${result.subject_name} · ${result.difficulty}`);

    const name = `practice-${result.question_id}-${++mcpAnswerCount}`;
    const options = mcpElement("div", "mb-3");
    result.answers.forEach((text, index) => {
        const option = mcpElement("div", "form-check");
        const input = mcpElement("input", "form-check-input");
        input.type = "radio";
        input.name = name;
        input.id = `${name}-${index}`;
        input.value = text;
        const label = mcpElement("label", "form-check-label", text);
        label.htmlFor = input.id;
        option.append(input, label);
        options.append(option);
    });

    const feedback = mcpElement("div", "mcp-summary mb-0");
    feedback.hidden = true;
    feedback.setAttribute("role", "status");
    const check = mcpElement("button", "btn btn-sm btn-outline-primary", "Check answer");
    check.type = "button";
    check.addEventListener("click", () => {
        const chosen = options.querySelector("input:checked");
        if (!chosen) {
            feedback.textContent = "Choose an answer first.";
            feedback.hidden = false;
            return;
        }
        const correct = chosen.value === result.correct_answer;
        feedback.replaceChildren(
            mcpElement("p", `fw-semibold mb-1 ${correct ? "text-success" : "text-danger"}`,
                correct ? "Correct!" : `Not quite. The answer is: ${result.correct_answer}`),
            mcpElement("p", "mb-0 small", result.explanation),
        );
        feedback.hidden = false;
        options.querySelectorAll("input").forEach((input) => { input.disabled = true; });
        check.hidden = true;
    });
    return [heading, source, options, check, feedback];
}

const MCP_RENDERERS = {
    quizzes(result) {
        if (!result.length) return [mcpElement("p", "text-secondary small", "No quizzes match those filters.")];
        return [mcpList(result.map((quiz) => {
            const item = mcpItem(
                mcpQuizTitle(quiz.quiz_id, quiz.title),
                `#${quiz.quiz_id}`,
                `${quiz.subject_name} · ${quiz.question_count} question${quiz.question_count === 1 ? "" : "s"}`
                    + (quiz.source === "ai_generated" ? " · AI generated" : ""),
                mcpDifficulty(quiz.difficulty),
            );
            const use = mcpElement("button", "btn btn-sm btn-outline-primary mt-2", "Look up this quiz");
            use.type = "button";
            use.addEventListener("click", () => lookUpQuiz(quiz.quiz_id));
            item.append(use);
            return item;
        }))];
    },
    quiz(result) {
        const summary = mcpElement("p", "mcp-summary",
            `${result.title} · ${result.subject_name} · ${result.difficulty} · ${result.questions.length} questions. ${result.description}`);
        const toggles = [];
        const items = result.questions.map((question) => {
            const item = mcpItem(
                mcpElement("span", "mcp-item-title", `${question.number}. ${question.question_text}`),
                `#${question.question_id}`,
                `Options: ${question.answers.join(" · ")}`,
            );
            toggles.push(mcpAnswerReveal(item, question));
            return item;
        });

        // One switch for checking a whole quiz at once; each question can still be toggled alone.
        const all = mcpElement("button", "btn btn-sm btn-outline-secondary mb-3", "Show all answers");
        all.type = "button";
        all.setAttribute("aria-pressed", "false");
        all.addEventListener("click", () => {
            const reveal = all.getAttribute("aria-pressed") !== "true";
            all.setAttribute("aria-pressed", String(reveal));
            all.textContent = reveal ? "Hide all answers" : "Show all answers";
            toggles.forEach((setRevealed) => setRevealed(reveal));
        });
        return [summary, all, mcpList(items)];
    },
    practice: mcpPracticeQuestion,
    search(result) {
        const summary = mcpElement("p", "mcp-summary",
            `${result.match_count} question${result.match_count === 1 ? "" : "s"} mention "${result.keyword}"`
            + (result.truncated ? "; showing the first 25." : "."));
        if (!result.matches.length) return [summary];
        return [summary, mcpList(result.matches.map((match) => mcpItem(
            mcpQuizTitle(match.quiz_id, `${match.quiz_title}, question ${match.number}`),
            `#${match.question_id}`,
            match.question_text,
        )))];
    },
};

function showMcpResult(output, kind, status, body) {
    if (status < 200 || status >= 300 || body.status !== "success") {
        output.replaceChildren(mcpStatusLine(status, body.error || "Request failed"), mcpRawResult(body));
        return;
    }
    output.replaceChildren(
        mcpStatusLine(status, `${body.tool} returned a result`),
        ...MCP_RENDERERS[kind](body.result),
        mcpRawResult(body.result, ["quiz", "practice"].includes(kind) ? "Raw tool result (includes answers)" : undefined),
    );
}

async function runMcpTool(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const kind = form.dataset.mcpForm;
    const output = document.getElementById(`${kind}-output`);
    if (!document.querySelector("#mcp-toggle").checked) {
        output.replaceChildren(mcpElement("p", "text-secondary small", "MCP mode is off. Turn it on before running a tool."));
        showMcpAlert("MCP mode is off. Turn it on before running a tool.");
        return;
    }
    if (!form.reportValidity()) return;

    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    output.textContent = "Running MCP tool…";
    document.querySelector("#mcp-alert").hidden = true;
    try {
        const response = await fetch(`${MCP_URL}${MCP_ROUTES[kind]}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(Object.fromEntries(new FormData(form))),
        });
        const body = await response.json().catch(() => ({ error: "Malformed response" }));
        showMcpResult(output, kind, response.status, body);
    } catch {
        showMcpResult(output, kind, 0, { error: "The quiz backend could not be reached." });
    } finally {
        button.disabled = false;
    }
}

if (document.querySelector("[data-mcp-page]")) {
    const toggle = document.querySelector("#mcp-toggle");
    toggle.addEventListener("change", () => {
        setMcpModeText();
        if (!toggle.checked) showMcpAlert("MCP mode is off. Turn it on before running a tool.");
        else document.querySelector("#mcp-alert").hidden = true;
    });

    document.querySelectorAll("[data-mcp-form]").forEach((form) => form.addEventListener("submit", runMcpTool));
    loadMcpStatus();
}
