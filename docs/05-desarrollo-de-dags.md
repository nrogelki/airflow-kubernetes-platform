# 05 · Desarrollo de DAGs

> Regla central: **los DAGs orquestan, no procesan.** Todo lo pesado corre en el
> entorno aislado vía `@task.external_python`.

## 1. Anatomía de un DAG

```
dags/sales_daily/
├── _dag.py              ← definición + tareas delgadas (lo parsea el dag-processor)
├── README.md            ← qué hace, schedule, conn_ids, flujo (obligatorio)
├── scripts/             ← lógica propia del pipeline (NO la parsea Airflow: .airflowignore)
│   ├── __init__.py
│   └── etl.py
└── sql/                 ← consultas .sql (opcional)
files/sales_daily/       ← inputs (config.json, rename.json) + staging en runtime
```

Créalo siempre con el generador (deja estructura, plantilla y permisos correctos):

```bash
make new-dag NAME=sales_daily ARGS='-s "0 6 * * *" -a "data@example.com" -z America/Santiago'
```

## 2. PYTHONPATH: la pieza que lo simplifica todo

Todos los componentes y todos los Pods de tarea tienen:

```
PYTHONPATH=/opt/airflow/dags:/opt/airflow/libs
```

### Beneficios

1. **Imports absolutos y limpios, sin hacks de rutas.**
   `from dataplatform.db.postgres import copy_csv` funciona igual en el scheduler, en el
   dag-processor, en el Pod de tarea y dentro del subproceso de `external_python`. Nada
   de `sys.path.append("../../utils")` ni rutas relativas que se rompen al mover un DAG.
2. **Una sola fuente de verdad para el código compartido.** Corriges un bug en
   `libs/dataplatform/` y lo reciben *todos* los DAGs en la siguiente ejecución, sin copiar
   archivos entre carpetas.
3. **Cero rebuilds.** `libs/` se monta por hostPath: no hay que reconstruir la imagen ni
   hacer `helm upgrade` para publicar una librería nueva. `git pull` y listo.
4. **Cada DAG es un paquete con espacio de nombres propio.** Como `dags/` también está en
   el PYTHONPATH, `from sales_daily.scripts.etl import run` no choca con el `etl.py` de
   otro DAG (`from inventory.scripts.etl import run`). Con carpetas planas, dos
   `utils.py` se pisan.
5. **Testeable fuera de Airflow.** `libs/` y `scripts/` son Python normal: los tests
   (`tests/`) los importan agregando las mismas rutas en `conftest.py`, sin levantar
   Airflow.
6. **Heredado por el subproceso aislado.** `external_python` hereda el entorno del Pod
   (`inherit_env=True` por defecto), así que el intérprete de `p313` encuentra
   `dataplatform` sin instalarlo como paquete.

### Implicancias (lo que hay que respetar)

- **Imagen (Python 3.12) y entorno (3.13).** El código de tus tareas corre solo en el
  entorno (3.13): ahí no hay nada que cuidar. Lo único que también lee la imagen es lo que
  se importa **a nivel global** en `_dag.py` (p. ej. `dataplatform.alerts`): ahí evita lo
  exclusivo de 3.13. Si se te escapa, el DAG aparece con un import error en la UI y en
  `make check-dags`; no falla en silencio. `ruff` (`py312`) detecta la sintaxis nueva, no
  las funciones nuevas de la librería estándar.
- **Lo que se importa en parse-time debe ser liviano.** Todo módulo importado a nivel
  global en un `_dag.py` se ejecuta en cada parseo, con las librerías de la imagen base
  (no las de `p313`).
  Por eso `dataplatform.alerts` solo usa la librería estándar al importarse.
- **`expect_airflow=True` es el valor por defecto** de `@task.external_python`: escribirlo
  o no da lo mismo; en los ejemplos va explícito para dejar claro que la tarea cuenta con
  Airflow en el entorno. Lo que aporta: la función recibe además el contexto de Airflow
  (`params`, `dag_run`, `macros`, `conf`); con `False` solo llegan lo básico (`run_id`,
  `ds`…) y las fechas. **Lo esencial no es el parámetro sino que el entorno tenga la misma
  versión de Airflow que la imagen** (en `p313`, fijada en `environment.yml`): de eso
  dependen `BaseHook.get_connection` y `Variable.get` dentro de la tarea. Si falta o no
  coincide, la tarea no falla: solo deja un aviso en el log y se queda sin ese contexto
  (y sin conexiones si falta Airflow). Verificado en MicroK8s.
- **Los nombres de paquete son globales.** No nombres un DAG como una librería real
  (`pandas`, `requests`, `airflow`): lo taparía. `check_dags.py` exige que la carpeta se
  llame igual que el `dag_id`.

