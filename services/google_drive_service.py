import os
import io
import mimetypes
from typing import List, Dict, Any, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
from google.auth.exceptions import RefreshError

import config
import utils
from config import logger


class GoogleDrive:
    def __init__(self, client_secret_file, scopes):
        """Initializes the Google Drive and Docs API clients using OAuth2 User Credentials."""
        self.creds = None
        
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first time.
        if os.path.exists('token.json'):
            self.creds = Credentials.from_authorized_user_file('token.json', scopes)
            
        # If there are no (valid) credentials available, let the user log in.
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except RefreshError:
                    # Refresh token is invalid/expired; trigger full flow again
                    flow = InstalledAppFlow.from_client_secrets_file(
                        client_secret_file, scopes
                    )
                    self.creds = flow.run_local_server(port=0)
            else:
                # client_secret_file is the path to the JSON you downloaded from Google Cloud
                flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, scopes)
                self.creds = flow.run_local_server(port=0)
                
            # Save the credentials for the next run so you don't have to log in every time
            with open('token.json', 'w') as token:
                token.write(self.creds.to_json())

        # Build the services using the user credentials
        self.drive_service = build('drive', 'v3', credentials=self.creds)
        self.docs_service = build('docs', 'v1', credentials=self.creds)

    def list_audio_files(self) -> List[Dict[str, Any]]:
        """
        Lists all non-trashed audio files in the monitored Google Drive folder.
        Returns a list of dictionaries with 'id', 'name', and 'mimeType'.
        """
        try:
            query = f"'{config.GOOGLE_AUDIOS_FOLDER_ID}' in parents and trashed = false"
            
            logger.info(f"Scanning Google Drive folder '{config.GOOGLE_AUDIOS_FOLDER_ID}'...")
            
            results = self.drive_service.files().list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType, createdTime)",
                pageSize=100
            ).execute()
            
            files = results.get('files', [])
            logger.info(f'files: {[f for f in files]}')
            audio_files = [f for f in files if utils.is_audio_file(f)]
            
            logger.info(f"Found {len(files)} total files, {len(audio_files)} are audio files.")
            return audio_files
            
        except Exception as e:
            logger.error(f"Error listing files from Google Drive: {e}")
            return []

    def get_image_file(self, root_name: str) -> tuple[Optional[str], Optional[io.BytesIO]]:
        """
        Finds the first image file in the images folder whose filename
        contains `root_name`.

        Searches GOOGLE_IMAGES_FOLDER_ID for image files matching the root_name
        and downloads the first one found.

        Returns:
            A tuple (filename, image_bytes) where image_bytes is a BytesIO object
            containing the raw image data. Returns (None, None) if no image is found.
        """
        try:
            query = (
                f"'{config.GOOGLE_IMAGES_FOLDER_ID}' in parents "
                f"and mimeType contains 'image/' "
                f"and name contains '{root_name}' "
                f"and trashed = false"
            )
            logger.info(f"Searching for image matching '{root_name}' "
                        f"in '{config.GOOGLE_IMAGES_FOLDER_ID}'...")

            results = self.drive_service.files().list(
                q=query,
                fields="files(id, name, mimeType)",
                pageSize=10
            ).execute()

            image_files = results.get('files', [])
            if not image_files:
                logger.info(f"No image found matching '{root_name}'.")
                return None, None

            first_image = image_files[0]
            logger.info(f"Found image: '{first_image['name']}' (ID: {first_image['id']}, "
                        f"MIME: {first_image['mimeType']})")

            # Download the image content into memory
            request = self.drive_service.files().get_media(fileId=first_image['id'])
            image_bytes = io.BytesIO()
            downloader = MediaIoBaseDownload(image_bytes, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()

            image_bytes.seek(0)
            logger.info(f"Successfully downloaded image '{first_image['name']}' "
                        f"({image_bytes.getbuffer().nbytes} bytes).")
            return first_image['name'], image_bytes

        except Exception as e:
            logger.error(f"Error getting image file for '{root_name}': {e}")
            return None, None

    def download_file(self, file_id: str, file_name: str) -> Optional[str]:
        """
        Downloads a file from Google Drive to the local temporary directory.
        Returns the absolute path to the downloaded file, or None if download failed.
        """
        try:
            # Ensure temp directory exists
            os.makedirs(config.TEMP_DOWNLOAD_DIR, exist_ok=True)
            local_path = os.path.abspath(os.path.join(config.TEMP_DOWNLOAD_DIR, file_name))
            
            logger.info(f"Downloading {file_name} ({file_id}) to {local_path}...")
            
            request = self.drive_service.files().get_media(fileId=file_id)
            
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
    
    def create_google_document(self, title: str, text: str):
        "Creates a google document with the generated article"
        try:
            # 1. Create blank document
            articles_folder_id = config.GOOGLE_ARTICLES_FOLDER_ID

            metadata = {
                'name': title,
                'mimeType': 'application/vnd.google-apps.document',
                'parents': [articles_folder_id]
            }

            new_doc = self.drive_service.files().create(
                body=metadata,
                fields='id'
            ).execute()

            doc_id = new_doc.get('id')
            logger.info(f'Created document "{title}"')

            # 2. Add structured content
            payload = [
                {
                    'insertText': {
                        'location': {
                            'index': 1  # Beginning of document
                        },
                        'text': text
                    }
                }
            ]

            self.docs_service.documents().batchUpdate(
                documentId=doc_id, 
                body={'requests': payload}
            ).execute()
            
            logger.info('Added article in document "{title}".')
            logger.info(f"You can see it here: https://docs.google.com/document/d/{doc_id}/edit")

        except HttpError as error:
            logger.error(f"Google Document API failed with error: {error}")
