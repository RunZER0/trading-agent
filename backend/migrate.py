"""
Run database migrations against Supabase PostgreSQL.
Usage: python migrate.py
"""
import asyncio
import pathlib
import os
import sys


async def main():
    # Load .env from repo root
    env_path = pathlib.Path(__file__).parent.parent / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("✗ DATABASE_URL not set. Check your .env file.")
        sys.exit(1)

    try:
        import asyncpg
    except ImportError:
        print("Installing asyncpg...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "asyncpg"])
        import asyncpg  # type: ignore

    sql_path = pathlib.Path(__file__).parent / "migrations" / "001_initial_schema.sql"
    sql = sql_path.read_text()

    print(f"Connecting to Supabase...")
    try:
        conn = await asyncpg.connect(url, ssl="require")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        sys.exit(1)

    try:
        # Split on semicolons and run each statement individually
        # (asyncpg doesn't support multi-statement execute)
        statements = [s.strip() for s in sql.split(";") if s.strip() and not s.strip().startswith("--")]
        ok = 0
        for stmt in statements:
            try:
                await conn.execute(stmt)
                ok += 1
            except asyncpg.exceptions.DuplicateTableError:
                pass  # Table already exists — that's fine
            except asyncpg.exceptions.DuplicateObjectError:
                pass  # Index/publication already exists — fine
            except Exception as e:
                print(f"  ⚠ Statement skipped: {str(e)[:80]}")
        print(f"✓ Migration complete ({ok} statements executed)")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
