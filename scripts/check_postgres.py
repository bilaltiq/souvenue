"""Run the original flows against a disposable localhost Postgres in CI only."""
import os
import sys
import unittest
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
url = os.environ.get('DATABASE_URL', '')
parsed = urlparse(url)
if parsed.hostname != '127.0.0.1' or parsed.path != '/souvenue_test':
    raise SystemExit('This destructive test runner is restricted to localhost/souvenue_test.')

import psycopg
import server
import test_app


class PostgresResult(unittest.TextTestResult):
    def startTest(self, test):
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute('DROP SCHEMA IF EXISTS souvenue CASCADE')
        super().startTest(test)


suite = unittest.defaultTestLoader.loadTestsFromModule(test_app)
# Run the same local-prototype flows with only their storage engine changed.
with patch.object(server, 'hosted', return_value=False):
    result = unittest.TextTestRunner(resultclass=PostgresResult, verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
