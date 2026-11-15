"""Initialize hosted tables and event snapshots at build time, not cold start."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if not os.environ.get('DATABASE_URL'):
    raise SystemExit('Set DATABASE_URL to your Supabase Postgres connection string before deploying.')

import server

server.initialize()
print('Souvenue database initialized. Existing accounts and posts were retained.')
