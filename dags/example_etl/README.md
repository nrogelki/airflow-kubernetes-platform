# example_etl

**Qué hace:** genera ventas sintéticas, las deja en staging como Parquet, las
agrega por región y escribe un CSV de resumen. No depende de sistemas externos:
sirve como **smoke test** de una instalación nueva.

| Campo | Valor |
|---|---|
| Schedule | manual (`None`) |
| Owner | data-team |
| Entorno | `/opt/conda/envs/p313` |
| Connections (`conn_id`) | ninguna |
| Origen → destino | sintético → `files/example_etl/summary_<fecha>.csv` |
| Alertas | comentadas (activar cuando exista `smtp_default`) |

## Flujo de tareas

```
load_config ─► extract ─► transform ─► cleanup
   (dict)       (str: ruta)  (dict)      (list)
```

Solo viajan **primitivos** por XCom: la ruta del Parquet, no el DataFrame.

## Inputs en `files/example_etl/`

- `config.json` — regiones, número de filas y semilla.
