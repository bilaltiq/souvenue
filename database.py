"""Postgres adapter for the prototype's small, fixed SQLite query vocabulary.

Hosted data lives in an unexposed `souvenue` schema. Queries and permission
checks stay on the server; never expose DATABASE_URL to browser code.
"""
import re


class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


def row_factory(cursor):
    names = [column.name for column in (cursor.description or [])]
    return lambda values: Row(zip(names, values))


def postgres_sql(query):
    pragma = re.fullmatch(r"PRAGMA table_info\((\w+)\)", query.strip())
    if pragma:
        table = pragma.group(1)
        return ("SELECT ordinal_position AS cid,column_name AS name FROM information_schema.columns "
                f"WHERE table_schema='souvenue' AND table_name='{table}' ORDER BY ordinal_position")
    query = query.replace("json_set(metadata,'$.listed',0)", "jsonb_set(metadata::jsonb,'{listed}','false')::text")
    query = re.sub(r"json_extract\(metadata,'\$\.(\w+)'\)", r"(metadata::jsonb->>'\1')", query)
    ignore = 'INSERT OR IGNORE' in query
    query = query.replace('INSERT OR IGNORE', 'INSERT')
    query = re.sub(r'([\w.]+) COLLATE NOCASE', r'LOWER(\1)', query)
    # Only transform SQL tokens; leave quoted string literals untouched.
    parts = re.split(r"('(?:''|[^'])*')", query)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r'\buser\b', '"user"', parts[i])
        parts[i] = re.sub(r'\bREAL\b', 'DOUBLE PRECISION', parts[i])
        parts[i] = parts[i].replace('?', '%s')
    query = ''.join(parts).rstrip(';')
    return query + ' ON CONFLICT DO NOTHING' if ignore else query


class PostgresConnection:
    def __init__(self, url):
        import psycopg
        self.connection = psycopg.connect(
            url, row_factory=row_factory, prepare_threshold=None,
            connect_timeout=10,
        )
        # Transaction-local state works with Supabase's transaction pooler.
        self.connection.execute('SET LOCAL search_path TO souvenue')
        self.connection.execute("SET LOCAL statement_timeout = '25s'")

    def execute(self, query, args=()):
        return self.connection.execute(postgres_sql(query), args or None)

    def executemany(self, query, records):
        # Psycopg executemany uses pipelining, unsupported by Supavisor's
        # transaction pooler. Deliberately execute sequentially instead.
        for record in records:
            self.execute(query, record)

    def executescript(self, script):
        for query in script.split(';'):
            if query.strip():
                self.execute(query)

    def commit(self):
        self.connection.commit()
        self.connection.execute('SET LOCAL search_path TO souvenue')
        self.connection.execute("SET LOCAL statement_timeout = '25s'")

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        try:
            self.connection.rollback() if kind else self.connection.commit()
        finally:
            self.connection.close()
