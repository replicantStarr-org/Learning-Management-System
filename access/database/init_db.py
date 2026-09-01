import os
import sqlite3

DATA_DIR = "data"
DATABASE_NAME = os.path.join(DATA_DIR, "users.db")

os.makedirs(DATA_DIR, exist_ok=True)

with sqlite3.connect(DATABASE_NAME) as connection:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            hashed_password TEXT NOT NULL,
            created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
