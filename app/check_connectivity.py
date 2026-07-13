"""Phase 1 smoke test: verify BigQuery and Vertex AI Gemini both work under ADC.

Run: python -m app.check_connectivity
"""
import logging

from google import genai
from google.cloud import bigquery

from app.config import Settings
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)


def check_bigquery(settings: Settings) -> None:
    logger.info("[bigquery] project=%s", settings.project)
    client = bigquery.Client(project=settings.project)
    rows = list(client.query("SELECT 1 AS x").result())
    assert rows[0].x == 1
    logger.info("[bigquery] OK -> %s", dict(rows[0]))


def check_vertex_ai(settings: Settings) -> None:
    logger.info(
        "[vertex-ai] project=%s location=%s model=%s", settings.project, settings.location, settings.model
    )
    client = genai.Client(vertexai=settings.use_vertexai, project=settings.project, location=settings.location)
    response = client.models.generate_content(
        model=settings.model,
        contents="Reply with exactly the word: pong",
    )
    logger.info("[vertex-ai] OK -> %r", response.text)


def main() -> None:
    configure_logging()
    settings = Settings.load()
    check_bigquery(settings)
    check_vertex_ai(settings)
    logger.info("All connectivity checks passed.")


if __name__ == "__main__":
    main()
