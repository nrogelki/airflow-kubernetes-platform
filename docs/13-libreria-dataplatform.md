# 13 · Librería `dataplatform`

Building blocks reutilizables en [`libs/dataplatform/`](../libs/dataplatform/),
importables desde cualquier DAG gracias al PYTHONPATH
([05 §2](05-desarrollo-de-dags.md#2-pythonpath-la-pieza-que-lo-simplifica-todo)).
Todos tienen tests en [`tests/`](../tests/).

| Módulo | Para qué | Dependencias | ¿Parse-time seguro? |
|---|---|---|---|
| `alerts.email_alerts` | Email HTML de fallo | stdlib (+ provider SMTP al enviar) | ✅ |
| `alerts.webhooks` | Slack, Teams, Google Chat, webhook genérico | stdlib | ✅ |
| `alerts.base` | `AlertInfo` + texto común para crear plantillas propias | stdlib | ✅ |
| `utils.local_files` | Rutas de `files/<dag_id>`, leer JSON, limpiar staging | stdlib | ✅ |
| `utils.dates` | `ds_add`, rangos, límites de mes, rutas particionadas | stdlib | ✅ |
| `utils.retry` | Decorador de reintentos con backoff exponencial + jitter | stdlib | ✅ |
| `utils.sql` | Cargar `.sql` de `dags/<id>/sql/` con parámetros validados | stdlib | ✅ |
| `utils.dataframes` | snake_case de columnas, rename estricto, cast de esquema | polars | ❌ (solo en tareas) |
| `quality.checks` | Gate de calidad de datos antes de cargar | polars (df) | ❌ |
| `db.postgres` | `run_statement`, `get_sqlalchemy_engine`, `copy_csv` (COPY) | provider postgres, sqlalchemy | ❌ |
| `transfers.sftp` | Listar/descargar por patrón, subir | provider sftp | ❌ |

"Parse-time seguro" = se puede importar a nivel global en un `_dag.py`. Los demás,
**solo dentro** de tareas `@task.external_python`.

## Ejemplos

### Fechas

```python
from dataplatform.utils.dates import ds_add, date_range, month_bounds, partition_path

ds_add("2026-03-01", -1)  # "2026-02-28"  -> "el día anterior al logical date"
list(date_range("2026-01-30", "2026-02-01"))  # ["2026-01-30", "2026-01-31", "2026-02-01"]
month_bounds("2024-02-10")  # ("2024-02-01", "2024-02-29")
partition_path("s3://lake/sales", "2026-03-01")  # ".../year=2026/month=03/day=01"
```

### Reintentos de una llamada puntual

```python
from dataplatform.utils.retry import retry


@retry(times=4, backoff_seconds=2, exceptions=(TimeoutError, ConnectionError))
def fetch_page(url): ...
```

Usa `retries` de Airflow para fallos de la tarea completa; `@retry` para una llamada
dentro de una tarea cara de repetir.

### SQL en archivos

```sql
-- dags/sales_daily/sql/delete_day.sql
DELETE FROM $table WHERE day = '$ds';
```

```python
from dataplatform.utils.sql import load_sql

sql = load_sql("sales_daily", "delete_day", {"table": "dw.sales", "ds": ds})
```

Los parámetros se validan contra caracteres peligrosos (`;`, comillas). Son para
**identificadores y fechas que tú controlas**; para valores que vienen de fuera usa
*bind parameters* del driver (`run_statement(conn_id, sql, {"x": valor})`).

### DataFrames

```python
from dataplatform.utils.dataframes import normalize_columns, apply_rename, cast_schema

df = normalize_columns(df)  # "Tráfico Total (GB)" -> "trafico_total_gb"
df = apply_rename(df, read_json(local_path, "rename.json"))  # falla si falta una columna
df = cast_schema(df, {"units": "int", "day": "date", "price": "float"})
```

### Calidad de datos

```python
from dataplatform.quality.checks import expect, run_checks

run_checks(
    df,
    [
        expect.min_rows(1),
        expect.columns(["sale_id", "day", "amount"]),
        expect.no_nulls(["sale_id"]),
        expect.unique(["sale_id"]),
        expect.between("amount", 0, 1_000_000),
    ],
)
# [PASS]/[FAIL] por check en el log; DataQualityError con el resumen si algo falla
```

### Postgres

```python
from dataplatform.db.postgres import run_statement, get_sqlalchemy_engine, copy_csv

run_statement("dw_postgres", "DELETE FROM dw.sales WHERE day = %(ds)s", {"ds": ds})
engine = get_sqlalchemy_engine("dw_postgres")  # para polars/pandas read/write
rows = copy_csv("dw_postgres", "dw.sales", "/opt/airflow/files/sales_daily/sales.csv")
```

### SFTP

```python
from dataplatform.transfers.sftp import download_matching

paths = download_matching("vendor_sftp", "/outbound", f"report_{ds}*.csv", "/opt/airflow/files/vendor_reports")
```

## Agregar un módulo

1. Solo si **dos o más DAGs** lo necesitan (si no, va en `dags/<id>/scripts/`).
2. Agnóstico del negocio: nada de nombres de tablas o reportes concretos.
3. Imports de terceros **perezosos** (dentro de funciones) si el módulo podría
   importarse en parse-time; globales si solo corre en tareas.
4. Si el módulo se importa al parsear (como `alerts`), compatible con Python 3.12 (la
   imagen); el resto solo corre en el entorno (3.13).
5. Tests en `tests/` (funciones puras sin Airflow cuando sea posible).
6. Documéntalo en esta página.
