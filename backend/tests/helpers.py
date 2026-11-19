from pathlib import Path

from app.analysis.build import build_model
from app.analysis.scan import scan_repo
from app.render.view import build_view


def make_repo(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return root


def view_edges(m, depth: int = 1):
    """Relations as drawn at `depth`, keyed by (source, target)."""
    return {(r.source, r.target): r for r in build_view(m, depth).relations}


def model_of(root: Path, files: dict[str, str], name: str = "demo"):
    make_repo(root, files)
    return build_model(root, scan_repo(root), name)


COMPOSE_MONOREPO = {
    "docker-compose.yml": """
services:
  api:
    build: ./backend
    depends_on: [db, cache]
    environment:
      - STRIPE_SECRET_KEY=x
  web:
    build:
      context: ./frontend
    depends_on:
      - api
  db:
    image: postgres:16
  cache:
    image: redis:7
  proxy:
    image: nginx:alpine
    depends_on: [web]
""",
    "backend/pyproject.toml": """
[project]
name = "shop-api"
description = "Shop API"
dependencies = ["fastapi>=0.1", "psycopg2-binary", "stripe", "celery"]
""",
    "backend/app/main.py": "from app.routes import users\n",
    "backend/app/routes/__init__.py": "",
    "backend/app/routes/users.py": (
        "from fastapi import APIRouter\n"
        "from app.services.users import create_user\n"
        "from ..models.user import User\n"
    ),
    "backend/app/services/__init__.py": "",
    "backend/app/services/users.py": (
        "import stripe\nfrom app.repositories import users_repo\nfrom app.core import config\n"
    ),
    "backend/app/repositories/__init__.py": "",
    "backend/app/repositories/users_repo.py": (
        "import psycopg2\nfrom app.models.user import User\n"
    ),
    "backend/app/models/__init__.py": "",
    "backend/app/models/user.py": "class User: ...\n",
    "backend/app/core/config.py": "X = 1\n",
    "frontend/package.json": '{"name":"shop-web","dependencies":{"react":"18","axios":"1"}}',
    "frontend/src/App.tsx": "import Home from './pages/Home'\nimport { api } from '@/api/client'\n",
    "frontend/src/pages/Home.tsx": (
        "import Button from '../components/Button'\nimport x from 'react'\n"
    ),
    "frontend/src/components/Button.tsx": "export default 1\n",
    "frontend/src/api/client.ts": "export * from './types'\nimport axios from 'axios'\n",
    "frontend/src/api/types.ts": "export type T = 1\n",
}
