import os
import config
from datetime import datetime

from typing import Dict, Any, Tuple
from config import logger

def is_audio_file(file_info: Dict[str, Any]) -> bool:
        """Determines if a file is an audio file based on MIME type or extension."""
        name = file_info.get('name', '').lower()
        mime_type = file_info.get('mimeType', '').lower()
        
        # 1. Check MIME type
        if mime_type.startswith('audio/'):
            return True
            
        # 2. Check extension
        _, ext = os.path.splitext(name)
        if ext in config.AUDIO_EXTENSIONS:
            return True
            
        return False


def get_date_from_filename(filename):
    try:
        part_date = filename.split("-")[1:]
        part_date_clean =[pd.split(".")[0] for pd in part_date]
        str_date = "-".join([part_date_clean[0], part_date_clean[1], part_date_clean[2].split(" ")[0]])
        return datetime.strptime(str_date, "%Y-%m-%d")
    except Exception as e:
        logger.info(f"Could not get date from filename. Defaulting to current date...")
        return datetime.now()

def get_root_name(file_name: str) -> Tuple[str, int]:
    """Extracts the root name from a filename (everything up to the last underscore).
    
    The file extension is stripped first, then the root is determined by
    splitting on '_' and joining all parts except the last one.
    Files without underscores in the stem return the full stem as root.
    
    Examples:
        'setas_cantharellus_1.mp3' -> 'setas_cantharellus'
        'setas_cantharellus_2.mp3' -> 'setas_cantharellus'
        'single_file.mp3'         -> 'single_file' (no second underscore -> standalone)
        'nounderscores.mp3'       -> 'nounderscores'
    """
    stem = os.path.splitext(file_name)[0]
    main_name = stem.split("-")[0]
    last_underscore = stem.rfind('_')
    if last_underscore == -1:
        # No underscore at all – the whole stem is the root
        return main_name, 0
    suffix = main_name[last_underscore + 1:]
    # Only treat it as a group suffix if it's numeric
    if suffix.isdigit():
        return main_name[:last_underscore], int(suffix)
    # Non-numeric suffix – the whole stem is the root (standalone)
    return main_name, 0


def get_sort_key(file_name: str) -> int:
    """Extracts the numeric suffix after the last underscore for sorting.
    
    Returns 0 if the filename has no numeric suffix.
    """
    stem = os.path.splitext(file_name)[0]
    last_underscore = stem.rfind('_')
    if last_underscore == -1:
        return 0
    suffix = stem[last_underscore + 1:]
    if suffix.isdigit():
        return int(suffix)
    return 0


def clean_local_file(local_path: str) -> None:
    """Safely deletes a local file if it exists."""
    if local_path and os.path.exists(local_path):
        try:
            logger.info(f"Cleaning up local file: {local_path}")
            os.remove(local_path)
            logger.info("Local file cleanup completed.")
        except Exception as e:
            logger.warning(f"Failed to delete local file {local_path}: {e}")

def get_category_id(category, categories_map):
    if not category:
        return None
    category_id = categories_map.get(category, None)
    if not category_id:
        # Try case-insensitive lookup
        for name, cid in categories_map.items():
            if name.lower() == category.lower():
                category_id = cid
                break
    if category_id:
        logger.info(f"Mapped category '{category}' to WordPress ID: {category_id}")
    else:
        logger.warning(f"Could not map category '{category}' to a WordPress ID. Posting without category.")
    return category_id