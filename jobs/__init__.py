"""Registro de trabajos programados: qué corre solo, cuándo, con qué tope y qué escribe.

- `jobs.keys`: la llave de cada trabajo y su área (capa del repo). Cualquier módulo puede nombrar un trabajo sin
  importar su código.
- `jobs.registry`: la entrada de cada llave (pasos, horario, tope, reintentos, dónde corre). Es la única fuente del
  calendario: las unidades de systemd, los agentes de launchd, `scraper.health` y la tabla de `ARCHITECTURE.md` salen
  de aquí.
- `jobs.run`: ejecuta un trabajo por llave, con candado por llave, tope de tiempo, reintentos y una línea por corrida
  en `data/logs/jobs.jsonl` (duración, resultado y pico de memoria).
- `jobs.units`: genera las unidades de systemd, los plists de launchd y la tabla de la documentación.

Solo librería estándar y Python 3.9+, igual que `scraper/`: corre con `/usr/bin/python3`. El registro nombra el código
de cada paso por módulo y lo lanza como subproceso con su intérprete; nunca lo importa.
"""
