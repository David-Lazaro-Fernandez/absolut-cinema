"""Diagrama de la arquitectura propuesta para la etapa 1 (Postgres como archivo histórico), con la librería
`diagrams` (iconos oficiales de AWS, render con Graphviz).

Correr:  .venv/bin/python docs/arquitectura_aws.py   →   docs/arquitectura-aws.png
Requiere `brew install graphviz` y `requirements-dev.txt`. El diagrama se regenera con el código: si cambia la
arquitectura, cambia este archivo, no la imagen.
"""
from pathlib import Path

from diagrams import Cluster, Diagram, Edge
from diagrams.custom import Custom
from diagrams.aws.compute import EC2
from diagrams.aws.database import RDS
from diagrams.aws.network import Route53
from diagrams.aws.storage import S3
from diagrams.onprem.client import User, Users

OUT = Path(__file__).with_name("arquitectura-aws")
LOGOS = Path(__file__).with_name("logos")   # PNG cuadrados: marcas oficiales (Wikimedia Commons, sitios propios)


WIDE = {"cinemex", "cinepolis", "didi", "sqlite"}   # logotipos horizontales: caja ancha y baja para que se lean


def logo(label, name):
    """Nodo con el logo de la marca en vez del icono genérico."""
    # Los PNG anchos ya traen la proporción de la caja (2.1 × 1.35 in), con el logo arriba y hueco para la etiqueta.
    size = {"width": "2.1", "height": "1.35", "imagescale": "true"} if name in WIDE else {}
    return Custom(label, str(LOGOS / f"{name}.png"), **size)

GRAPH = {"fontname": "Archivo, Helvetica", "fontsize": "12", "pad": "0.4", "splines": "spline"}
NODE = {"fontname": "Archivo, Helvetica", "fontsize": "11"}

with Diagram("absolut-cinema · etapa 1: captura en EC2, histórico en RDS", filename=str(OUT), show=False,
             direction="LR", graph_attr=GRAPH, node_attr=NODE):
    cinepolis = logo("Cinépolis GraphQL\napi-g.cinepolis.com", "cinepolis")
    cinemex = logo("Cinemex REST\napi.cinemex.com", "cinemex")
    rappi = logo("Rappi\nHTML", "rappi")
    didi = logo("DiDi Food\nHTML", "didi")

    with Cluster("EC2 · /opt/absolut-cinema · systemd (TZ America/Mexico_City)"):
        with Cluster("Captura (solo stdlib)"):
            snapshot = EC2("make snapshot\n07:30 · 13:30 · 20:30")
            seats = EC2("make seats\ncada 15 min")
            daily = EC2("make daily · delivery\n06:00 · 15:00")
        sqlite = logo("snapshots.db\nSQLite WAL · búfer local", "sqlite")
        sync = EC2("make sync\ncada 15 min · psycopg en su venv")
        with Cluster("Presentación"):
            caddy = logo("Caddy\nHTTPS + basic auth", "caddy")
            dashboard = logo("Streamlit\nviews/cartelera · views/dulceria", "streamlit")

    rds = RDS("RDS PostgreSQL\nshowtime · showtime_state (por captura)\nevent · muestras · precios")
    s3 = S3("S3 / Spaces\ncrudo .json.gz por captura\nrespaldo diario de la base")
    dns = Route53("dominio del cliente")
    directivos = Users("Directivos Cinemex")
    analistas = User("Analistas del cliente\nSQL directo al histórico")

    [cinepolis, cinemex] >> Edge(color="gray") >> snapshot
    cinepolis >> Edge(color="gray") >> seats
    [rappi, didi] >> Edge(color="gray") >> daily
    [snapshot, seats, daily] >> sqlite
    snapshot >> Edge(label="crudo") >> s3
    sqlite >> Edge(label="solo lo nuevo, tablas que solo crecen") >> sync >> rds
    sqlite >> Edge(style="dashed", label="respaldo 05:07") >> s3
    sqlite >> Edge(label="mode=ro", style="dashed") >> dashboard
    rds >> Edge(style="dashed", label="etapa 2:\nanalytics sobre Postgres") >> dashboard
    dashboard >> caddy >> dns >> directivos
    rds >> analistas

print(f"generado: {OUT}.png")
