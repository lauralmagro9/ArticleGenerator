import requests
import os
import re
import io
from requests.auth import HTTPBasicAuth
from typing import Dict, List, Tuple
from datetime import datetime

from config import logger


class WordPress:
    def __init__(self, url, user, password):
        self.url = url
        self.auth = HTTPBasicAuth(user, password)
        
    def get_published_posts(self, max_posts: int = 100) -> List[Dict[str, str]]:
        """
        Retrieves titles and URLs of existing published posts from WordPress.
        Pages through the REST API in batches of 100 until all posts are fetched
        or max_posts is reached.

        Returns a list of dicts: [{"title": "...", "url": "..."}, ...]
        """
        posts = []
        page = 1
        per_page = min(max_posts, 100)
        posts_url = f"{self.url}posts"

        while len(posts) < max_posts:
            try:
                response = requests.get(
                    posts_url,
                    params={
                        "status": "publish",
                        "per_page": per_page,
                        "page": page,
                        "fields": "id,link,title",
                        "_fields": "id,link,title",
                    },
                    auth=self.auth,
                    timeout=15,
                )

                if response.status_code == 400:
                    # Likely went past the last page
                    break
                response.raise_for_status()

                batch = response.json()
                if not batch:
                    break

                for post in batch:
                    title = post.get("title", {})
                    rendered_title = title.get("rendered", "") if isinstance(title, dict) else str(title)
                    url = post.get("link", "")
                    if rendered_title and url:
                        posts.append({"title": rendered_title, "url": url})

                # If we got fewer results than per_page, we're on the last page
                if len(batch) < per_page:
                    break

                page += 1

            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to fetch published posts from WordPress: {e}")
                break

        logger.info(f"Fetched {len(posts)} published posts from WordPress.")
        return posts[:max_posts]

    def post_draft_to_wordpress(
        self,
        title: str,
        content: str,
        date: datetime,
        metadescription: str = None,
        category_id: int = None,
        image_id: int = None
    ) -> Tuple[int, str]:
        """
        Posts the article to WordPress as a draft.
        Returns a tuple containing:
        - The WordPress Post ID (int)
        - The WordPress Post direct link URL (str)
        Raises requests.exceptions.RequestException on failure.
        """
        # Build API url
        posts_url = f"{self.url}posts"
        logger.info(f"Posting draft article to WordPress REST API at: {posts_url}")
        
        # Payload for draft creation
        payload = {
            'title': title,
            'content': content,
            'date': date.strftime("%Y-%m-%dT%H:%M:%S"),
            'status': "pending"
        }

        if image_id:
            payload['featured_media'] = image_id

        if category_id:
            payload['categories'] = [category_id]
            
        if metadescription:
            payload['meta'] = {'_yoast_wpseo_metadesc': metadescription}
        
        try:
            response = requests.post(posts_url, json=payload, auth=self.auth)
            
            # If authentication failed (401), explain what might be wrong
            if response.status_code == 401:
                logger.error("WordPress authentication failed (401 Unauthorized). "
                            "Please verify your WordPress username and Application Password in .env.")
            
            response.raise_for_status()
            
            post_data = response.json()
            post_id = post_data.get('id')
            post_link = post_data.get('link')
            
            logger.info(f"WordPress draft created successfully! Post ID: {post_id}, URL: {post_link}")
            return post_id, post_link
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to post draft to WordPress: {e}")
            if 'response' in locals() and response is not None:
                logger.error(f"Response status: {response.status_code}, content: {response.text}")
            raise e

    def get_posts_categories(self)-> dict[str, str]:
        """
        Fetch existing categories from wordpress
        Returns a dictionary containing:
        - The category name (str)
        - The category id (str)
        Raises requests.exceptions.RequestException on failure.
        """
        categories_map = {}
        try:
            cat_url = f"{self.url}categories"
            response = requests.get(cat_url, params={'per_page': 100}, auth=self.auth, timeout=10)
            
            # Best practice: This automatically raises a RequestException for 4xx or 5xx errors
            response.raise_for_status() 
            
            # If we reach here, it means status_code was 200-299
            for cat in response.json():
                categories_map[cat['name']] = cat['id']
                
            logger.info(f"Dynamically fetched categories from WordPress: {list(categories_map.keys())}")
            return categories_map

        except requests.exceptions.RequestException as e:
            # Catch any network/HTTP error, log it, and raise it up the chain
            logger.error(f"WordPress API connection failed: {e}")
            raise

    def upload_image(self, image_file: io.BytesIO, image_description: str=None, image_filename: str=None) -> int:
        """
        Upload image file to WordPress media library.
        Checks if image with same filename already exists and returns existing ID if found.
        
        Args:
            image_file: File-like object (from Flask request.files)
            image_description: Alt text/description for the image
            image_filename: Optional filename (uses image_file.filename if not provided)
        
        Returns:
            int: Image ID on success, None on error
        """
        # Load configuration
        media_url = f"{self.url}media"
        
        if image_filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            image_filename = image_file.filename if hasattr(image_file, 'filename') else f'image_{timestamp}.jpg'
        
        # Normalize filename: lowercase and replace spaces/underscores with hyphens
        name, ext = os.path.splitext(image_filename)
        # Replace spaces and underscores with hyphens, convert to lowercase
        name = re.sub(r'[\s_]+', '-', name.lower())
        # Remove any characters that aren't alphanumeric, hyphens, or dots
        name = re.sub(r'[^a-z0-9\-.]', '', name)
        image_filename_formatted = f"{name}{ext.lower()}"
        
        # Check if image with same filename already exists
        try:
            search_response = requests.get(
                media_url,
                params={'search': image_filename},
                auth=self.auth
            )
            
            if search_response.status_code == 200:
                existing_media = search_response.json()
                # Check if any media item has the exact same filename
                for media in existing_media:
                    source_url = media['source_url'].lower()
                    if image_filename_formatted in source_url:
                        existing_id = media['id']
                        logger.info(f"Found existing image: {image_filename} (ID: {existing_id}). Reusing instead of uploading.")
                        return existing_id
        except Exception as e:
            logger.warning(f"Image {str(e)} does not exist in WordPress. Proceeding with upload...")
        
        # Image doesn't exist, proceed with upload
        # Determine MIME type from filename
        mime_type = 'image/jpeg'  # default
        if image_filename.lower().endswith('.png'):
            mime_type = 'image/png'
        elif image_filename.lower().endswith('.gif'):
            mime_type = 'image/gif'
        elif image_filename.lower().endswith('.webp'):
            mime_type = 'image/webp'
        
        try:
            # Reset file pointer to beginning
            image_file.seek(0)
            
            files = {
                'file': (image_filename, image_file, mime_type)
            }
            data = {
                'title': image_filename,
            }
            if image_description:
                data['alt_text'] = image_description

            response = requests.post(
                media_url,
                files=files,
                data=data,
                auth=self.auth
            )
            
            if response.status_code == 201:
                response_json = response.json()
                image_id = response_json['id']
                logger.info(f"Image {image_filename} successfully uploaded to WordPress (ID: {image_id})")
                return image_id
            else:
                error_msg = f"Failed to upload image: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return None
                
        except Exception as e:
            error_msg = f"Error uploading image: {str(e)}"
            logger.error(error_msg)
            return None

        

