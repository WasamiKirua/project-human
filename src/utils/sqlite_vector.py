import apsw
import sqlite_vec
import os
import time
import numpy as np
import hashlib
import json

class SQLiteComponent:
    def __init__(self):
        # Load configuration
        self.config = self.load_config()
        self.db_file = self.config['db_store']

    def load_config(self):
        config_path = 'config.json'
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
                memory_config = config.get("memory", {})
        return memory_config

    def create_db(self):
        # Check if database file exists
        db_exists = os.path.exists(self.db_file)

        try:
            print(f"[GUI] --> [SQLite] 🔄 {'Opening' if db_exists else 'Creating'} SQLite database '{self.db_file}'")
            db = apsw.Connection(self.db_file)
            db.enable_load_extension(True)
            sqlite_vec.load(db)
            db.enable_load_extension(False)

            if not db_exists:
                # Create a simple messages table with just id and message
                db.execute(
                    """
                    CREATE TABLE messages(
                      id INTEGER PRIMARY KEY,
                      message TEXT
                    );
                    """
                )

                print(f"[GUI] --> [SQLite] ✅ Created SQLite database tables for storage")
            else:
                # Verify tables exist
                cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
                if not cursor.fetchone():
                    db.execute("CREATE TABLE messages(id INTEGER PRIMARY KEY, message TEXT);")
                    print("[GUI] --> [SQLite] ✅ Created missing messages table")

            return db
        except Exception as create_error:
            print(f"[GUI] --> [SQLite] ❌ Error with SQLite database: {str(create_error)}")
            return None

    def store_conversations(self, user_input, ai_response):
        # Connect to existing database
        db = apsw.Connection(self.db_file)
        db.enable_load_extension(True)
        sqlite_vec.load(db)
        db.enable_load_extension(False)

        # Get the next ID
        cursor = db.execute("SELECT MAX(id) FROM messages")
        max_id_row = cursor.fetchone()
        max_id = max_id_row[0] if max_id_row[0] is not None else 0
        next_id = max_id + 1

        entries = []
        entries.append({
            "User": user_input,
            "Assistant": ai_response
        })

        try:
            # Convert the entries list to a JSON string
            entries_json = json.dumps(entries)

            db.execute(
                "INSERT INTO messages(id, message) VALUES(?, ?)",
                [next_id, entries_json] # Insert the JSON string
            )
            next_id += 1
        except Exception as insert_error:
            print(f"[LLM] --> [SQLite] ❌ Error inserting message: {str(insert_error)}")

