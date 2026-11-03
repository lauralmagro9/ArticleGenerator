import os
import sys
import logging
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

# Google Drive Config
GOOGLE_AUDIOS_FOLDER_ID = "1DWE4vryg1S119Si1Q8pL0-ngYpdUCPqb"
GOOGLE_ARTICLES_FOLDER_ID = "1NJY_CAYDreX41R8Oi8AuiU4KCLoA3sg0"
GOOGLE_IMAGES_FOLDER_ID = "10ivPTnFN6yiWMVRtO461NP8aUSMGCbEA"
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
GOOGLE_DRIVE_SCOPES = [
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/drive'
]

# Model / Gemini Config
MODEL_API_KEY = os.getenv('MODEL_API_KEY')
MODEL = 'gemini-3.8-flash'

# WordPress Config
WORDPRESS_URL = "https://elseteromanolo.com/wp-json/wp/v2/"
WORDPRESS_USER = os.getenv('WORDPRESS_USER')
WORDPRESS_PASSWORD = os.getenv('WORDPRESS_PASSWORD')

POLL_INTERVAL = 300
TEMP_DOWNLOAD_DIR = 'temp_audio'
DB_FILE = "processed_files.json"
# List of common audio file extensions to match if MIME type is generic
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.flac', '.ogg', '.aac', '.wma', '.mp4', '.m4b', '.opus', '.webm'}

# Generation Config
PROMPT_GOAL = ''' Tu trabajo es transformar la voz humana de Manolo El Setero en un artículo que:
siga sonando humano
conserve la personalidad de Manolo
mantenga expresiones naturales
tenga estructura suficiente para ser cómodo de leer
NO suene generado por IA.
Además, debes integrar de forma natural 1 o 2 enlaces a publicaciones anteriores con textos de anclaje orgánicos,
sacados de la lista de artículos ya publicados: {}
'''

PROMPT_INSTRUCTIONS = '''
1. Está permitido reorganizar ligeramente las ideas
y condensar repeticiones para mejorar el ritmo, siempre que no se añada contenido nuevo y
se mantenga la intención original.
2. Prohibido presentarse o anunciar el tema: El texto NO puede empezar con saludos ni frases como 
"Hoy os hablo de", "Hablemos de", "Vamos a ver". El artículo debe empezar DIRECTAMENTE entrando 
en materia (ej. "La chantarela (Cantharellus pallens) es una seta que...").
3. Prohibido anunciar transiciones: Queda totalmente prohibido usar frases como "Hoy me centraré en", 
"Pasamos a hablar de", "A continuación veremos". Las transiciones entre párrafos deben ser totalmente 
fluidas y naturales.
4. Está prohibido usar la expresión "es decir" para explicar términos técnicos.
En su lugar, integra la explicación entre paréntesis o comas, exclusivamente. NO USES LOS GUIONES.
7. Está prohibido ensalzar de manera forzada los adjetivos. No uses adverbios como "verdaderamente", "sumamente" o similares y la terminación "-ísimo".
8. No te refieras a las setas como si fueran personas. No uese expresiones como "le gusta", "le encanta", o similares.
9. Los nombres científicos en latín deben estar en cursiva.
6. Fidelidad Absoluta: Cíñete al 100% a los datos, temperaturas, ubicaciones y vivencias del audio. NO inventes nada.
Mantén:
expresiones coloquiales
pequeñas repeticiones naturales
frases incompletas si suenan humanas
cambios de tema suaves
comentarios personales
emociones espontáneas
observaciones aparentemente “innecesarias”

NO conviertas el texto en:

una redacción académica
una guía profesional
una revista outdoor
contenido SEO artificial
'''
PROMPT_FORMAT = '''
1. Escribe el artículo final directamente en HTML con etiquetas sencillas (<p>, <strong>, <em>, <ul>).
NO uses bloques de código de programación (```html) para mostrar el texto; vuelca el HTML directamente en la respuesta.
2. Título y Encabezados (H3): Frases cortas, directas y naturales. NO uses la estructura "Concepto: Adjetivo".
'''