## 3. Los tres patrones de import

**Patrón 1 — building block de `libs/` dentro de una tarea**

```python
@task.external_python(python=PYTHON_ENV, expect_airflow=True)
def load_config(local_path: str) -> dict:
    from dataplatform.utils.local_files import read_json  # ← import DENTRO

    return read_json(local_path, "config.json")
```

**Patrón 2 — lógica propia del DAG (`scripts/`)**

```python
@task.external_python(python=PYTHON_ENV, expect_airflow=True)
def transform(parquet_path: str, local_path: str) -> dict:
    import sys

    if "/opt/airflow/dags" not in sys.path:  # guard defensivo (PYTHONPATH ya lo incluye)
        sys.path.insert(0, "/opt/airflow/dags")
    from example_etl.scripts.example_etl_etl import summarize  # ruta completa <dag_id>.scripts.<mod>

    return summarize(parquet_path, local_path)
```

**Patrón 3 — lo único que va global en `_dag.py`**: lo que Airflow necesita para
*construir* el DAG: decoradores, operadores y **callbacks de alertas**.

```python
from airflow.sdk import dag, task
from dataplatform.alerts.webhooks import slack_alert
```

¿Por qué los imports van dentro? `external_python` **serializa el código fuente de la
función** y lo ejecuta en otro intérprete: los imports globales del `_dag.py` no viajan
(→ `NameError`) y, además, cargarían pandas en el dag-processor en cada parseo.

## 4. Reglas de oro

