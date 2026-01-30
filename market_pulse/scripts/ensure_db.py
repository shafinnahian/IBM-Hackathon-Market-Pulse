"""
Create the application database if it does not exist.

Connect to the PostgreSQL server (database 'postgres'), check pg_database
for the target database name from DATABASE_URL, and run CREATE DATABASE
only when it is missing. Does not create tables or run migrations.

Usage:
    uv run python -m market_pulse.scripts.ensure_db

Requires DATABASE_URL in the environment (e.g. postgresql+asyncpg://user:pass@host:5432/market_pulse_dev).
Both postgresql:// and postgresql+asyncpg:// are accepted; +asyncpg is stripped for asyncpg.
"""

import asyncio
import os
from urllib.parse import urlparse, urlunparse

import asyncpg
from dotenv import load_dotenv

load_dotenv()


def _get_server_url_and_db_name() -> tuple[str, str]:
    """Parse DATABASE_URL into a server URL (connect to 'postgres') and the target DB name."""
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        raise SystemExit("DATABASE_URL is not set")

    # asyncpg uses postgresql://; strip SQLAlchemy-style postgresql+asyncpg
    url = raw.replace("postgresql+asyncpg", "postgresql", 1)
    parsed = urlparse(url)
    if parsed.scheme != "postgresql":
        raise SystemExit("DATABASE_URL must use postgresql:// or postgresql+asyncpg://")

    # path is like /market_pulse_dev or /market_pulse_dev?options=...
    path = parsed.path.strip("/")
    if "?" in path:
        path = path.split("?")[0]
    db_name = path or "postgres"
    if db_name == "postgres":
        raise SystemExit(
            "DATABASE_URL must point to an application database, not the default 'postgres'"
        )

    # Build URL for connecting to the 'postgres' database (server connection)
    server_path = "/postgres"
    if parsed.query:
        server_path = f"/postgres?{parsed.query}"
    server_parsed = parsed._replace(path=server_path)
    server_url = urlunparse(server_parsed)
    return server_url, db_name


async def _ensure_database(server_url: str, db_name: str) -> None:
    conn = await asyncpg.connect(server_url)
    try:
        row = await conn.fetchrow(
            "SELECT 1 FROM pg_database WHERE datname = $1", db_name
        )
        if row is None:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
            print(f"Created database: {db_name}")
        else:
            print(f"Database already exists: {db_name}")
    finally:
        await conn.close()


def main() -> None:
    server_url, db_name = _get_server_url_and_db_name()
    asyncio.run(_ensure_database(server_url, db_name))


if __name__ == "__main__":
    main()
