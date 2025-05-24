import apsw
import sqlite_vec
import os
import time
import numpy as np
import hashlib
import json

def load_config():
    config_path = 'config.json'
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
            memory_config = config.get("memory", {})
    return memory_config


def create_db():
    memory_config = load_config()
    db_file = memory_config['db_store']
    # Check if database file exists
    db_exists = os.path.exists(db_file)
    
    try:
        print(f"🔄 {'Opening' if db_exists else 'Creating'} SQLite database '{db_file}'")
        db = apsw.Connection(db_file)
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
            
            # Create embeddings table for vector storage
            db.execute(
                """
                CREATE TABLE embeddings(
                  id INTEGER PRIMARY KEY,
                  message_id INTEGER,
                  role TEXT,
                  content TEXT,
                  embedding BLOB,
                  timestamp INTEGER,
                  FOREIGN KEY(message_id) REFERENCES messages(id)
                );
                """
            )
            
            print(f"✅ Created SQLite database tables for storage")
        else:
            # Verify tables exist
            cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
            if not cursor.fetchone():
                db.execute("CREATE TABLE messages(id INTEGER PRIMARY KEY, message TEXT);")
                print("✅ Created missing messages table")
                
            cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='embeddings'")
            if not cursor.fetchone():
                db.execute("""
                    CREATE TABLE embeddings(
                      id INTEGER PRIMARY KEY,
                      message_id INTEGER,
                      role TEXT,
                      content TEXT,
                      embedding BLOB,
                      timestamp INTEGER,
                      FOREIGN KEY(message_id) REFERENCES messages(id)
                    );
                """)
                print("✅ Created missing embeddings table")
            
        return db
    except Exception as create_error:
        print(f"❌ Error with SQLite database: {str(create_error)}")
        return None
    
