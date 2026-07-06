"""Phase 1 smoke test: verify BigQuery and Vertex AI Gemini both work under ADC.

Run: python -m app.check_connectivity
"""
from google import genai
from google.cloud import bigquery

from app.config import Settings


def check_bigquery(settings: Settings) -> None:
    print(f"[bigquery] project={settings.project}")
    client = bigquery.Client(project=settings.project)
    rows = list(client.query("SELECT 1 AS x").result())
    assert rows[0].x == 1
    print(f"[bigquery] OK -> {dict(rows[0])}")


def check_vertex_ai(settings: Settings) -> None:
    print(f"[vertex-ai] project={settings.project} location={settings.location} model={settings.model}")
    client = genai.Client(vertexai=settings.use_vertexai, project=settings.project, location=settings.location)
    response = client.models.generate_content(
        model=settings.model,
        contents="Reply with exactly the word: pong",
    )
    print(f"[vertex-ai] OK -> {response.text!r}")


def main() -> None:
    settings = Settings.load()
    check_bigquery(settings)
    check_vertex_ai(settings)
    print("\nAll connectivity checks passed.")


if __name__ == "__main__":
    main()
