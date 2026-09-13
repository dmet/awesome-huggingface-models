"""Authenticated Runway SDK client."""
from runwayml import RunwayML

from config import settings


def get_client() -> RunwayML:
    return RunwayML(api_key=settings.require_api_secret())
