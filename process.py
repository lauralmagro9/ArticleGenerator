from collections import defaultdict
import config
import time
from config import logger
import db

from services.google_drive_service import GoogleDrive
import services.gemini_service as gemini_service
from services.wordpress_service import WordPress
from utils import get_root_name, clean_local_file, get_category_id, get_date_from_filename

# Initialize classes
wp = WordPress(config.WORDPRESS_URL, config.WORDPRESS_USER, config.WORDPRESS_PASSWORD)
gd = GoogleDrive(client_secret_file=config.GOOGLE_CLIENT_SECRET, scopes=config.GOOGLE_DRIVE_SCOPES)

# Fetch existing published posts once for the whole batch so the model
# can reference 1-2 relevant internal links in each generated article.
logger.info("Fetching existing published posts for internal linking...")
related_articles = wp.get_published_posts(max_posts=100)
# Get wp categories
categories_map = wp.get_posts_categories()

def process_file_group(root_name: str, file_group: list) -> None:
    """Processes a group of related audio files from Google Drive into a single article.
    
    All files in the group share the same root name and are sorted by their
    numeric suffix.  They are downloaded, uploaded together to Gemini, and
    a single article is generated from their combined content.
    All individual file IDs are marked as completed or failed together.
    """
    file_ids = [f['id'] for f in file_group]
    file_names = [f['name'] for f in file_group]
    local_paths = []

    logger.info(f"--- Starting processing for group '{root_name}' ({len(file_group)} file(s): {file_names}) ---")

    try:
        # 1. Mark all files as processing in DB
        for f in file_group:
            db.mark_processing(f['id'], f['name'])

        # 2. Download all files in the group
        for f in file_group:
            local_path = gd.download_file(f['id'], f['name'])
            if not local_path:
                error_msg = f"Failed to download file '{f['name']}' from Google Drive."
                for fid in file_ids:
                    db.mark_failed(fid, error_msg)
                return
            local_paths.append(local_path)

        # 4. Generate Article from all audio files in the group
        try:
            logger.info(f"Invoking Gemini to create article from group '{root_name}' ({len(local_paths)} audio(s))...")
            article_data = gemini_service.generate_article_from_audio(
                local_paths,
                related_articles=related_articles,
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error generating article from group '{root_name}': {error_msg}")
            for fid in file_ids:
                db.mark_failed(fid, error_msg)
            return

        title = article_data.get('title')
        content = article_data.get('content')
        metadescription = article_data.get('metadescription')
        category = article_data.get('category')
        date = file_group[0]["date"]

        if not title or not content:
            raise ValueError("Gemini returned empty title or content.")

        # 5. Map category name to ID from config.CATEGORIES_MAP
        category_id = get_category_id(category, categories_map)

        # 6. Retrieve image associated to the audio and upload it to wordpress
        image_filename, image_file = gd.get_image_file(root_name)
        if image_filename and image_file:
            image_id = wp.upload_image(image_file=image_file, image_filename=image_filename)
        else:
            image_id = None

        # 7. Post draft to WordPress
        logger.info("Uploading draft to WordPress...")
        try:
            wp_post_id, wp_post_link = wp.post_draft_to_wordpress(
                title=title,
                content=content,
                date=date,
                metadescription=metadescription,
                category_id=category_id,
                image_id=image_id
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error uploading article to wordpress from group '{root_name}': {error_msg}")
            for fid in file_ids:
                db.mark_failed(fid, error_msg)
            return

        # 8. Create google doc with post
        logger.info(f"Creating google doc with draft for group '{root_name}'...")
        try:
            gd.create_google_document(title=title, text=content)
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error creating google doc for group '{root_name}': {error_msg}")
            for fid in file_ids:
                db.mark_failed(fid, error_msg)
            return

        # 8. Mark all files in the group as completed
        for fid in file_ids:
            db.mark_completed(fid, wp_post_id, wp_post_link)
        logger.info(f"Successfully processed group '{root_name}' ({len(file_group)} file(s))")

    finally:
        # Always clean up all downloaded audio files
        for lp in local_paths:
            clean_local_file(lp)
        logger.info(f"--- Finished processing for group '{root_name}' ---\n")


def check_and_process() -> None:
    """Scans Google Drive for new files, groups them by root name, and processes each group."""
    logger.info("Starting check for new audio files...")
    
    # List audio files from Google Drive
    audio_files = gd.list_audio_files()
    if not audio_files:
        logger.info("No audio files found in Google Drive folder.")
        return
        
    # Filter files that haven't been completed yet
    new_files = [f for f in audio_files if not db.is_processed(f['id'])]
    logger.info(f"Found {len(new_files)} new (unprocessed) files.")
    
    if not new_files:
        return

    # Group files by root name (everything before the last underscore)
    groups = defaultdict(list)
    for f in new_files:
        filename = f['name']
        root, order = get_root_name(filename)
        f["date"] = get_date_from_filename(filename=filename)
        f["order"] = order
        groups[root].append(f)

    # Sort groups by date
    sorted_groups = dict(
    sorted(
        groups.items(),
        key=lambda item: min(f['date'] for f in item[1])
    )
    )
    # Sort files within each group by order
    for root in sorted_groups:
        sorted_groups[root].sort(key=lambda f: f['order'])

    logger.info(f"Grouped {len(new_files)} files into {len(groups)} group(s): "
                f"{{{', '.join(f'{r}: {len(fs)} file(s)' for r, fs in groups.items())}}}")

    total_groups = len(sorted_groups)
    for i, (root_name, file_group) in enumerate(sorted_groups.items()):
        process_file_group(root_name, file_group)

        # Wait 60 seconds between groups to avoid reaching quota limits, but skip waiting after the final group
        if i < total_groups - 1:
            logger.info("Waiting 60 seconds before processing the next group...")
            time.sleep(60)