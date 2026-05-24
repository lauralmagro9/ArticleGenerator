import requests
from requests.auth import HTTPBasicAuth
from typing import Dict, Any, List, Tuple
from datetime import datetime

import config
from config import logger


def get_published_posts(max_posts: int = 100) -> List[Dict[str, str]]:
    """
    Retrieves titles and URLs of existing published posts from WordPress.
    Pages through the REST API in batches of 100 until all posts are fetched
    or max_posts is reached.

    Returns a list of dicts: [{"title": "...", "url": "..."}, ...]
    """
    api_url = f"{config.WORDPRESS_URL}/wp-json/wp/v2/posts"
    auth = HTTPBasicAuth(config.WORDPRESS_USER, config.WORDPRESS_APP_PASSWORD)

    posts = []
    page = 1
    per_page = min(max_posts, 100)

    while len(posts) < max_posts:
        try:
            response = requests.get(
                api_url,
                params={
                    "status": "publish",
                    "per_page": per_page,
                    "page": page,
                    "fields": "id,link,title",
                    "_fields": "id,link,title",
                },
                auth=auth,
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
    title: str,
    content: str,
    metadescription: str = None,
    category_id: int = None
) -> Tuple[int, str]:
    """
    Posts the article to WordPress as a draft.
    Returns a tuple containing:
      - The WordPress Post ID (int)
      - The WordPress Post direct link URL (str)
    Raises requests.exceptions.RequestException on failure.
    """
    # Build API url
    api_url = f"{config.WORDPRESS_URL}/wp-json/wp/v2/posts"
    
    logger.info(f"Posting draft article to WordPress REST API at: {api_url}")
    
    # Set up basic auth using username and application password
    auth = HTTPBasicAuth(config.WORDPRESS_USER, config.WORDPRESS_APP_PASSWORD)
    
    # Payload for draft creation
    payload = {
        'title': title,
        'content': content,
        'status': "pending",
        'date': datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    }
    
    if category_id:
        payload['categories'] = [category_id]
        
    if metadescription:
        payload['meta'] = {'_yoast_wpseo_metadesc': metadescription}
    
    try:
        response = requests.post(api_url, json=payload, auth=auth, timeout=30)
        
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

