import sqlite3
import os

def create_database() -> string:
    db_name = os.getenv("DATABASE_NAME")
    db_con = sqlite3.connect(db_name)

    return db_con

def construct_database(db_connection: string) -> None:
    with open('construct_db.sql', 'r') as script:
        cursor = db_connection.cursor()
        cursor.executescript(script)
        cursor.commit()
        cursor.close()

def main():
    db = create_database()
    construct_database(db)
    db.close()

if __name__ == "__main__":
    main()
