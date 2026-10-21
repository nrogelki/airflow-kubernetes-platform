# Changelog

Todos los cambios relevantes de este proyecto se documentan aquí.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
versionado según [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

### Changed

- `example_kpo`: imagen dedicada `python:3.10-slim` → `python:3.11-slim` (Python 3.10
  llega a fin de soporte en octubre de 2026).
- Dependabot agrupa las actualizaciones en un PR por ecosistema (los saltos mayores de
  pip siguen en PRs separados).
- `detect-secrets` en pre-commit usa un `.secrets.baseline` con los falsos positivos
  auditados.
- Acciones del CI actualizadas (`checkout` v7, `setup-python` v7, `setup-helm` v5,
  `setup-kubectl` v5, `setup-buildx-action` v4, `build-push-action` v7) y mínimos de
  las herramientas de desarrollo (ruff 0.17, pytest 9, yamllint 1.38, pre-commit 4.7).
- Hooks de pre-commit alineados con el CI: `pre-commit-hooks` v6.0.0, ruff v0.17.1 y
  shellcheck v0.11.0.1.
- `polars` fijado en `requirements-dev.txt` a la misma versión que el entorno de
  producción (`envs/p313`, 1.44.2), para que los tests prueben lo que corre en los DAGs.

### Fixed

- Plantilla de issues y `CONTRIBUTING.md` enlazaban a Discussions, que no están activas;
  ahora apuntan a las preguntas frecuentes y al troubleshooting.
- El ejemplo de DAG del README explica por qué los DAGs reales añaden un guard de
  `sys.path`.

## [1.0.0] - 2026-10-20

Primera versión pública.

### Added

- Despliegue de Apache Airflow 3.2.1 con KubernetesExecutor sobre MicroK8s 1.35 de un
  nodo, con el chart oficial `apache-airflow/airflow` 1.22.0 (fijado), configurado desde
  un único `config/platform.env`.
- Plantillas `helm/values.template.yaml` y `pod_template.template.yaml` con los ajustes
  de producción de Airflow 3: secret key idéntica en tres lugares, `api.workers=1`,
  `base_url` en `[api]`, `execution_api_server_url`, `mp_start_method=spawn`, probes
  relajados, logs servidos por el api-server, NodePort fijo, recursos dimensionados por
  componente y volumen de PostgreSQL configurable (`POSTGRES_STORAGE_SIZE`,
  `STORAGE_CLASS`).
- Scripts idempotentes (`make`): instalación fijada de MicroK8s y Helm (RBAC activado),
  bootstrap del host, entorno Conda aislado, build e import de la imagen a containerd,
  deploy, `doctor`, scaffolding de DAGs y reparación del entorno.
- Imagen de Airflow inmutable con integraciones fijadas a las constraints oficiales
  (Hive, ClickHouse, Google APIs).
- Entorno aislado `p313` (Python 3.13) para `@task.external_python`, definido en
  `envs/p313/environment.yml` con versiones exactas y un `environment.lock.yml` que fija
  también las dependencias indirectas (linux-64).
- CronJobs de auto-sanación (limpieza de Pods y watchdog de Calico) con su código fuente
  en archivos `.sh`, empaquetados con Kustomize, y suite de pruebas `test-watchdog.sh`.
- Librería `dataplatform`: alertas (email, Slack, Teams, Google Chat, webhook;
  fallo/reintento/éxito), Postgres (COPY, engine), SFTP, calidad de datos, fechas,
  reintentos, SQL y DataFrames.
- DAGs de ejemplo: `example_etl`, `example_alerts`, `example_resource_override` y
  `example_kpo` (KubernetesPodOperator con otra imagen, con y sin `pod_template_file`,
  funcional con y sin RBAC).
- `tools/check_dags.py`, tests con pytest, pre-commit y CI (lint, tests, helm template,
  kustomize, build de imagen).
- Documentación: 16 guías (de conceptos clave a preguntas frecuentes, incluida la
  migración desde CeleryExecutor y desde Airflow 2) y 4 ADR.

[Unreleased]: https://github.com/nrogelki/airflow-kubernetes-platform/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/nrogelki/airflow-kubernetes-platform/releases/tag/v1.0.0
