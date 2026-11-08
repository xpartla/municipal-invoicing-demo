"""The OpenAPI document the frontend's typed client is generated from (`pnpm gen:api`)."""

import json

from riso import paths

OPENAPI_FILE = paths.REPO_ROOT / "frontend" / "openapi.json"


def openapi_json() -> str:
    """The app's OpenAPI document as stable, readable JSON. The routes are the same with or
    without a database, so the demo configuration is enough to build it."""
    from riso.api.app import Settings, create_app

    schema = create_app(Settings()).openapi()
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
