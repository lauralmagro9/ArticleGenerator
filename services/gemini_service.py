
import time
import json
import re
from typing import Dict, Any, List, Literal
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from pathlib import Path
from services.wordpress_service import WordPress

import config
from config import logger

# Define the Pydantic schema for structured Gemini response
wp = WordPress(config.WORDPRESS_URL, config.WORDPRESS_USER, config.WORDPRESS_PASSWORD)
categories_map = wp.get_posts_categories()
class ArticleSchema(BaseModel):
    title: str = Field(description="A catchy, engaging, and SEO-friendly title for the blog article.")
    content: str = Field(description="The body content of the article, structured in clean HTML (using tags like p, h2, h3, ul, ol, strong, em). DO NOT include html/head/body outer wrappers. DO NOT wrap the output in markdown block code fences (like ```html or ```).")
    metadescription: str = Field(description="A brief summary of the content. You must keep it between 120 and 150 characters and include the target keyword naturally.")
    category: str = Field(description=f"The category of the article. It must be one of the following: {categories_map.keys()}")

def generate_article_from_audio(
    local_paths: list,
    related_articles: List[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Uploads one or more local audio files to the Gemini File API, waits for
    them to process, and calls Gemini to generate a single structured blog
    article from the combined audio content.
    Deletes the uploaded files from Gemini storage before returning.

    Args:
        local_paths: List of paths to local audio files to process.
            Files should be ordered in the sequence they should be
            interpreted (e.g., part 1 first, part 2 second).
        related_articles: Optional list of existing published posts as
            [{"title": "...", "url": "..."}, ...].  These are injected into
            the prompt so the model can include 1-2 relevant internal links.

    Returns a dictionary containing 'title', 'content', 'metadescription',
    and 'category'.
    """
    # Initialize the GenAI Client
    client = genai.Client(api_key=config.MODEL_API_KEY)
    uploaded_files = []
    
    try:
        # Upload all audio files to Gemini File API
        for local_path in local_paths:
            logger.info(f"Uploading file to Gemini File API: {local_path}")
            uploaded_file = client.files.upload(file=local_path)
            uploaded_files.append(uploaded_file)
            logger.info(f"Uploaded file name: {uploaded_file.name}")
        
        # Wait for all files to process (essential for audio/video processing)
        logger.info(f"Waiting for Gemini to process {len(uploaded_files)} audio file(s)...")
        for uploaded_file in uploaded_files:
            while True:
                file_info = client.files.get(name=uploaded_file.name)
                state = file_info.state.name if hasattr(file_info.state, 'name') else str(file_info.state)
                
                logger.info(f"Gemini processing state for '{uploaded_file.name}': {state}")
                if state == 'ACTIVE':
                    break
                elif state == 'FAILED':
                    raise Exception(f"Gemini File API processing failed for '{uploaded_file.name}'")
                    
                time.sleep(3)
            
        logger.info(f"All {len(uploaded_files)} audio file(s) are active. Requesting article generation...")
        
        # Build the internal-links block for the prompt
        if related_articles:
            links_lines = [
                f'- <a href="{p["url"]}">{p["title"]}</a>'
                for p in related_articles
            ]
            links_block = "\n".join(links_lines)
        else:
            links_block = "(No hay publicaciones anteriores disponibles.)"

        # Define instruction prompt, injecting the related-articles list
        goal = config.PROMPT_GOAL.format(links_block)
        instructions = config.PROMPT_INSTRUCTIONS
        format = config.PROMPT_FORMAT
        
        # Build contents list: all uploaded audio files followed by the prompt
        contents = list(uploaded_files) + [goal]

        # Generate content with structured JSON output matching schema
        response = client.models.generate_content(
            model=config.MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ArticleSchema,
                temperature=1,
                system_instruction=[instructions, format]
            )
        )
        
        # Parse the structured JSON response
        try:
            article_data = json.loads(response.text)
            logger.info(f"Successfully generated article: '{article_data.get('title')}'")
            return {
                'title': article_data.get('title', 'Untitled Article'),
                'content': article_data.get('content', ''),
                'metadescription': article_data.get('metadescription', ''),
                'category': article_data.get('category', ''),
            }
        except json.JSONDecodeError as je:
            logger.error(f"Failed to parse Gemini structured JSON response: {response.text}")
            raise je
            
    except Exception as e:
        logger.error(f"Error during Gemini processing/generation: {e}")
        raise e
        
    finally:
        # Always clean up all uploaded files from Gemini storage
        for uploaded_file in uploaded_files:
            try:
                logger.info(f"Cleaning up file from Gemini storage: {uploaded_file.name}")
                client.files.delete(name=uploaded_file.name)
                logger.info("Gemini file cleanup completed.")
            except Exception as cleanup_err:
                logger.warning(f"Failed to delete Gemini file {uploaded_file.name}: {cleanup_err}")

