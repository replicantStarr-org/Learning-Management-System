from pathlib import Path
import os

def database_exists() -> bool:
    db_name = os.getenv("DATABASE_NAME")
    db_path = f"/database/{db_name}"

    file_path = Path(db_path)

    if file_path.is_file():
        return True

    return False

