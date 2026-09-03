import * as pdfjsLib from "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.6.82/build/pdf.min.mjs";

pdfjsLib.GlobalWorkerOptions.workerSrc =
	"https://cdn.jsdelivr.net/npm/pdfjs-dist@4.6.82/build/pdf.worker.min.mjs";

const THUMBNAIL_WIDTH = 320;
const PRELOAD_MARGIN = "200px";

// Documents are opened lazily and reused, so a card thumbnail, the detail
// preview and the reader all share one download of the same PDF.
const openDocuments = new Map();

function loadDocument(location) {
	if (!openDocuments.has(location)) {
		const task = pdfjsLib.getDocument({
			url: location,
			// Fetch byte ranges on demand rather than the whole document, so
			// opening a card costs page one instead of the full paper.
			disableAutoFetch: true,
			disableStream: false,
		});
		openDocuments.set(location, task.promise);
	}

	return openDocuments.get(location);
}

// Only the canvas bitmap is sized here; CSS lays the element out at 100% width
// and derives the height from that bitmap's aspect ratio.
async function renderPage(page, canvas, displayWidth) {
	const ratio = window.devicePixelRatio || 1;
	const unscaled = page.getViewport({ scale: 1 });
	const viewport = page.getViewport({ scale: (displayWidth / unscaled.width) * ratio });

	canvas.width = viewport.width;
	canvas.height = viewport.height;

	await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
	canvas.classList.add("is-loaded");
}

async function renderFirstPage(canvas, displayWidth) {
	const pdf = await loadDocument(canvas.dataset.location);
	await renderPage(await pdf.getPage(1), canvas, displayWidth);
}

// Reader pages are a canvas with PDF.js's text layer laid over the top: the
// spans are transparent and positioned on the glyphs they represent, which is
// what makes the rendered page selectable like a normal document.
async function renderReaderPage(page, wrapper, displayWidth) {
	const ratio = window.devicePixelRatio || 1;
	const unscaled = page.getViewport({ scale: 1 });
	const scale = displayWidth / unscaled.width;
	const viewport = page.getViewport({ scale });

	wrapper.style.width = `${viewport.width}px`;
	wrapper.style.height = `${viewport.height}px`;
	// PDF.js positions and sizes every text span against this.
	wrapper.style.setProperty("--scale-factor", scale);

	const canvas = wrapper.querySelector(".reader-page-canvas");
	canvas.width = Math.floor(viewport.width * ratio);
	canvas.height = Math.floor(viewport.height * ratio);
	canvas.style.width = `${viewport.width}px`;
	canvas.style.height = `${viewport.height}px`;

	await page.render({
		canvasContext: canvas.getContext("2d"),
		viewport,
		transform: ratio === 1 ? null : [ratio, 0, 0, ratio, 0, 0],
	}).promise;

	const container = wrapper.querySelector(".textLayer");
	container.replaceChildren();
	await new pdfjsLib.TextLayer({
		textContentSource: await page.getTextContent(),
		container,
		viewport,
	}).render();

	drawHighlights(wrapper);
	wrapper.classList.add("is-loaded");
}

// Rectangles are stored as fractions of the page, so they are drawn as
// percentages and stay correct whatever width the page was rendered at.
function drawHighlights(wrapper) {
	const layer = wrapper.querySelector(".highlight-layer");
	const pageNumber = Number(wrapper.dataset.page);
	let drewFocused = false;

	layer.replaceChildren();
	for (const rect of readerHighlights) {
		if (rect.page_number !== pageNumber) {
			continue;
		}

		const mark = document.createElement("div");
		mark.className = "highlight-mark";
		mark.style.left = `${rect.x * 100}%`;
		mark.style.top = `${rect.y * 100}%`;
		mark.style.width = `${rect.width * 100}%`;
		mark.style.height = `${rect.height * 100}%`;
		mark.style.background = rect.colour;
		mark.title = rect.name || "Highlight";
		if (rect.l_resource_highlight_id === focusedHighlightId) {
			mark.classList.add("is-focused");
			drewFocused = true;
		}
		layer.append(mark);
	}

	// The countdown starts when the ring is actually on screen, not when the
	// jump was requested; the page it lands on may take a while to render.
	if (drewFocused) {
		startFocusCountdown();
	}
}

