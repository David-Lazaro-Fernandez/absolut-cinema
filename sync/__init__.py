"""Archivo histórico en PostgreSQL: copia lo nuevo de data/snapshots.db y reconstruye la historia de cada función
desde el crudo de cada captura. Corre en el venv (psycopg); el scraper nunca importa este paquete.
Ver docs/postgres-esquema.md."""
