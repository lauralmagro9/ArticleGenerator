# Base imports
import pytest
import os

# Py PI imports
from werkzeug.datastructures import FileStorage
from io import BytesIO

def get_files(type):
    cwd = os.getcwd()
    data_folder = os.path.join(cwd, "tests", "data", type)
    return [os.path.join(data_folder, f) for f in os.listdir(data_folder)]

@pytest.fixture(params=get_files("audios"))
def audio_file(request):
    file_path = request.param
    base_name = os.path.basename(file_path)        
    ext = os.path.splitext(base_name)[1].replace(".", "")       

    with open(file_path, "rb") as f:
        data = f.read()

    buffer = BytesIO(data)

    return FileStorage(
        stream=buffer,
        filename=base_name,
        content_type=f"audio/{ext}",
    )

@pytest.fixture(params=get_files("images"))
def image_file(request):
    file_path = request.param
    base_name = os.path.basename(file_path)
    ext = os.path.splitext(base_name)[1].replace(".", "")
    with open(file_path, "rb") as f:
        data = f.read()
    buffer = BytesIO(data)
    return FileStorage(
        stream=buffer,
        filename=base_name,
        content_type=f"image/{ext}",
    )

# @pytest.fixture(params=get_files("transcriptions"))
#def transcription_file(request):
#    file_path = request.param
#    base_name = os.path.basename(file_path)
#       with open(file_path, "r") as f:
#        transcription = f.read()
#    return (transcription, base_name)