function createReaderPage(pageNumber, width, height) {
	const wrapper = document.createElement("div");
	wrapper.className = "reader-page";
	wrapper.dataset.page = String(pageNumber);
	wrapper.style.width = `${width}px`;
	wrapper.style.height = `${height}px`;

	const canvas = document.createElement("canvas");
	canvas.className = "reader-page-canvas";

	// Sits between the canvas and the text layer, so the marks are over the page
	// but the words stay selectable.
	const highlightLayer = document.createElement("div");
	highlightLayer.className = "highlight-layer";

	const textLayer = document.createElement("div");
	textLayer.className = "textLayer";

	wrapper.append(canvas, highlightLayer, textLayer);

	return wrapper;
}

function markFailed(canvas) {
	canvas.closest(".resource-thumb")?.classList.add("is-failed");
}

// Every rectangle of every highlight on the document currently open.
let readerHighlights = [];
let readerResource = null;
// Set while jumping to a highlight, so its marks stand out when drawn.
let focusedHighlightId = null;
let focusClearTimer = null;

async function loadHighlights(resourceId) {
	try {
		const response = await fetch(`/api/highlights/resource/${resourceId}`);
		return response.ok ? (await response.json()).highlights : [];
	} catch {
		return [];
	}
}

/* ---------- card thumbnails ---------- */

const thumbnailObserver = new IntersectionObserver((entries) => {
	for (const entry of entries) {
		if (!entry.isIntersecting) {
			continue;
		}

		const canvas = entry.target;
		thumbnailObserver.unobserve(canvas);
		renderFirstPage(canvas, THUMBNAIL_WIDTH).catch(() => markFailed(canvas));
	}
}, { rootMargin: PRELOAD_MARGIN });

function observeThumbnails(root) {
	for (const canvas of root.querySelectorAll(".resource-thumb-canvas")) {
		thumbnailObserver.observe(canvas);
	}
}

/* ---------- detail popup ---------- */

const detailModal = new bootstrap.Modal("#detail-modal");
const detailCanvas = document.getElementById("detail-canvas");
const detailHighlights = document.getElementById("detail-highlights");
let selectedResource = null;
// The highlights the popup is currently showing, so that editing a row can pick
// up the values already fetched rather than asking for them again.
let loadedHighlights = [];

async function showResourceHighlights(resourceId) {
	detailHighlights.replaceChildren(
		Object.assign(document.createElement("p"), {
			className: "text-secondary small mb-0",
			textContent: "Loading highlights...",
		}),
	);

	let highlights = [];
	try {
		const response = await fetch(`/api/highlights/resource/${resourceId}/summary`);
		highlights = response.ok ? (await response.json()).highlights : [];
	} catch {
		highlights = [];
	}

	// The popup may have moved on to another resource while this was in flight.
	if (selectedResource?.id !== String(resourceId)) {
		return;
	}

	loadedHighlights = highlights;

	if (!highlights.length) {
		detailHighlights.replaceChildren(
			Object.assign(document.createElement("p"), {
				className: "text-secondary small mb-0",
				textContent: "No highlights yet. Select text while reading to make one.",
			}),
		);
		return;
	}

	detailHighlights.replaceChildren(...highlights.map(renderHighlightEntry));
}

function renderHighlightEntry(highlight) {
	const entry = document.createElement("div");
	entry.className = "highlight-entry";
	entry.dataset.highlightId = highlight.l_resource_highlight_id;

	// Following the highlight and editing it are separate targets, so the whole
	// row cannot be one button.
	const open = document.createElement("button");
	open.type = "button";
	open.className = "highlight-entry-open";

	const swatch = document.createElement("span");
	swatch.className = "highlight-entry-swatch";
	swatch.style.background = highlight.colour;

	const name = document.createElement("span");
	name.className = "highlight-entry-name";
	// An unnamed highlight is still recognisable by what it says.
	name.textContent = highlight.name || highlight.quote?.trim().slice(0, 60) || "Untitled highlight";

	const location = document.createElement("span");
	location.className = "highlight-entry-location";
	location.textContent = `Page ${highlight.page_number}`;

	open.append(swatch, name, location);

	const edit = document.createElement("button");
	edit.type = "button";
	edit.className = "highlight-entry-edit";
	edit.textContent = "Edit";
	edit.setAttribute("aria-label", `Edit ${name.textContent}`);

	const row = document.createElement("div");
	row.className = "highlight-entry-row";
	row.append(open, edit);
	entry.append(row);

	if (highlight.comment) {
		const comment = document.createElement("p");
		comment.className = "highlight-entry-comment preserve-lines";
		comment.textContent = highlight.comment;
		entry.append(comment);
	}

	return entry;
}

