import sqlite3
import os
from pathlib import Path

def create_database() -> str:
    db_name = os.getenv("DATABASE_NAME")
    db_path = os.getenv("DATABASE_PATH")
    db_con = sqlite3.connect(db_path + "/" + db_name)

    return db_con

def construct_database(db_connection: str) -> None:
    with open('construct_db.sql', 'r') as script:
        cursor = db_connection.cursor()
        cursor.executescript(script.read())
        db_connection.commit()
        cursor.close()

def database_exists():
    db_name = os.getenv("DATABASE_NAME")
    db_path = os.getenv("DATABASE_PATH")
    path = Path(db_path + "/" + db_name)
    return path.exists()

def main():
    if database_exists():
        return

    db = create_database()
    construct_database(db)
    db.close()

if __name__ == "__main__":
    main()
