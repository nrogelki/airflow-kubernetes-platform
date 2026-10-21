# ADR 0003 · Entorno Conda aislado + `@task.external_python`

- **Estado:** Aceptada
- **Contexto:** Las tareas usan pandas/polars/drivers en versiones que chocan con las
  *constraints* de Airflow. Instalar todo en la imagen generaba conflictos y builds
  pesados; `_PIP_ADDITIONAL_REQUIREMENTS` descargaba de PyPI en cada arranque de Pod.
- **Decisión:** Imagen de Airflow mínima e inmutable (`pullPolicy: Never`). El trabajo
  pesado corre con `@task.external_python` en un entorno **Conda** autocontenido,
  montado por hostPath en solo lectura, con Airflow (misma versión, con constraints)
  instalado dentro para usar hooks y Connections.
- **Alternativas:**
  - *Todo en la imagen*: conflictos de dependencias y rebuild por cada librería.
  - *`@task.virtualenv`*: crea el venv en cada ejecución (lento, depende de PyPI).
  - *`python -m venv` montado*: sus symlinks apuntan a un intérprete del host que no existe en el Pod.
  - *Una imagen por equipo + KPO*: válido para stacks especiales ([docs/14](../14-imagenes-dedicadas-kpo.md)), excesivo como norma.
- **Consecuencias** (✅ beneficio · ⚠️ costo que se acepta):
  - ✅ Librerías de datos actualizables sin tocar la imagen ni Airflow.
  - ✅ Cero descargas en runtime.
  - ⚠️ Solo primitivos entre tareas; imports dentro de las funciones (disciplina que `check_dags.py` ayuda a mantener).
  - ⚠️ Lo que se importa al parsear (en la imagen, Python 3.12) no puede usar nada exclusivo de 3.13; el código de las tareas corre solo en el entorno (3.13).
