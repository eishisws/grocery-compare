# Disposable CI background: disposable Postgres source-of-truth image.
# Stock Postgres images don't ship both extensions; PostGIS image lacks
# pgvector (pgdg repos are pre-configured here, so it installs fine).
FROM postgis/postgis:16-3.5

RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-16-pgvector \
 && rm -rf /var/lib/apt/lists/*
