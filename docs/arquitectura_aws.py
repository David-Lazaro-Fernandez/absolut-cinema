"""Diagrama del despliegue en AWS (EC2 con la captura nacional y todo en SQLite), con la librería
`diagrams` (iconos oficiales de AWS, render con Graphviz).

Correr:  .venv/bin/python docs/arquitectura_aws.py   →   docs/arquitectura-aws.png
Requiere `brew install graphviz` y `requirements-dev.txt`. El diagrama se regenera con el código: si cambia la
arquitectura, cambia este archivo, no la imagen. Refleja `ARCHITECTURE.md` al 2026-09-25: EC2 en marcha desde el
2026-09-10 con la salida a Cinépolis por Cloudflare WARP; sin Postgres ni RDS (dos bases SQLite, un escritor cada una).
"""
from pathlib import Path

from diagrams import Cluster, Diagram, Edge
from diagrams.custom import Custom
from diagrams.aws.compute import EC2
from diagrams.aws.engagement import SimpleEmailServiceSes
from diagrams.aws.network import Route53
from diagrams.aws.storage import S3
from diagrams.generic.network import Router
from diagrams.onprem.client import User, Users
from diagrams.saas.cdn import Cloudflare

OUT = Path(__file__).with_name("arquitectura-aws")
LOGOS = Path(__file__).with_name("logos")   # PNG cuadrados: marcas oficiales (Wikimedia Commons, sitios propios)


WIDE = {"cinemex", "cinepolis", "didi", "sqlite"}   # logotipos horizontales: caja ancha y baja para que se lean


def logo(label, name):
    """Nodo con el logo de la marca en vez del icono genérico."""
    # Los PNG anchos ya traen la proporción de la caja (2.1 × 1.35 in), con el logo arriba y hueco para la etiqueta.
    size = {"width": "2.1", "height": "1.35", "imagescale": "true"} if name in WIDE else {}
    return Custom(label, str(LOGOS / f"{name}.png"), **size)

GRAPH = {"fontname": "Archivo, Helvetica", "fontsize": "12", "pad": "0.4", "splines": "spline",
         "ranksep": "1.4", "nodesep": "0.6"}
NODE = {"fontname": "Archivo, Helvetica", "fontsize": "11"}

with Diagram("absolut-cinema · captura nacional en EC2, todo en SQLite", filename=str(OUT),
             show=False, direction="LR", graph_attr=GRAPH, node_attr=NODE):
    with Cluster("Fuentes externas (APIs públicas con clave embebida)"):
        cinepolis = logo("Cinépolis GraphQL\napi-g.cinepolis.com\ncartelera · planos · boletos · dulcería",
                         "cinepolis")
        cinemex = logo("Cinemex REST\napi.cinemex.com", "cinemex")
        rappi = logo("Rappi\nHTML", "rappi")
        didi = logo("DiDi Food\nHTML", "didi")

    with Cluster("EC2 t4g.medium · /opt/absolut-cinema · systemd (TZ America/Mexico_City)"):
        # El WAF de Cloudflare de Cinépolis bloquea los rangos de AWS por ASN (verificado 2026-09-10): la salida a
        # ese host pasa por el WARP de la instancia. No es para repartir el ritmo; el ritmo lo frena config.py.
        with Cluster("Salida solo para los hosts de AC_EGRESS_PROXY_HOSTS"):
            warp = Cloudflare("cliente WARP en modo proxy\nSOCKS5 127.0.0.1:40000")
            privoxy = Router("Privoxy · HTTP :8118\nAC_EGRESS_PROXY")

        with Cluster("Captura (solo stdlib, /usr/bin/python3)"):
            snapshot = EC2("make snapshot · scraper.run\ncartelera nacional 07:30 · 13:30 · 20:30")
            seats = EC2("make seats · sample --post-start\ncada hora (:50) · ambas cadenas · AC_SEATS_PLAZAS")
            presale = EC2("make presale · 10:07\npreventas de ambas cadenas")
            prices = EC2("make prices concessions · 06:07\nboletos y menú de dulcería")
            capacity = EC2("make capacity · día 1, 04:07\naforo por sala (plano público)")
            delivery = EC2("make delivery · 15:07\ndulcería a domicilio")
            health = EC2("make health · 08:07\nlogs/health.log · sale con 1 si hay problemas;\n"
                         "las mismas funciones pintan la página Operaciones")

        sqlite = logo("snapshots.db\nSQLite WAL · escribe solo la captura", "sqlite")
        cuentas = logo("app.db\nSQLite WAL · escribe solo auth/\naccount · session · token · audit", "sqlite")

        with Cluster("Presentación"):
            caddy = logo("Caddy\nHTTPS (basic auth hasta el dominio)", "caddy")
            dashboard = logo("Streamlit · app.py\ncartelera · dulcería · datos\nusuarios · operaciones (admin)",
                             "streamlit")

    s3 = S3("S3\ncrudo .json.gz por captura\nrespaldo diario 05:07 de ambas bases")
    ses = SimpleEmailServiceSes("Amazon SES\ninvitación y restablecimiento")
    dns = Route53("dominio del cliente")
    directivos = Users("Directivos Cinemex")
    analistas = User("Analistas del cliente\nexplorador Datos")

    cinepolis >> Edge(color="gray", label="el WAF rechaza\nla IP de AWS") >> warp >> privoxy
    privoxy >> Edge(color="gray") >> [snapshot, seats, prices, capacity, presale]
    cinemex >> Edge(color="gray") >> [snapshot, seats, prices, capacity, presale]
    [rappi, didi] >> Edge(color="gray") >> delivery
    [snapshot, seats, prices, capacity, delivery, presale] >> sqlite
    snapshot >> Edge(label="crudo") >> s3
    sqlite >> Edge(style="dashed", label="lee") >> health
    sqlite >> Edge(style="dashed", label="respaldo 05:07") >> s3
    sqlite >> Edge(style="dashed", label="mode=ro · analytics/") >> dashboard
    dashboard >> Edge(label="auth/ · lo único\nque escribe") >> cuentas
    cuentas >> Edge(style="dashed", label="respaldo 05:07") >> s3
    dashboard >> Edge(style="dashed") >> ses
    dashboard >> caddy >> dns >> directivos
    dns >> analistas

print(f"generado: {OUT}.png")
