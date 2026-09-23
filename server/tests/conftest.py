"""Test environment: never reach the real System One API, whatever server/.env contains."""

import os

os.environ["SPATIAL_SYSTEM_ONE"] = "off"
os.environ["TYPESAFE_API_KEY"] = ""
