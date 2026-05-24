import os
import sys
import logging
import tomllib
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('app.log', encoding='utf-8')
    ]
)
logger = logging.getLogger('ArticleGenerator')

# Load environment variables
load_dotenv()

# Load settings from settings.toml if available
SETTINGS_FILE = 'settings.toml'
settings = {}
if os.path.exists(SETTINGS_FILE):
    try:
        with open(SETTINGS_FILE, 'rb') as f:
            settings = tomllib.load(f)
        logger.info(f"Loaded settings from {SETTINGS_FILE}")
    except Exception as e:
        logger.error(f"Failed to load settings file {SETTINGS_FILE}: {e}")

services_config = settings.get('services', {})
wordpress_settings = services_config.get('WORDPRESS', {})
model_settings = services_config.get('MODEL', {})
generation_settings = settings.get('generation', {})

# Google Drive Config
GOOGLE_DRIVE_FOLDER_ID = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
GOOGLE_APPLICATION_CREDENTIALS = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'service_account.json')

# Model / Gemini Config
GEMINI_API_KEY = model_settings.get('llm_api_key') or os.getenv('GEMINI_API_KEY')
GEMINI_MODEL = model_settings.get('llm_model') or os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
LLM_BASE_URL = model_settings.get('llm_base_url') or os.getenv('LLM_BASE_URL', 'https://api.deepseek.com')

# WordPress Config
WORDPRESS_URL = wordpress_settings.get('wp_base_url') or os.getenv('WORDPRESS_URL')
WORDPRESS_USER = wordpress_settings.get('wp_username') or os.getenv('WORDPRESS_USER')
WORDPRESS_APP_PASSWORD = wordpress_settings.get('wp_key') or os.getenv('WORDPRESS_APP_PASSWORD')

# Clean up wordpress url format
if WORDPRESS_URL:
    WORDPRESS_URL = WORDPRESS_URL.rstrip('/')

# Polling/Runtime Config
try:
    POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '300'))
except ValueError:
    POLL_INTERVAL = 300

TEMP_DOWNLOAD_DIR = os.getenv('TEMP_DOWNLOAD_DIR', 'temp_audio')

# Generation Config
HEADER_PATTERN = generation_settings.get('HEADER_PATTERN', r"<h1\b[^>]*>(.*?)</h1>")
PROMPT = generation_settings.get('PROMPT', '')

# Dynamically fetch WordPress categories at startup
CATEGORIES_MAP = {}
try:
    api_url = f"{WORDPRESS_URL}/categories"
    auth = HTTPBasicAuth(WORDPRESS_USER, WORDPRESS_APP_PASSWORD)
    response = requests.get(api_url, params={'per_page': 100}, auth=auth, timeout=10)
    if response.status_code == 200:
        for cat in response.json():
            CATEGORIES_MAP[cat['name']] = cat['id']
        logger.info(f"Dynamically fetched categories from WordPress: {list(CATEGORIES_MAP.keys())}")
    else:
        logger.warning(f"Failed to fetch categories from WordPress (HTTP {response.status_code}): {response.text}")
except Exception as e:
    logger.warning(f"Could not load categories from WordPress: {e}. Using fallback categories.")

CATEGORIES_LIST = tuple(CATEGORIES_MAP.keys())


def validate_config() -> bool:
    """
    Validates that all necessary configuration values are populated.
    Returns True if valid, raises ValueError otherwise.
    """
    missing = []
    
    if not GOOGLE_DRIVE_FOLDER_ID:
        missing.append('GOOGLE_DRIVE_FOLDER_ID')
    if not GEMINI_API_KEY:
        missing.append('GEMINI_API_KEY')
    if not WORDPRESS_URL:
        missing.append('WORDPRESS_URL')
    if not WORDPRESS_USER:
        missing.append('WORDPRESS_USER')
    if not WORDPRESS_APP_PASSWORD:
        missing.append('WORDPRESS_APP_PASSWORD')
        
    if missing:
        logger.error(f"Missing required configuration variables: {', '.join(missing)}")
        logger.error("Please populate them in a .env file or settings.toml.")
        return False

    # Check if Google Credentials file exists
    if not os.path.exists(GOOGLE_APPLICATION_CREDENTIALS):
        logger.warning(
            f"Google credentials file not found at: {os.path.abspath(GOOGLE_APPLICATION_CREDENTIALS)}. "
            f"Please place your Google Service Account JSON file there."
        )
        return False
        
    return True

