"""Test environment, set before any app module is imported: never reach real LLM providers or the System One API,
whatever server/.env contains, and whichever test file pytest happens to import first."""

import os
from pathlib import Path

os.environ["SPATIAL_SYSTEM_ONE"] = "off"
os.environ["TYPESAFE_API_KEY"] = ""
os.environ["SPATIAL_PROVIDERS"] = "nothing"
os.environ["SPATIAL_OCR"] = "0"
os.environ["SPATIAL_API_TOKEN"] = ""
os.environ["SPATIAL_DB"] = str(Path(__file__).parent / "test_spatial.db")
os.environ["TAVILY_API_KEY"] = ""
os.environ["SPATIAL_SPEECH_BACKEND"] = "local"  # never call hosted speech from tests
os.environ["SPATIAL_AUDIO_WARM"] = "0"
os.environ["SPATIAL_ALLOWED_HOSTS"] = "127.0.0.1,localhost,testserver"
os.environ["SPATIAL_DESKTOP_TOKEN_FILE"] = str(Path(__file__).parent / "test_desktop.token")
