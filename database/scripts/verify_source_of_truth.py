"""Production guard for the source of truth: fails unless the target database
has both prongs' shared contract in place (extensions + tables).

Used by the nightly price-getter cron (before any scrape) and by CD (after
migrations, before deploys). CI: database job.
"""

import os
import sys

from sqlalchemy import create_engine, text

EXPECTED_EXTENSIONS = {"postgis", "vector", "pg_trgm"}
EXPECTED_TABLES = {"stores", "products"}


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("FATAL: DATABASE_URL is not set")
        return 2

    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            extensions = {r[0] for r in conn.execute(text("SELECT extname FROM pg_extension"))}
            tables = {
                r[0]
                for r in conn.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            }

            missing_extensions = EXPECTED_EXTENSIONS - extensions
            missing_tables = EXPECTED_TABLES - tables

            if missing_extensions:
                print(f"FATAL: missing extensions: {sorted(missing_extensions)}")
            if missing_tables:
                print(f"FATAL: missing tables: {sorted(missing_tables)} — migrations not applied?")
            if missing_extensions or missing_tables:
                return 1

            print(f"source of truth OK — extensions: {sorted(extensions)}")
            print(f"tables present: {sorted(EXPECTED_TABLES)}")
            return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