1. **Solo primitivos entre tareas** (`str`, `int`, `float`, `bool`, `list`, `dict`). Un
   DataFrame se guarda como **archivo** en `files/<dag_id>/` y a la tarea siguiente le
   pasas **su ruta**. El formato lo eliges tú:

   | Usa | Cuándo |
   |---|---|
   | **Parquet** (recomendado) | Datos que una tarea deja para la siguiente: conserva tipos, pesa menos y se lee más rápido |
   | **CSV** | Cuando el destino lo pide (p. ej. `COPY` de Postgres) o alguien tiene que abrirlo en Excel |

   ¿No conoces Parquet? Ver el [glosario](00-conceptos-clave.md#formatos-de-archivo).
2. **Credenciales solo por `conn_id`.** Nunca en código, `files/` ni Variables en texto
   plano. La tarea recibe el `conn_id` y abre su propia conexión.
3. **`catchup=False` y `max_active_runs=1`** salvo necesidad justificada.
4. **Idempotencia.** Re-ejecutar un día no debe duplicar datos: `DELETE ... WHERE day =
   '{ds}'` antes de cargar, o `MERGE`/`INSERT ... ON CONFLICT`.
5. **Alertas en todo DAG productivo** ([12-alertas.md](12-alertas.md)).
6. **Promover a `libs/` solo cuando un segundo DAG lo necesita.** Nada "por si acaso".
7. **Sin `.py` sueltos en la raíz de `dags/`**: los parsea el dag-processor.
8. **Usa `ds`/`logical_date`, nunca `datetime.now()`**, para que los reprocesos sean
   reproducibles (`dataplatform.utils.dates.ds_add(ds, -1)`). Ojo: en Airflow 3, con un
   `schedule` cron, `ds` es **el día en que corre** (en Airflow 2 era el período anterior):
   para "procesar ayer" usa `ds_add(ds, -1)`. Detalle en
   [08](08-migracion-desde-celery.md#si-además-saltas-de-airflow-2-a-3).
9. **Valida antes de cargar** con `dataplatform.quality.checks`.

## 5. Ejemplos incluidos

| DAG | Qué enseña |
|---|---|
| [`example_etl`](../dags/example_etl/) | ETL completo: config en `files/`, extract → Parquet → resumen CSV → limpieza de staging. Solo primitivos por XCom. Sirve de smoke test. |
| [`example_alerts`](../dags/example_alerts/) | Todas las plantillas de alertas: fallo (email, Slack, Teams, Google Chat, webhook), reintento y éxito de DAG. Falla a propósito. |
| [`example_resource_override`](../dags/example_resource_override/) | Darle 4 CPU / 12 Gi a **una** tarea con `executor_config`, y limitarla con un pool. |
| [`example_kpo`](../dags/example_kpo/) | Un paso en **otra imagen** con `KubernetesPodOperator` (con argumentos y con `pod_template_file` + sidecar), listo para clústeres con y sin RBAC ([14](14-imagenes-dedicadas-kpo.md)). |

### Receta: ETL de base de datos a base de datos

```python
@task.external_python(python=PYTHON_ENV, expect_airflow=True)
def extract(conn_id: str, local_path: str, ds: str | None = None) -> str:
    import polars as pl
    from dataplatform.db.postgres import get_sqlalchemy_engine
    from dataplatform.utils.sql import load_sql

    query = load_sql("sales_daily", "extract", {"ds": ds})
    df = pl.read_database(query, get_sqlalchemy_engine(conn_id))
    path = f"{local_path}/sales_{ds}.parquet"
    df.write_parquet(path)
    return path  # ← la ruta, no el DataFrame


@task.external_python(python=PYTHON_ENV, expect_airflow=True)
def load(parquet_path: str, conn_id: str, ds: str | None = None) -> int:
    import polars as pl
    from dataplatform.db.postgres import copy_csv, run_statement
    from dataplatform.quality.checks import expect, run_checks

    df = pl.read_parquet(parquet_path)
    run_checks(df, [expect.min_rows(1), expect.no_nulls(["sale_id"]), expect.unique(["sale_id"])])
    run_statement(conn_id, "DELETE FROM dw.sales WHERE day = %(ds)s", {"ds": ds})  # idempotente
    csv_path = parquet_path.replace(".parquet", ".csv")
    df.write_csv(csv_path)
    return copy_csv(conn_id, "dw.sales", csv_path)
```

### Receta: tarea con más recursos

```python
from kubernetes.client import models as k8s

BIG = {"pod_override": k8s.V1Pod(spec=k8s.V1PodSpec(containers=[k8s.V1Container(
    name="base", resources=k8s.V1ResourceRequirements(
        requests={"cpu": "2", "memory": "8Gi"}, limits={"cpu": "4", "memory": "16Gi"}))]))}

@task.external_python(python=PYTHON_ENV, executor_config=BIG, pool="heavy_tasks")
def big_join(...): ...
```

## 6. Antes de subir un DAG

```bash
make check-dags         # parsea, resuelve imports de dataplatform/scripts, estructura, dag_id
make test               # si agregaste lógica testeable en scripts/ o libs/
```

`tools/check_dags.py` falla (código 1) si: `_dag.py` no parsea, un import de
`dataplatform.*` o `<dag_id>.scripts.*` no existe, `_dag.py` importa pandas/polars/etc. a
nivel global, o el `dag_id` no coincide con la carpeta. También corre en pre-commit y CI.

Luego: `git pull` en el nodo → el DAG aparece **pausado** en la UI (por
`dags_are_paused_at_creation`) → actívalo.

### Cambiar un DAG que ya está en producción

Los DAGs se leen directo de `dags/` en el disco del nodo, **sin versiones guardadas**. Un
run no queda fijo al código con el que partió: cada tarea carga el archivo tal como esté
**en el momento en que arranca su Pod**. Probado en el laboratorio, eso tiene dos efectos:

| Si el archivo cambia con un run en curso… | Qué pasa con ese run |
|---|---|
| …y el cambio es válido | La tarea que ya corre sigue con el código viejo. Las pendientes usan el **nuevo**, y una tarea agregada **se ejecuta en ese mismo run**. El run mezcla versiones. |
| …y el archivo queda roto (error de sintaxis, import que falla) | El DAG desaparece de la UI (error de importación) y las tareas pendientes **no se programan**: el run queda en `running` sin avanzar, **sin fallar y sin alerta**. Al corregir el archivo se reanuda solo (en segundos). |

Por eso:

1. **Despliega cambios cuando el DAG no tenga runs en curso.** Mira la UI, o
   `GET /api/v2/dags/<dag_id>/dagRuns?state=running`. Si es un DAG largo o frecuente,
   **paúsalo**, espera que termine el run y despliega.
2. **Nunca subas un `_dag.py` sin pasar `make check-dags`**: un archivo roto deja runs
   detenidos sin avisar.
3. Si igual quedó un run mezclado, trátalo como sospechoso: *Clear* del run para
   rehacerlo entero con la versión nueva (la carga debe ser idempotente, regla 4).

## 7. Checklist

- [ ] Lógica en `scripts/`, `_dag.py` solo orquesta
- [ ] Imports de `dataplatform.*`/`scripts/` dentro de las tareas
- [ ] Solo primitivos entre tareas; conexiones por `conn_id`
- [ ] Inputs en `files/<dag_id>/` con permisos `50000:developers`
- [ ] Carga idempotente + checks de calidad
- [ ] Alertas de fallo configuradas
- [ ] `README.md` del DAG completo
- [ ] `make check-dags` sin FAIL
- [ ] Desplegado sin runs en curso del DAG (o con el DAG pausado)
