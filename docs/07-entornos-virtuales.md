# 07 · Entornos virtuales: buenas prácticas

## 1. Por qué un entorno aislado

La imagen de Airflow trae cientos de dependencias fijadas por sus *constraints*. Si
instalas ahí pandas, polars o drivers, tarde o temprano una versión choca con Airflow
(el famoso *dependency hell*) y el scheduler deja de arrancar.

La solución: **dos niveles de dependencias** que nunca se mezclan.

| | Imagen de Airflow | Entorno aislado `p313` |
|---|---|---|
| Python | 3.12 | 3.13 |
| Contiene | Airflow + providers livianos | Airflow (para hooks) + librerías de datos |
| Lo usan | scheduler, dag-processor, api-server, proceso base de la tarea | el subproceso de `@task.external_python` |
| Se actualiza | reconstruyendo la imagen (tag nuevo) | `make conda-env`, sin tocar la imagen |
| Se monta | — | hostPath **solo lectura** en el Pod de tarea |

## 2. ¿Por qué Conda y no `python -m venv`?

Un `venv` **no copia el intérprete**: crea enlaces simbólicos a un Python del host (p. ej.
`/usr/bin/python3.13`). Montado dentro del Pod, ese enlace apunta a una ruta que **no
existe en el contenedor** → `No such file or directory`.

Un entorno Conda es **autocontenido**: trae su propio intérprete y sus librerías
nativas (OpenSSL, libstdc++, GDAL...). Por eso funciona montado en cualquier contenedor
glibc. Alternativas válidas con la misma propiedad: `uv python install` + venv sobre ese
Python standalone, o `python-build-standalone`.

## 3. Reglas

1. **Misma ruta en el host y en el Pod.** Crea el entorno en `/opt/conda/envs/p313` del
   host y móntalo en `/opt/conda/envs/p313`. Conda escribe su prefijo en algunos scripts;
   si la ruta coincide, nada se rompe. (Es el default de `platform.env`.)
2. **Airflow dentro del entorno, misma versión que la imagen.** Sin él no hay
   `BaseHook.get_connection` ni providers dentro de la tarea. Está fijado en
   `environment.yml` (`apache-airflow==3.2.1`): al subir Airflow, cambia ambos.
3. **Pocos entornos, no uno por DAG.** Cada entorno es un volumen más en el
   `pod_template` y algo más que mantener. Crea otro solo ante una incompatibilidad real
   (p. ej. una librería que exige Python 3.10).
4. **Solo lectura.** El Pod lo monta `readOnly`: una tarea no puede hacer `pip install`
   y "arreglar" el entorno para todas las demás.
5. **Legible por todos** (`chmod -R a+rX`): los Pods corren como UID 50000.
6. **Declarativo, fijado y versionado.** Dos archivos en `envs/p313/`, ambos en git:
   - `environment.yml`: lo que tú mantienes. Solo dependencias **directas**, cada una con
     versión exacta (`python=3.13.15`, `polars==1.44.2`...). Nunca `>=`.
   - `environment.lock.yml`: lo genera `make conda-env` con `conda env export`. Fija
     **todo**, incluidas las dependencias indirectas. Con él, un servidor nuevo queda
     idéntico al actual; no lo edites a mano.
7. **Nunca `pip install` a mano en el entorno productivo.** Edita `environment.yml`, corre
   `make conda-env` y commitea **los dos** archivos.
8. **Cambios grandes con *blue/green*.** Para una actualización arriesgada (pandas 2→3,
   Python 3.13→3.14), crea un entorno nuevo en paralelo:

   ```bash
   mkdir envs/p314 && cp envs/p313/environment.yml envs/p314/   # sin el lock
   # editar envs/p314/environment.yml: name: p314, python=3.14.x, versiones nuevas
   cp config/platform.env /tmp/p314.env
   sed -i 's/^PYTHON_ENV_NAME=.*/PYTHON_ENV_NAME="p314"/' /tmp/p314.env
   sudo ENV_FILE=/tmp/p314.env scripts/create_conda_env.sh
   ```

   Monta ambos en el `pod_template`, migra los DAGs uno a uno cambiando la constante
   `PYTHON_ENV`, y retira el viejo cuando ninguno lo use. Nunca lo modifiques en
   caliente mientras hay tareas corriendo.
9. **Un entorno de desarrollo local separado.** Para tests y lint usa un `.venv` normal
   con `requirements-dev.txt` (`make dev-install`). Ese sí puede ser `venv`: no se monta
   en ningún Pod.

## 4. Verificar e inspeccionar

```bash
/opt/conda/envs/p313/bin/python --version
/opt/conda/envs/p313/bin/python -m pip list | grep -Ei "polars|pandas|airflow"
/opt/conda/envs/p313/bin/python -c "import dataplatform" 2>/dev/null \
  || echo "normal: dataplatform se resuelve por PYTHONPATH dentro del Pod"

# Desde dentro de un Pod:
kubectl exec -n airflow deploy/airflow-scheduler -c scheduler -- ls /opt/airflow/libs
```

## 5. Errores típicos

| Síntoma | Causa | Solución |
|---|---|---|
| Todos los Pods de tarea en `ContainerCreating`; evento `hostPath type check failed` | La ruta del entorno no existe en el nodo | `make conda-env` o corregir `CONDA_ENVS_HOST_PATH` |
| `No such file or directory: /opt/conda/envs/p313/bin/python` | Entorno creado con `venv`, o en otra ruta | Recrear con Conda en la misma ruta |
| `ModuleNotFoundError: polars` en una tarea | Tarea con `@task` en vez de `@task.external_python` | Usar `external_python` |
| `ModuleNotFoundError: polars` en el dag-processor | Import global en `_dag.py` | Moverlo dentro de la tarea (`check_dags.py` lo detecta) |
| `ModuleNotFoundError: airflow` dentro de la tarea | Entorno sin Airflow | `make conda-env` (Airflow está en `environment.yml`) |
| `PermissionError` al importar | Entorno no legible por UID 50000 | `sudo chmod -R a+rX /opt/conda/envs/p313` |