// Swaps one row for a form over the same highlight. Kept inside the resource
// popup because that is where the notes are read, and the reader's popup only
// ever deals with the selection being made now.
function renderHighlightEditor(highlight) {
	const form = document.createElement("form");
	form.className = "highlight-editor";

	const name = document.createElement("input");
	name.type = "text";
	name.className = "form-control form-control-sm";
	name.maxLength = 64;
	name.placeholder = "Name this highlight";
	name.setAttribute("aria-label", "Highlight name");
	name.value = highlight.name || "";

	const comment = document.createElement("textarea");
	comment.className = "form-control form-control-sm";
	comment.rows = 3;
	comment.maxLength = 1000;
	comment.placeholder = "Add a comment";
	comment.setAttribute("aria-label", "Highlight comment");
	comment.value = highlight.comment || "";

	const colours = createColourChooser(highlight.colour);

	const error = document.createElement("p");
	error.className = "highlight-editor-error";
	error.hidden = true;

	const remove = document.createElement("button");
	remove.type = "button";
	remove.className = "btn btn-outline-danger btn-sm me-auto";
	remove.textContent = "Delete";

	const cancel = document.createElement("button");
	cancel.type = "button";
	cancel.className = "btn btn-outline-secondary btn-sm";
	cancel.textContent = "Cancel";

	const save = document.createElement("button");
	save.type = "submit";
	save.className = "btn btn-primary btn-sm";
	save.textContent = "Save";

	const actions = document.createElement("div");
	actions.className = "highlight-actions";
	actions.append(remove, cancel, save);

	form.append(name, comment, colours.element, error, actions);

	const resourceId = Number(highlight.l_resource_id);

	function fail(text) {
		error.textContent = text;
		error.hidden = false;
	}

	async function submit(request) {
		save.disabled = true;
		remove.disabled = true;
		error.hidden = true;

		try {
			const response = await fetch(
				`/api/highlights/${highlight.l_resource_highlight_id}`,
				request,
			);
			if (!response.ok) {
				const body = await response.json().catch(() => ({}));
				fail(body.error || "The highlight could not be saved.");
				return;
			}

			// Re-read rather than patching locally, so the list shows what was
			// actually stored.
			await showResourceHighlights(resourceId);
		} catch {
			fail("The highlight could not be saved.");
		} finally {
			save.disabled = false;
			remove.disabled = false;
		}
	}

	form.addEventListener("submit", (event) => {
		event.preventDefault();
		submit({
			method: "PATCH",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				name: name.value,
				colour: colours.colour(),
				comment: comment.value,
			}),
		});
	});

	remove.addEventListener("click", () => {
		if (window.confirm("Delete this highlight?")) {
			submit({ method: "DELETE" });
		}
	});

	cancel.addEventListener("click", () => showResourceHighlights(resourceId));

	return form;
}

function openDetail(card) {
	selectedResource = { ...card.dataset };

	document.getElementById("detail-title").textContent = selectedResource.title;
	document.getElementById("detail-author").textContent = selectedResource.author;
	document.getElementById("detail-description").textContent = selectedResource.description;

	detailCanvas.dataset.location = selectedResource.location;
	detailCanvas.classList.remove("is-loaded");
	detailCanvas.closest(".resource-thumb").classList.remove("is-failed");
	renderFirstPage(detailCanvas, THUMBNAIL_WIDTH).catch(() => markFailed(detailCanvas));
	showResourceHighlights(Number(selectedResource.id));

	detailModal.show();
}

