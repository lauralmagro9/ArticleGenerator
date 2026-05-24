import os
import io
import mimetypes
from typing import List, Dict, Any, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

import config
from config import logger

# List of common audio file extensions to match if MIME type is generic
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.flac', '.ogg', '.aac', '.wma', '.mp4', '.m4b', '.opus', '.webm'}

def get_drive_service():
    """Initializes and returns the Google Drive API client using Service Account credentials."""
    creds = service_account.Credentials.from_service_account_file(
        config.GOOGLE_APPLICATION_CREDENTIALS,
        scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    return build('drive', 'v3', credentials=creds)

def is_audio_file(file_info: Dict[str, Any]) -> bool:
    """Determines if a file is an audio file based on MIME type or extension."""
    name = file_info.get('name', '').lower()
    mime_type = file_info.get('mimeType', '').lower()
    
    # 1. Check MIME type
    if mime_type.startswith('audio/'):
        return True
        
    # 2. Check extension
    _, ext = os.path.splitext(name)
    if ext in AUDIO_EXTENSIONS:
        return True
        
    return False

def list_audio_files() -> List[Dict[str, Any]]:
    """
    Lists all non-trashed audio files in the monitored Google Drive folder.
    Returns a list of dictionaries with 'id', 'name', and 'mimeType'.
    """
    try:
        service = get_drive_service()
        query = f"'{config.GOOGLE_DRIVE_FOLDER_ID}' in parents and trashed = false"
        
        logger.info(f"Scanning Google Drive folder '{config.GOOGLE_DRIVE_FOLDER_ID}'...")
        
        results = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, mimeType, createdTime)",
            pageSize=100
        ).execute()
        
        files = results.get('files', [])
        audio_files = [f for f in files if is_audio_file(f)]
        
        logger.info(f"Found {len(files)} total files, {len(audio_files)} are audio files.")
        return audio_files
        
    except Exception as e:
        logger.error(f"Error listing files from Google Drive: {e}")
        return []

def download_file(file_id: str, file_name: str) -> Optional[str]:
    """
    Downloads a file from Google Drive to the local temporary directory.
    Returns the absolute path to the downloaded file, or None if download failed.
    """
    try:
        service = get_drive_service()
        
        # Ensure temp directory exists
        os.makedirs(config.TEMP_DOWNLOAD_DIR, exist_ok=True)
        local_path = os.path.abspath(os.path.join(config.TEMP_DOWNLOAD_DIR, file_name))
        
        logger.info(f"Downloading {file_name} ({file_id}) to {local_path}...")
        
        request = service.files().get_media(fileId=file_id)
        
        with io.FileIO(local_path, 'wb') as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    percent = int(status.progress() * 100)
                    # Limit log verbosity, log every 20%
                    if percent % 20 == 0 or percent == 100:
                        logger.info(f"Download progress: {percent}%")
                        
        logger.info(f"Download complete: {local_path}")
        return local_path
        
    except Exception as e:
        logger.error(f"Error downloading file {file_name} ({file_id}): {e}")
        # Clean up partial download if it exists
        if 'local_path' in locals() and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass
        return None
