import os
import re
import runpy
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path

from config.review_config import ServiceConfig, service_path


CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:[`\"\[]?)([\w-]+)(?:[`\"\]]?)\s*\(.*?\)\s*(?:;|(?=[\"']{3}))",
    re.IGNORECASE | re.DOTALL,
)


@contextmanager
def _working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _find_inputs(database_dir: Path) -> tuple[Path | None, list[Path]]:
    python_files = sorted(database_dir.glob("*.py"))
    init_file = next(
        (p for p in python_files if "init" in p.stem.lower() and any(x in p.stem.lower() for x in ("db", "data"))),
        None,
    )
    return init_file, sorted(database_dir.glob("*.sql"))


def collect(repo_root: Path, service: ServiceConfig) -> tuple[bool, str]:
    database_dir = service_path(repo_root, service) / "database"
    if not database_dir.is_dir():
        return False, f"Missing database directory: {database_dir.relative_to(repo_root)}"

    init_file, sql_files = _find_inputs(database_dir)
    if init_file is None:
        return False, "No database initializer with 'init' and either 'db' or 'data' in its name was found."

    source_files = [init_file, *sql_files]
    statements: list[tuple[str, str]] = []
    for source in source_files:
        text = source.read_text(encoding="utf-8")
        statements.extend((match.group(1), match.group(0).strip()) for match in CREATE_TABLE.finditer(text))

    if not statements:
        return False, "No CREATE TABLE statements were found in the database initializer or SQL files."

    with tempfile.TemporaryDirectory(prefix=f"agentic-{service.key}-db-") as temporary:
        work_dir = Path(temporary)
        for source in database_dir.iterdir():
            if source.is_file():
                shutil.copy2(source, work_dir / source.name)

        old_database_path = os.environ.get("DATABASE_PATH")
        old_database_name = os.environ.get("DATABASE_NAME")
        os.environ["DATABASE_PATH"] = str(work_dir)
        os.environ.setdefault("DATABASE_NAME", f"{service.key}.db")
        try:
            with _working_directory(work_dir):
                runpy.run_path(str(work_dir / init_file.name), run_name="__main__")
        except Exception as exc:
            return False, f"Database initializer failed in isolation: {type(exc).__name__}: {exc}"
        finally:
            if old_database_path is None:
                os.environ.pop("DATABASE_PATH", None)
            else:
                os.environ["DATABASE_PATH"] = old_database_path
            if old_database_name is None:
                os.environ.pop("DATABASE_NAME", None)
            else:
                os.environ["DATABASE_NAME"] = old_database_name

        databases = sorted(work_dir.rglob("*.db"))
        if not databases:
            return False, "Database initializer did not create a .db file."

        counts: list[str] = []
        failures: list[str] = []
        table_names = list(dict.fromkeys(name for name, _ in statements))
        connection = sqlite3.connect(databases[0])
        try:
            for table in table_names:
                try:
                    count = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                except sqlite3.Error as exc:
                    failures.append(f"{table}: query failed ({exc})")
                    continue
                counts.append(f"{table}={count}")
                if count < 5:
                    failures.append(f"{table}: expected at least 5 seeded rows, found {count}")
        finally:
            connection.close()

    statement_text = "\n\n".join(statement for _, statement in statements)
    evidence = f"Seed counts: {', '.join(counts)}.\n\nCREATE TABLE statements:\n{statement_text}"
    if failures:
        return False, "; ".join(failures) + f"\n\n{evidence}"
    return True, evidence
