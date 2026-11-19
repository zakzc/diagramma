"""Print the OpenAPI schema without starting a server (used by `npm run gen:api`)."""

import json

from app.main import app

print(json.dumps(app.openapi(), indent=2))
