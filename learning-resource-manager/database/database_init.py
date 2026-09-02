import os
import sqlite3
from pathlib import Path


def database_file() -> Path:
    db_name = os.environ["DATABASE_NAME"]
    db_path = os.environ["DATABASE_PATH"]

    return Path(db_path) / db_name

def create_database() -> sqlite3.Connection:
    return sqlite3.connect(database_file())

def construct_database(db_connection: sqlite3.Connection) -> None:
    with open('construct_db.sql') as script:
        cursor = db_connection.cursor()
        cursor.executescript(script.read())
        db_connection.commit()
        cursor.close()

def populate_database(db_connection: sqlite3.Connection) -> None:
    with open('populate_db.sql') as script:
        cursor = db_connection.cursor()
        cursor.executescript(script.read())
        db_connection.commit()
        cursor.close()

def database_exists() -> bool:
    return database_file().exists()

def main() -> None:
    if database_exists():
        return

    db = create_database()
    construct_database(db)
    populate_database(db)
    db.close()

if __name__ == "__main__":
    main()
