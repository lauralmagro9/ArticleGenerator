import os
import logging

# Local imports
from ArticleGenerator.services.model_services import LLMGenerator, TR_CLASS, load_models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def save_result(result, output_filename):
    cwd = os.getcwd()
    results_folder = os.path.join(cwd, "tests", "data", "results")
    output_path = os.path.join(results_folder, output_filename)
    with open(output_path, "w", encoding="utf-8") as file:
        file.write(result)

class TestTranscriptionModel:
    def test_transcribe_audio_file(self, app, audio_file):
        logger.info("Testing transcription model")
        base_name, ext = audio_file.filename.split(".")
        
        # Lazy load model
        load_models()
        transcription = TR_CLASS.transcribe_audio_file(audio_file)

        assert transcription is not None
        logger.info(f"Transcription: {transcription}")

        output_filename = f"{base_name}_transcription.txt"
        save_result(transcription, output_filename)
        

class TestLLMGenerator:
    def test_llm_generate_article(self, app, transcription_file):
        logger.info("Testing LLM generator")
        transcription, file_name = transcription_file

        LLM_CLASS = LLMGenerator()

        prompt = f"Transform this text to to json fomrat with the key 'text': {transcription}"
        article_json = LLM_CLASS.llm_generate_article(prompt)

        assert article_json is not None
        logger.info(f"LLM generation: {article_json}")

        save_result(article_json, file_name)
        
        

