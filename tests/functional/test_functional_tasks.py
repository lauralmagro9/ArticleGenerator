import io
from unittest.mock import patch, MagicMock

from ArticleGenerator.tasks import create_article

def test_create_article(app, audio_file, transcription_file):
    data = {
        "search_intention": "Boletus en Soria",
        "category": "boletus",
        "image_description": "desc",
        "audio_file": audio_file,
        "image_file": (io.BytesIO(b"image-bytes"), "photo.jpg"),
    }
    
    with (patch("ArticleGenerator.tasks.TR_CLASS") as mock_tr_class,
          patch("ArticleGenerator.tasks.load_models") as mock_load):
        mock_load = MagicMock()
        mock_tr_class.transcribe_audio.return_value = transcription_file
        post_url, error = create_article(**data)

    assert post_url
    assert error is None
        