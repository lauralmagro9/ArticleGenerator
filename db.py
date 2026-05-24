import os
import json
from datetime import datetime
from typing import Dict, Any, Optional
from config import logger

DB_FILE = 'processed_files.json'

def load_db() -> Dict[str, Any]:
    """Loads the database from the JSON file. Creates it if it doesn't exist."""
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read database file: {e}. Starting with empty database.")
        return {}

def save_db(data: Dict[str, Any]) -> None:
    """Saves the database to the JSON file."""
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to write database file: {e}")

def is_processed(file_id: str) -> bool:
    """Checks if a file has been successfully processed."""
    db = load_db()
    file_info = db.get(file_id)
    return file_info is not None and file_info.get('status') == 'completed'

def get_file_status(file_id: str) -> Optional[str]:
    """Gets the status of a file."""
    db = load_db()
    file_info = db.get(file_id)
    return file_info.get('status') if file_info else None

def mark_processing(file_id: str, file_name: str) -> None:
    """Marks a file as currently processing."""
    db = load_db()
    db[file_id] = {
        'name': file_name,
        'status': 'processing',
        'started_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat()
    }
    save_db(db)
    logger.info(f"Marked file {file_name} ({file_id}) as processing.")

def mark_completed(file_id: str, wp_post_id: int, wp_post_link: str) -> None:
    """Marks a file as completed and stores WordPress post reference."""
    db = load_db()
    if file_id in db:
        db[file_id]['status'] = 'completed'
        db[file_id]['wp_post_id'] = wp_post_id
        db[file_id]['wp_post_link'] = wp_post_link
        db[file_id]['completed_at'] = datetime.now().isoformat()
        db[file_id]['updated_at'] = datetime.now().isoformat()
        save_db(db)
        logger.info(f"Marked file {db[file_id]['name']} ({file_id}) as completed. WP Post ID: {wp_post_id}")
    else:
        logger.warning(f"Attempted to mark unknown file {file_id} as completed.")

def mark_failed(file_id: str, error_message: str) -> None:
    """Marks a file as failed with an error message."""
    db = load_db()
    if file_id in db:
        db[file_id]['status'] = 'failed'
        db[file_id]['error'] = error_message
        db[file_id]['failed_at'] = datetime.now().isoformat()
        db[file_id]['updated_at'] = datetime.now().isoformat()
        save_db(db)
        logger.error(f"Marked file {db[file_id]['name']} ({file_id}) as failed. Error: {error_message}")
    else:
        logger.warning(f"Attempted to mark unknown file {file_id} as failed.")
