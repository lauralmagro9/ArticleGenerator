import os
import sys
import time
import argparse
from typing import List

import config
from config import logger
import db
import services.google_drive_service as google_drive_service
import services.gemini_service as gemini_service
import services.wordpress_service as wordpress_service

def clean_local_file(local_path: str) -> None:
    """Safely deletes a local file if it exists."""
    if local_path and os.path.exists(local_path):
        try:
            logger.info(f"Cleaning up local file: {local_path}")
            os.remove(local_path)
            logger.info("Local file cleanup completed.")
        except Exception as e:
            logger.warning(f"Failed to delete local file {local_path}: {e}")

def process_file(file_info: dict, related_articles: list = None) -> None:
    """Processes a single audio file from Google Drive."""
    file_id = file_info['id']
    file_name = file_info['name']
    local_path = None
    
    logger.info(f"--- Starting processing for file: '{file_name}' ({file_id}) ---")
    
    # 1. Mark as processing in DB
    db.mark_processing(file_id, file_name)
    
    # 2. Download the file
    local_path = google_drive_service.download_file(file_id, file_name)
    if not local_path:
        db.mark_failed(file_id, "Failed to download file from Google Drive.")
        return
        
    try:
        # 3. Call Gemini to generate the article
        logger.info(f"Invoking Gemini to create article from {file_name}...")
        article_data = gemini_service.generate_article_from_audio(
            local_path,
            related_articles=related_articles,
        )
        
        title = article_data.get('title')
        content = article_data.get('content')
        metadescription = article_data.get('metadescription')
        category = article_data.get('category')
        
        if not title or not content:
            raise ValueError("Gemini returned empty title or content.")
            
        # Map category name to ID from config.CATEGORIES_MAP
        category_id = None
        if category:
            category_id = config.CATEGORIES_MAP.get(category)
            if not category_id:
                # Try case-insensitive lookup
                for name, cid in config.CATEGORIES_MAP.items():
                    if name.lower() == category.lower():
                        category_id = cid
                        break
            if category_id:
                logger.info(f"Mapped category '{category}' to WordPress ID: {category_id}")
            else:
                logger.warning(f"Could not map category '{category}' to a WordPress ID. Posting without category.")

        # 4. Post draft to WordPress
        logger.info("Uploading draft to WordPress...")
        wp_post_id, wp_post_link = wordpress_service.post_draft_to_wordpress(
            title=title,
            content=content,
            metadescription=metadescription,
            category_id=category_id
        )
        
        # 5. Mark as completed
        db.mark_completed(file_id, wp_post_id, wp_post_link)
        logger.info(f"Successfully processed file: '{file_name}'")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error processing file '{file_name}': {error_msg}")
        db.mark_failed(file_id, error_msg)
        
    finally:
        # 6. Always clean up downloaded audio file
        clean_local_file(local_path)
        logger.info(f"--- Finished processing for file: '{file_name}' ---\n")

def check_and_process() -> None:
    """Scans Google Drive for new files and processes them."""
    logger.info("Starting check for new audio files...")
    
    # List audio files from Google Drive
    audio_files = google_drive_service.list_audio_files()
    if not audio_files:
        logger.info("No audio files found in Google Drive folder.")
        return
        
    # Filter files that haven't been completed yet
    new_files = [f for f in audio_files if not db.is_processed(f['id'])]
    logger.info(f"Found {len(new_files)} new (unprocessed) files.")
    
    if not new_files:
        return

    # Fetch existing published posts once for the whole batch so the model
    # can reference 1-2 relevant internal links in each generated article.
    logger.info("Fetching existing published posts for internal linking...")
    related_articles = wordpress_service.get_published_posts(max_posts=100)
    
    for file_info in new_files:
        process_file(file_info, related_articles=related_articles)

def main() -> None:
    # Setup CLI arguments
    parser = argparse.ArgumentParser(
        description="Audio-to-Article WordPress Draft Generator. Monitors Google Drive, transcribes with Gemini, posts to WordPress."
    )
    parser.add_argument(
        '--run-once',
        action='store_true',
        help="Run the file scanner once and exit immediately rather than polling."
    )
    args = parser.parse_args()
    
    logger.info("Initializing Audio-to-Article Generator...")
    
    # Validate configurations
    if not config.validate_config():
        logger.error("Configuration validation failed. Exiting.")
        sys.exit(1)
        
    logger.info("Configuration is valid.")
    
    if args.run_once:
        logger.info("Running in RUN-ONCE mode.")
        check_and_process()
        logger.info("Finished running. Exiting.")
    else:
        logger.info(f"Running in DAEMON mode (polling every {config.POLL_INTERVAL} seconds).")
        try:
            while True:
                check_and_process()
                logger.info(f"Sleeping for {config.POLL_INTERVAL} seconds before next scan...")
                time.sleep(config.POLL_INTERVAL)
        except KeyboardInterrupt:
            logger.info("Daemon execution interrupted by user. Exiting.")
            sys.exit(0)

if __name__ == '__main__':
    main()