detailHighlights.addEventListener("click", (event) => {
	const entry = event.target.closest(".highlight-entry");
	if (!entry || !selectedResource) {
		return;
	}

	const highlightId = Number(entry.dataset.highlightId);

	if (event.target.closest(".highlight-entry-edit")) {
		const highlight = loadedHighlights.find(
			(candidate) => candidate.l_resource_highlight_id === highlightId,
		);
		if (highlight) {
			entry.replaceChildren(renderHighlightEditor(highlight));
		}
		return;
	}

	if (!event.target.closest(".highlight-entry-open")) {
		return;
	}

	const resource = selectedResource;
	document.getElementById("detail-modal").addEventListener(
		"hidden.bs.modal",
		() => openReader(resource, highlightId),
		{ once: true },
	);
	detailModal.hide();
});

const bookGrid = document.getElementById("book-grid");

bookGrid.addEventListener("click", (event) => {
	const card = event.target.closest(".resource-card");
	if (card) {
		openDetail(card);
	}
});

bookGrid.addEventListener("keydown", (event) => {
	if (event.key !== "Enter" && event.key !== " ") {
		return;
	}

	const card = event.target.closest(".resource-card");
	if (card) {
		event.preventDefault();
		openDetail(card);
	}
});

/* ---------- reader popup ---------- */

const readerModalElement = document.getElementById("reader-modal");
const readerModal = new bootstrap.Modal(readerModalElement);
const readerBody = document.getElementById("reader-body");
const readerPages = document.getElementById("reader-pages");
const readerStatus = document.getElementById("reader-status");
let pageObserver = null;

function resetReader() {
	pageObserver?.disconnect();
	pageObserver = null;
	readerPages.replaceChildren();
	readerStatus.textContent = "";
	readerHighlights = [];
	readerResource = null;
	focusedHighlightId = null;
	window.clearTimeout(focusClearTimer);
	focusClearTimer = null;
	hideHighlightPopup();
}

async function openReader(resource, focusHighlightId = null) {
	resetReader();
	document.getElementById("reader-title").textContent = resource.title;
	readerStatus.textContent = "Loading...";

	// Page width is now a layout dimension rather than just render sharpness, so
	// it has to be measured once the modal has actually been laid out. A cached
	// document resolves in a microtask, well before that would otherwise happen.
	const shown = new Promise((resolve) =>
		readerModalElement.addEventListener("shown.bs.modal", resolve, { once: true }));
	readerModal.show();

	let pdf;
	try {
		pdf = await loadDocument(resource.location);
	} catch {
		readerStatus.textContent = "";
		readerPages.replaceChildren(
			Object.assign(document.createElement("p"), {
				className: "text-secondary text-center py-5",
				textContent: "This document could not be opened.",
			}),
		);
		return;
	}

	readerStatus.textContent = `${pdf.numPages} pages`;
	readerResource = resource;
	readerHighlights = await loadHighlights(resource.id);

	// Page one sizes the placeholders for every page, so the reader has a stable
	// scroll height before anything has actually been rendered.
	const firstPage = await pdf.getPage(1);
	const { width, height } = firstPage.getViewport({ scale: 1 });

	await shown;
	const displayWidth = Math.min(Math.max(readerBody.clientWidth - 32, 600), 1000);
	const displayHeight = (displayWidth / width) * height;

	pageObserver = new IntersectionObserver((entries) => {
		for (const entry of entries) {
			if (!entry.isIntersecting) {
				continue;
			}

			const wrapper = entry.target;
			pageObserver.unobserve(wrapper);
			pdf.getPage(Number(wrapper.dataset.page))
				.then((page) => renderReaderPage(page, wrapper, displayWidth))
				.catch(() => wrapper.classList.add("is-failed"));
		}
	}, { root: readerBody, rootMargin: PRELOAD_MARGIN });

	for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber++) {
		const wrapper = createReaderPage(pageNumber, displayWidth, displayHeight);
		readerPages.append(wrapper);
		pageObserver.observe(wrapper);
	}

	if (focusHighlightId) {
		jumpToHighlight(focusHighlightId);
	}
}

const FOCUS_FLASH_MS = 2600;

// Placeholders are already the right height, so the scroll target is known
// before the page it lands on has rendered.
function jumpToHighlight(highlightId) {
	const rect = readerHighlights.find(
		(candidate) => candidate.l_resource_highlight_id === highlightId,
	);
	if (!rect) {
		return;
	}

	const wrapper = readerPages.querySelector(`.reader-page[data-page="${rect.page_number}"]`);
	if (!wrapper) {
		return;
	}

	focusedHighlightId = highlightId;
	readerBody.scrollTo({
		top: Math.max(wrapper.offsetTop + rect.y * wrapper.offsetHeight - 80, 0),
		behavior: "smooth",
	});
}

