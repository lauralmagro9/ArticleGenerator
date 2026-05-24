
import time
import json
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from typing import Literal

import config
from config import logger

# Define the Pydantic schema for structured Gemini response
class ArticleSchema(BaseModel):
    title: str = Field(description="A catchy, engaging, and SEO-friendly title for the blog article.")
    content: str = Field(description="The body content of the article, structured in clean HTML (using tags like p, h2, h3, ul, ol, strong, em). DO NOT include html/head/body outer wrappers. DO NOT wrap the output in markdown block code fences (like ```html or ```).")
    metadescription: str = Field(description="A brief summary of the content. You must keep it between 120 and 150 characters and include the target keyword naturally.")
    category: Literal[config.CATEGORIES_LIST]

def generate_article_from_audio(
    local_path: str,
    related_articles: List[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Uploads the local audio file to the Gemini File API, waits for it to process,
    and calls Gemini to generate a structured blog article.
    Deletes the uploaded file from Gemini storage before returning.

    Args:
        local_path: Path to the local audio file to process.
        related_articles: Optional list of existing published posts as
            [{"title": "...", "url": "..."}, ...].  These are injected into
            the prompt so the model can include 1-2 relevant internal links.

    Returns a dictionary containing 'title', 'content', 'metadescription',
    and 'category'.
    """
    # Initialize the GenAI Client
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    uploaded_file = None
    
    try:
        logger.info(f"Uploading file to Gemini File API: {local_path}")
        # Upload file to Gemini File API
        uploaded_file = client.files.upload(file=local_path)
        logger.info(f"Uploaded file name: {uploaded_file.name}")
        
        # Wait for file to process (essential for audio/video processing)
        logger.info("Waiting for Gemini to process the audio file...")
        while True:
            file_info = client.files.get(name=uploaded_file.name)
            state = file_info.state.name if hasattr(file_info.state, 'name') else str(file_info.state)
            
            logger.info(f"Gemini processing state: {state}")
            if state == 'ACTIVE':
                break
            elif state == 'FAILED':
                raise Exception("Gemini File API processing failed")
                
            time.sleep(3)
            
        logger.info("Audio file is active. Requesting article generation...")
        
        # Build the internal-links block for the prompt
        if related_articles:
            links_lines = [
                f'- <a href="{p["url"]}">{p["title"]}</a>'
                for p in related_articles
            ]
            links_block = "\n".join(links_lines)
        else:
            links_block = "(No hay publicaciones anteriores disponibles.)"

        # Define instruction prompt, injecting the related-articles list at {2}
        # Placeholders in the template:
        #   {0} = main topic (left empty; Gemini infers it from the audio)
        #   {1} = output format description (left empty; handled by schema)
        #   {2} = internal links list
        #   {3} = transcription text (left empty; Gemini reads the audio directly)
        prompt = config.PROMPT.format("", "", links_block, "")
        
        # Generate content with structured JSON output matching schema
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=[uploaded_file, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ArticleSchema,
                temperature=0.7,
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
        # Always clean up the uploaded file from Gemini storage
        if uploaded_file:
            try:
                logger.info(f"Cleaning up file from Gemini storage: {uploaded_file.name}")
                client.files.delete(name=uploaded_file.name)
                logger.info("Gemini file cleanup completed.")
            except Exception as cleanup_err:
                logger.warning(f"Failed to delete Gemini file {uploaded_file.name}: {cleanup_err}")
