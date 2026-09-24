def load_database_chunks() -> list[dict[str, Any]]:
    db_path = resolve_db_path()
    if not db_path.exists():
        # In containers, rag-server may not have direct filesystem access to SQLite.
        # Fallback to database-service HTTP API so tier_1 facts remain available.
        try:
            response = requests.get(f"{DATABASE_SERVICE_URL}/students", timeout=10)
            response.raise_for_status()
            students = response.json()

            chunks: list[dict[str, Any]] = [
                {
                    "chunk_id": "db_service_student_count",
                    "source_id": "database-service:/students",
                    "authority_tier": "tier_1",
                    "text": f"Student count is {len(students)}.",
                    "metadata": {"source_type": "database_service", "metric": "count"},
                    "indexed_at": now_iso(),
                }
            ]

            for row in students[:500]:
                sid = row.get("student_id", "unknown")
                sname = row.get("student_name", "unknown")
                subject = row.get("subject_code", "unknown")
                chunks.append(
                    {
                        "chunk_id": f"db_service_student_{sid}",
                        "source_id": "database-service:/students",
                        "authority_tier": "tier_1",
                        "text": (
                            f"Student record: student_id={sid}, "
                            f"student_name={sname}, subject_code={subject}."
                        ),
                        "metadata": {"source_type": "database_service", "table": "students"},
                        "indexed_at": now_iso(),
                    }
                )

            return chunks
        except Exception as exc:
            return [
                {
                    "chunk_id": "db_missing",
                    "source_id": str(db_path.relative_to(APP_DIR)) if db_path.is_absolute() else str(db_path),
                    "authority_tier": "tier_1",
                    "text": (
                        f"Database file not found: {db_path}. "
                        f"database-service fallback failed: {exc}"
                    ),
                    "metadata": {"source_type": "database", "exists": False},
                    "indexed_at": now_iso(),
                }
            ]

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    chunks: list[dict[str, Any]] = []
    try:
        tables = [
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        chunks.append(
            {
                "chunk_id": "db_schema",
                "source_id": str(db_path.relative_to(APP_DIR)),
                "authority_tier": "tier_1",
                "text": f"Database tables: {', '.join(tables)}",
                "metadata": {"source_type": "database", "tables": tables},
                "indexed_at": now_iso(),
            }
        )

        if "students" in tables:
            row = conn.execute("SELECT COUNT(*) AS count FROM students").fetchone()
            count = row["count"] if row else 0
            chunks.append(
                {
                    "chunk_id": "db_student_count",
                    "source_id": str(db_path.relative_to(APP_DIR)),
                    "authority_tier": "tier_1",
                    "text": f"Student count is {count}.",
                    "metadata": {"source_type": "database", "table": "students", "metric": "count"},
                    "indexed_at": now_iso(),
                }
            )

            for row in conn.execute(
                "SELECT student_id, student_name, subject_code FROM students ORDER BY student_id LIMIT 500"
            ).fetchall():
                r = dict(row)
                chunks.append(
                    {
                        "chunk_id": f"db_student_{r['student_id']}",
                        "source_id": str(db_path.relative_to(APP_DIR)),
                        "authority_tier": "tier_1",
                        "text": (
                            f"Student record: student_id={r['student_id']}, "
                            f"student_name={r['student_name']}, subject_code={r['subject_code']}."
                        ),
                        "metadata": {"source_type": "database", "table": "students"},
                        "indexed_at": now_iso(),
                    }
                )
    finally:
        conn.close()

    return chunks