function startFocusCountdown() {
	if (focusClearTimer !== null) {
		return;
	}

	focusClearTimer = window.setTimeout(() => {
		focusClearTimer = null;
		focusedHighlightId = null;
		for (const drawn of readerPages.querySelectorAll(".reader-page.is-loaded")) {
			drawHighlights(drawn);
		}
	}, FOCUS_FLASH_MS);
}

/* ---------- creating highlights ---------- */

const SUGGESTED_COLOURS = ["#ffd54f", "#a5d6a7", "#90caf9", "#f48fb1", "#ce93d8"];

// A row of suggested swatches followed by a picker for anything else. Used by
// the create popup here and by the editor in the resource popup, so both offer
// the same choice. Returns the element plus a read of the current colour.
function createColourChooser(initialColour) {
	const element = document.createElement("div");
	element.className = "highlight-colours";
	element.setAttribute("role", "radiogroup");
	element.setAttribute("aria-label", "Highlight colour");

	let chosen = initialColour;

	const custom = document.createElement("input");
	custom.type = "color";
	custom.setAttribute("aria-label", "Custom highlight colour");

	const swatches = SUGGESTED_COLOURS.map((colour) => {
		const button = document.createElement("button");
		button.type = "button";
		button.className = "highlight-colour";
		button.dataset.colour = colour;
		button.style.background = colour;
		button.setAttribute("role", "radio");
		button.setAttribute("aria-label", `Colour ${colour}`);
		return button;
	});

	function choose(colour) {
		chosen = colour;
		for (const swatch of swatches) {
			const isChosen = swatch.dataset.colour === colour;
			swatch.classList.toggle("is-chosen", isChosen);
			swatch.setAttribute("aria-checked", String(isChosen));
		}
		// The picker doubles as the swatch for a colour that is not suggested, so
		// it only reads as chosen when none of the suggestions match.
		custom.value = colour;
		label.classList.toggle("is-chosen", !SUGGESTED_COLOURS.includes(colour));
	}

	const label = document.createElement("label");
	label.className = "highlight-colour highlight-colour-custom";
	label.title = "Any other colour";
	label.append(custom);

	element.append(...swatches, label);
	element.addEventListener("click", (event) => {
		const button = event.target.closest(".highlight-colour[data-colour]");
		if (button) {
			choose(button.dataset.colour);
		}
	});
	// "input" rather than "change", so dragging around the picker previews live.
	custom.addEventListener("input", () => choose(custom.value));

	choose(initialColour);

	return { element, colour: () => chosen, choose };
}

const highlightPopup = document.getElementById("highlight-popup");
const highlightForm = document.getElementById("highlight-form");
const highlightName = document.getElementById("highlight-name");
const highlightComment = document.getElementById("highlight-comment");
const highlightStart = document.getElementById("highlight-start");
const highlightSave = document.getElementById("highlight-save");
let pendingSelection = null;

const highlightColours = createColourChooser(SUGGESTED_COLOURS[0]);
document.getElementById("highlight-colours").replaceWith(highlightColours.element);

function hideHighlightPopup() {
	highlightPopup.hidden = true;
	highlightForm.hidden = true;
	highlightStart.hidden = false;
	highlightName.value = "";
	highlightComment.value = "";
	highlightColours.choose(SUGGESTED_COLOURS[0]);
	pendingSelection = null;
}

function pageBoxFor(rect) {
	const x = rect.left + rect.width / 2;
	const y = rect.top + rect.height / 2;

	for (const wrapper of readerPages.children) {
		const box = wrapper.getBoundingClientRect();
		if (x >= box.left && x <= box.right && y >= box.top && y <= box.bottom) {
			return { wrapper, box };
		}
	}

	return null;
}

