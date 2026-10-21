# Contribuir

¡Gracias por querer mejorar la plataforma! Toda contribución es bienvenida: correcciones
de documentación, nuevas plantillas de alertas, building blocks, fixes de
infraestructura o reportes de incidentes reales con su solución.

## Antes de empezar

- Para cambios grandes (arquitectura, nuevos componentes), abre primero un **issue** o
  una **Discussion** para acordar el enfoque.
- Lee [docs/05-desarrollo-de-dags.md](docs/05-desarrollo-de-dags.md) y los
  [ADR](docs/adr/): explican el porqué de las decisiones.

## Entorno de desarrollo

```bash
sudo apt-get install -y python3-venv   # Ubuntu/Debian: sin esto, `python3 -m venv` falla
python3 -m venv .venv && . .venv/bin/activate
make dev-install          # pytest, ruff, yamllint, shellcheck, pre-commit + hooks
make lint test check-dags
```

No necesitas Kubernetes para contribuir a `libs/`, `tools/`, `scripts/` o la
documentación: los tests corren sin Airflow ni clúster.

## Flujo

1. Fork y rama desde `main`: `feat/slack-threads`, `fix/doctor-disk-check`, `docs/…`.
2. Commits pequeños con [Conventional Commits](https://www.conventionalcommits.org/es/):
   `feat(alerts): agrega plantilla para Discord`, `fix(scripts): …`, `docs: …`.
3. Agrega tests para código nuevo en `libs/` o `tools/` (funciones puras cuando se pueda).
4. Actualiza la documentación y `CHANGELOG.md` (sección `[Unreleased]`).
5. Abre el PR con la plantilla. CI debe quedar en verde.

## Estándares

- **Python:** `ruff` (lint + format). Lo que se importa al parsear un DAG debe ser
  compatible con 3.12 (imagen); el resto corre en 3.13 (entorno). Código y comentarios en
  inglés; documentación en español.
- **Shell:** `bash` con `set -euo pipefail`, pasando `shellcheck -x`. Scripts idempotentes.
- **YAML:** `yamllint`.
- **Plantillas** (`*.template.yaml`): toda variable nueva va en
  `config/platform.env.example` **y** en la lista `VARS` de `scripts/render_config.sh`.
- **Nunca** incluyas secretos, IPs reales, hostnames internos ni nombres de empresas en
  ejemplos. Usa `example.com`, `10.0.0.x` y placeholders.

## Reportar bugs

Usa la plantilla de issue e incluye la salida de `make doctor` y las versiones
(MicroK8s, Helm, chart, Airflow). Quita credenciales e IPs antes de pegar logs.

Al participar aceptas el [Código de Conducta](CODE_OF_CONDUCT.md).
