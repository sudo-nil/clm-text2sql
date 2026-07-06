"""Environment-driven configuration. No hardcoded project IDs, locations, or model names."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    project: str
    location: str
    dataset: str
    model: str
    use_vertexai: bool

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            project=_require("GOOGLE_CLOUD_PROJECT"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
            dataset=os.environ.get("BQ_DATASET", "clm"),
            model=os.environ.get("GEMINI_MODEL", "gemini-2.5-pro"),
            use_vertexai=os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "true").lower() == "true",
        )