// A selection produces one rectangle per line, each stored as a fraction of the
// page it falls on, so a highlight can even run across a page break.
function selectionToRects(range) {
	const rects = [];

	for (const rect of range.getClientRects()) {
		if (rect.width < 1 || rect.height < 1) {
			continue;
		}

		const found = pageBoxFor(rect);
		if (!found) {
			continue;
		}

		rects.push({
			page_number: Number(found.wrapper.dataset.page),
			x: (rect.left - found.box.left) / found.box.width,
			y: (rect.top - found.box.top) / found.box.height,
			width: rect.width / found.box.width,
			height: rect.height / found.box.height,
		});
	}

	return rects;
}

function offerHighlight() {
	const selection = window.getSelection();
	if (!selection || selection.isCollapsed || !selection.rangeCount) {
		hideHighlightPopup();
		return;
	}

	const range = selection.getRangeAt(0);
	const quote = selection.toString().trim();
	if (!readerPages.contains(range.commonAncestorContainer) || !quote) {
		hideHighlightPopup();
		return;
	}

	const rects = selectionToRects(range);
	if (!rects.length) {
		hideHighlightPopup();
		return;
	}

	pendingSelection = { quote, rects };

	// Positioned inside the scrolling body, so it stays with the text.
	const bounds = range.getBoundingClientRect();
	const host = readerBody.getBoundingClientRect();
	highlightPopup.hidden = false;
	highlightForm.hidden = true;
	highlightStart.hidden = false;
	highlightPopup.style.left =
		`${bounds.left - host.left + readerBody.scrollLeft + bounds.width / 2}px`;
	highlightPopup.style.top = `${bounds.top - host.top + readerBody.scrollTop}px`;
}

readerBody.addEventListener("mouseup", (event) => {
	// Clicking the popup itself clears the selection; that must not dismiss it
	// before the click lands.
	if (highlightPopup.contains(event.target)) {
		return;
	}

	window.setTimeout(offerHighlight, 0);
});

highlightStart.addEventListener("click", () => {
	highlightStart.hidden = true;
	highlightForm.hidden = false;
	highlightName.focus();
});

document.getElementById("highlight-cancel").addEventListener("click", hideHighlightPopup);

highlightForm.addEventListener("submit", async (event) => {
	event.preventDefault();
	if (!pendingSelection || !readerResource) {
		return;
	}

	highlightSave.disabled = true;
	try {
		const response = await fetch("/api/highlights", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				l_resource_id: Number(readerResource.id),
				name: highlightName.value,
				colour: highlightColours.colour(),
				quote: pendingSelection.quote,
				comment: highlightComment.value,
				rects: pendingSelection.rects,
			}),
		});

		if (response.ok) {
			// Re-read rather than patching locally, so what is drawn is what was
			// actually stored.
			readerHighlights = await loadHighlights(readerResource.id);
			for (const wrapper of readerPages.querySelectorAll(".reader-page.is-loaded")) {
				drawHighlights(wrapper);
			}
			window.getSelection()?.removeAllRanges();
			hideHighlightPopup();
		}
	} finally {
		highlightSave.disabled = false;
	}
});

document.getElementById("detail-read").addEventListener("click", () => {
	const resource = selectedResource;
	if (!resource) {
		return;
	}

	// Wait for the detail popup to finish closing; Bootstrap will not open a
	// second modal cleanly while the first is still transitioning out.
	document.getElementById("detail-modal").addEventListener(
		"hidden.bs.modal",
		() => openReader(resource),
		{ once: true },
	);
	detailModal.hide();
});

document.getElementById("reader-modal").addEventListener("hidden.bs.modal", resetReader);

/* ---------- adding and removing resources ---------- */

function reloadGrid() {
	htmx.ajax("GET", "/api/resources/all_html", { target: "#book-grid", swap: "innerHTML" });
}

const uploadModal = new bootstrap.Modal("#upload-modal");
const uploadForm = document.getElementById("upload-form");
const uploadFile = document.getElementById("upload-file");
const uploadFilename = document.getElementById("upload-filename");
const uploadError = document.getElementById("upload-error");
const uploadSubmit = document.getElementById("upload-submit");
const dropzone = document.getElementById("dropzone");

function showUploadError(text) {
	uploadError.textContent = text;
	uploadError.hidden = !text;
}

