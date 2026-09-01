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

function markFailed(canvas) {
	canvas.closest(".resource-thumb")?.classList.add("is-failed");
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
let selectedResource = null;

function openDetail(card) {
	selectedResource = { ...card.dataset };

	document.getElementById("detail-title").textContent = selectedResource.title;
	document.getElementById("detail-author").textContent = selectedResource.author;
	document.getElementById("detail-description").textContent = selectedResource.description;

	detailCanvas.dataset.location = selectedResource.location;
	detailCanvas.classList.remove("is-loaded");
	detailCanvas.closest(".resource-thumb").classList.remove("is-failed");
	renderFirstPage(detailCanvas, THUMBNAIL_WIDTH).catch(() => markFailed(detailCanvas));

	detailModal.show();
}

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

const readerModal = new bootstrap.Modal("#reader-modal");
const readerBody = document.getElementById("reader-body");
const readerPages = document.getElementById("reader-pages");
const readerStatus = document.getElementById("reader-status");
let pageObserver = null;

function resetReader() {
	pageObserver?.disconnect();
	pageObserver = null;
	readerPages.replaceChildren();
	readerStatus.textContent = "";
}

async function openReader(resource) {
	resetReader();
	document.getElementById("reader-title").textContent = resource.title;
	readerStatus.textContent = "Loading...";
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

	// Page one sets the placeholder bitmap ratio for every page, so the reader
	// has a stable scroll height before anything has actually been rendered.
	const firstPage = await pdf.getPage(1);
	const { width, height } = firstPage.getViewport({ scale: 1 });
	const displayWidth = Math.min(Math.max(readerBody.clientWidth - 32, 600), 1000);

	pageObserver = new IntersectionObserver((entries) => {
		for (const entry of entries) {
			if (!entry.isIntersecting) {
				continue;
			}

			const canvas = entry.target;
			pageObserver.unobserve(canvas);
			pdf.getPage(Number(canvas.dataset.page))
				.then((page) => renderPage(page, canvas, displayWidth))
				.catch(() => canvas.classList.add("is-failed"));
		}
	}, { root: readerBody, rootMargin: PRELOAD_MARGIN });

	for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber++) {
		const canvas = document.createElement("canvas");
		canvas.className = "reader-page";
		canvas.dataset.page = String(pageNumber);
		canvas.width = width;
		canvas.height = height;
		readerPages.append(canvas);
		pageObserver.observe(canvas);
	}
}

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

/* ---------- wiring ---------- */

document.body.addEventListener("htmx:afterSwap", (event) => observeThumbnails(event.target));
observeThumbnails(document);
