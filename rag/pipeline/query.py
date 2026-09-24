def load_report_chunks() -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for name in REPORT_FILES:
        path = REPORTS_DIR / name
        if not path.exists():
            continue

        text = ""
        try:
            if path.suffix == ".json":
                text = json.dumps(json.loads(path.read_text(encoding="utf-8")), indent=2)
            else:
                text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            text = path.read_text(encoding="utf-8", errors="ignore")

        for i, chunk in enumerate(chunk_text(text), start=1):
            chunks.append(
                {
                    "chunk_id": f"{path.stem}_{i}",
                    "source_id": f"reports/{name}",
                    "authority_tier": "tier_2",
                    "text": chunk,
                    "metadata": {"source_type": "report", "file": name},
                    "indexed_at": now_iso(),
                }
            )

    return chunks

def load_repository_chunks() -> list[dict[str, Any]]:
    ignored = {".git", ".venv", "__pycache__", "node_modules", "chroma"}
    files: list[str] = []

    for root, dirs, filenames in os.walk(APP_DIR, topdown=True, followlinks=False, onerror=lambda e: None):
        # Prune ignored and symlinked directories to avoid scanning protected mounts.
        pruned_dirs: list[str] = []
        for directory_name in dirs:
            if directory_name in ignored:
                continue
            directory_path = Path(root) / directory_name
            try:
                if directory_path.is_symlink():
                    continue
            except OSError:
                continue
            pruned_dirs.append(directory_name)
        dirs[:] = pruned_dirs

        for filename in filenames:
            file_path = Path(root) / filename
            try:
                if file_path.is_symlink():
                    continue
                rel = file_path.relative_to(APP_DIR)
                files.append(str(rel).replace("\\", "/"))
            except (OSError, ValueError):
                continue

    text = "Repository files include: " + ", ".join(sorted(files[:400]))
    return [
        {
            "chunk_id": "repo_index",
            "source_id": "repository",
            "authority_tier": "tier_3",
            "text": text,
            "metadata": {"source_type": "repository", "file_count": len(files)},
            "indexed_at": now_iso(),
        }
    ]