function setChosenFile(file) {
	if (file && file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
		showUploadError("Only PDF files can be uploaded.");
		return;
	}

	// Assigning a DataTransfer list is the only way to put a dropped file into
	// a file input, so the form submits identically either way.
	const transfer = new DataTransfer();
	if (file) {
		transfer.items.add(file);
	}
	uploadFile.files = transfer.files;
	uploadFilename.textContent = file ? file.name : "";
	showUploadError("");
}

document.getElementById("upload-browse").addEventListener("click", () => uploadFile.click());
uploadFile.addEventListener("change", () => setChosenFile(uploadFile.files[0]));

for (const eventName of ["dragenter", "dragover"]) {
	dropzone.addEventListener(eventName, (event) => {
		event.preventDefault();
		dropzone.classList.add("is-active");
	});
}

for (const eventName of ["dragleave", "drop"]) {
	dropzone.addEventListener(eventName, (event) => {
		event.preventDefault();
		dropzone.classList.remove("is-active");
	});
}

dropzone.addEventListener("drop", (event) => setChosenFile(event.dataTransfer.files[0]));

uploadForm.addEventListener("submit", async (event) => {
	event.preventDefault();
	showUploadError("");

	if (!uploadFile.files.length) {
		showUploadError("Choose a PDF to upload.");
		return;
	}

	uploadSubmit.disabled = true;
	uploadSubmit.textContent = "Uploading...";

	try {
		const response = await fetch("/api/resources/upload", {
			method: "POST",
			body: new FormData(uploadForm),
		});
		const body = await response.json().catch(() => ({}));

		if (!response.ok) {
			showUploadError(body.error || "The resource could not be saved.");
			return;
		}

		uploadForm.reset();
		setChosenFile(null);
		uploadModal.hide();
		reloadGrid();
	} catch {
		showUploadError("The upload could not be sent.");
	} finally {
		uploadSubmit.disabled = false;
		uploadSubmit.textContent = "Add resource";
	}
});

const detailRemove = document.getElementById("detail-remove");

detailRemove.addEventListener("click", async () => {
	const resource = selectedResource;
	if (!resource) {
		return;
	}

	if (!window.confirm(`Remove "${resource.title}"? This also deletes the PDF.`)) {
		return;
	}

	detailRemove.disabled = true;
	try {
		const response = await fetch(`/api/resources/${resource.id}`, { method: "DELETE" });
		if (response.ok) {
			detailModal.hide();
			reloadGrid();
		}
	} finally {
		detailRemove.disabled = false;
	}
});

/* ---------- library assistant ---------- */

const chatLog = document.getElementById("chat-log");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatSend = document.getElementById("chat-send");

function appendMessage(variant, text) {
	document.getElementById("chat-hint")?.remove();

	const message = document.createElement("p");
	message.className = `chat-message preserve-lines ${variant}`;
	message.textContent = text;
	chatLog.append(message);
	chatLog.scrollTop = chatLog.scrollHeight;

	return message;
}

function setChatPending(pending) {
	chatInput.disabled = pending;
	chatSend.disabled = pending;
	chatSend.textContent = pending ? "Asking..." : "Send";
}

async function askAssistant(question) {
	appendMessage("is-student", question);
	// The model runs locally and regularly takes half a minute, so the wait
	// needs to be visible rather than looking like a dropped request.
	const pending = appendMessage("is-pending", "Searching the library...");
	setChatPending(true);

	try {
		const response = await fetch("/api/chat/send_message", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ message: question }),
		});
		const body = await response.json().catch(() => ({}));

		pending.remove();
		if (response.ok) {
			appendMessage("is-assistant", body.reply);
		} else {
			appendMessage("is-error", body.error || "The library assistant could not answer.");
		}
	} catch {
		pending.remove();
		appendMessage("is-error", "The library assistant could not be reached.");
	} finally {
		setChatPending(false);
		chatLog.scrollTop = chatLog.scrollHeight;
	}
}

chatForm.addEventListener("submit", (event) => {
	event.preventDefault();

	const question = chatInput.value.trim();
	if (!question) {
		return;
	}

	chatInput.value = "";
	askAssistant(question);
});

document.getElementById("chat-modal").addEventListener("shown.bs.modal", () => chatInput.focus());

/* ---------- wiring ---------- */

document.body.addEventListener("htmx:afterSwap", (event) => observeThumbnails(event.target));
observeThumbnails(document);
