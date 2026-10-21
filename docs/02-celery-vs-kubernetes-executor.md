# 02 · CeleryExecutor vs KubernetesExecutor

## Cómo funciona cada uno

Con CeleryExecutor hay **N workers de larga vida** (contenedores o procesos) que toman
tareas de una cola en Redis/RabbitMQ. Cada worker ejecuta varias tareas a la vez
(`worker_concurrency`) **en el mismo proceso/contenedor**. Es un modelo probado y eficiente,
con algunas limitaciones de diseño:

- **Recursos compartidos.** Las tareas de un mismo worker comparten su RAM y CPU. Los
  recursos se definen por worker, no por tarea: si una tarea necesita mucho más que las
  demás, hay que dimensionar el worker (o una cola dedicada) para ese caso.
- **Dependencias compartidas.** Todas las tareas usan el entorno Python del worker;
  actualizar una librería para un DAG afecta a todos los demás, y a Airflow.
- **Estado entre tareas.** El proceso del worker sobrevive a las tareas: lo que una tarea
  deja cargado (módulos, cachés, conexiones) sigue ahí para la siguiente.
- **Más piezas que operar.** Broker, workers, Flower, *visibility timeouts*, colas.

## Qué cambia con KubernetesExecutor

| Aspecto | CeleryExecutor | KubernetesExecutor (esta plataforma) |
|---|---|---|
| Unidad de ejecución | Slot dentro de un worker compartido | **Un Pod por tarea** |
| Aislamiento de recursos | Por worker (sus tareas comparten RAM/CPU) | `requests`/`limits` por Pod (cgroups) |
| Si una tarea excede su memoria | Afecta al proceso del worker que la ejecuta | `OOMKilled` solo esa tarea; Airflow reintenta |
| Estado residual | Vive mientras viva el worker | Nulo: el Pod se destruye |
| Recursos distintos por tarea | Colas + pools de workers distintos | `executor_config` en la propia tarea |
| Dependencias | Entorno del worker | Imagen mínima + entorno aislado montado |
| Componentes extra | Broker + workers + Flower | Ninguno |
| Capacidad ociosa | Workers encendidos aunque no haya trabajo | Cero Pods cuando no hay tareas |

## El costo (honesto)

- **Latencia de arranque por tarea**: cada tarea espera a que se cree su Pod y arranque
  Airflow dentro. Medido en esta plataforma, desde que la tarea entra en cola hasta que
  empieza a correr: **mediana ~5 s** (casi siempre entre 3 y 10 s; una tarea
  `KubernetesPodOperator` más, porque arranca un segundo Pod). Depende del servidor.
  Irrelevante para ETLs de minutos; **malo para miles de tareas de 1 segundo**.
- **Requiere entender Kubernetes lo mínimo** (`kubectl get pods`, `describe`, `logs`).
  El archivo [10-operacion-y-recursos.md](10-operacion-y-recursos.md) incluye una guía rápida con los comandos esenciales.
- **Sin *warm workers***: no hay caché en memoria entre tareas.

## ¿Cuándo NO migrar?

- La mayoría de tus tareas duran < 10 s y son miles por hora → Celery (o
  `CeleryKubernetesExecutor` / *multiple executors* de Airflow 3 para mezclar).
- No tienes a nadie dispuesto a operar Kubernetes, aunque sea un nodo.
- Tus tareas ya delegan todo a sistemas externos (Spark, BigQuery, dbt Cloud) y los
  workers casi no consumen recursos: Celery te sirve igual de bien.

## ¿Cuándo sí?

- ETLs en Python (pandas/polars) de minutos a horas, con consumos de memoria muy
  distintos entre sí.
- Quieres fijar CPU/RAM **por tarea** en vez de dimensionar workers para el caso más pesado.
- Varios equipos o DAGs con dependencias incompatibles compartiendo un Airflow.
- Prefieres operar menos componentes (sin broker ni workers fijos) en un servidor propio.

Para migrar: [08-migracion-desde-celery.md](08-migracion-desde-celery.md).
