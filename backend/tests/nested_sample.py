"""A small repo with real folder depth, shared by the hierarchy, view and render tests."""

NESTED = {
    "package.json": '{"name":"w","dependencies":{"express":"4"}}',
    "src/index.ts": "import './api/routes/users'\n",
    "src/api/routes/users.ts": "import { u } from '../../services/users'\nimport '../deps'\n",
    "src/api/routes/items.ts": "import { i } from '../../services/items'\nimport '../deps'\n",
    "src/api/deps.ts": "export const d = 1\n",
    "src/services/users.ts": "import '../db/models/user'\nimport '../db/client'\n",
    "src/services/items.ts": "import '../db/models/item'\nimport '../db/client'\n",
    "src/db/models/user.ts": "x\n",
    "src/db/models/item.ts": "x\n",
    "src/db/client.ts": "import pg from 'pg'\n",
    "src/shared/a/b/c/leaf.ts": "x\n",
    "src/shared/a/b/c/leaf2.ts": "x\n",
}
