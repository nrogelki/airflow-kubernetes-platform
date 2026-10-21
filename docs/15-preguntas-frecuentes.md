# 15 · Preguntas frecuentes

## Sobre la plataforma

**¿Necesito saber Kubernetes para usarla?**
Para *escribir DAGs*, no: se trabaja con archivos Python y carpetas. Para *operarla*
basta con lo básico (`kubectl get pods`, `describe`, `logs`), que está resumido en
[10 §4](10-operacion-y-recursos.md#4-monitoreo-y-diagnóstico). El vocabulario está en
[00-conceptos-clave.md](00-conceptos-clave.md).

**¿Por qué MicroK8s y no Docker Compose?**
Docker Compose con Airflow implica CeleryExecutor y workers fijos que comparten recursos
y entorno entre tareas; esta plataforma busca justamente un Pod aislado por tarea, y para
eso necesita Kubernetes. MicroK8s lo entrega completo en un solo servidor, instalado con
un comando.
Ver [02](02-celery-vs-kubernetes-executor.md).

**¿Funciona con otro Kubernetes (k3s, EKS, GKE)?**
No está probado: la plataforma se validó solo en MicroK8s 1.35 de **un nodo**. Lo
específico de MicroK8s está en `scripts/install_microk8s.sh`, `scripts/build_image.sh`
(import a containerd) y `STORAGE_CLASS`. Con varios nodos, además, el `hostPath` deja de
servir: multinodo queda fuera del alcance de esta plantilla
([11](11-single-node.md#3-es-suficiente-para-mí)).

**¿Cuántos DAGs aguanta?**
El límite práctico lo pone cuántas tareas **simultáneas** caben en la RAM del servidor,
no la cantidad de DAGs. Ver [10 §3](10-operacion-y-recursos.md#3-dimensionamiento).

**¿Es seguro para producción?**
Es la versión genérica de una instalación productiva. Revisa las implicancias de un solo
nodo ([11](11-single-node.md)), protege la UI (red interna o TLS) y programa backups
([10 §5](10-operacion-y-recursos.md#5-backups)).

## Sobre los DAGs

**¿Por qué los imports van dentro de las funciones?**
Por dos razones. `@task.external_python` envía **solo el código de la función** a otro
intérprete, así que lo importado fuera no viaja. Además, todo lo que está arriba del
`_dag.py` se ejecuta cada vez que Airflow lee el archivo, y lo hace con las librerías de la
**imagen** de Airflow, no con las del entorno `p313` (pueden no estar, o estar en otra
versión). Ver [05 §3](05-desarrollo-de-dags.md#3-los-tres-patrones-de-import).

**¿Cuándo uso `@task` normal y cuándo `@task.external_python`?**
`@task` sirve para lógica liviana de orquestación con la librería estándar (armar una
lista, decidir una rama). Todo lo que use librerías de datos, drivers o procese archivos
va con `@task.external_python`.

**¿Por qué no puedo pasar un DataFrame entre tareas?**
Cada tarea corre en un Pod distinto, posiblemente minutos después, y XCom guarda los
valores en la base de datos de Airflow, que no está hecha para datos masivos. Guárdalo
como archivo (Parquet o CSV) en `files/<dag_id>/` y pasa la ruta. Cuál conviene:
[05 §4](05-desarrollo-de-dags.md#4-reglas-de-oro).

**¿Dónde pongo una función: `scripts/` o `libs/`?**
Si la usa un solo DAG, va en `dags/<dag_id>/scripts/`. Si la usan dos o más, va en
`libs/dataplatform/`. No la promuevas "por si acaso".

**Hice un cambio y no se ve en la UI.**
El DAG Processor relee los archivos cada pocos minutos. Si pasan más de 5, revisa los
errores de importación (banner rojo en la UI) y ejecuta `make check-dags`. Ver
[09](09-troubleshooting.md#el-dag-no-aparece).

**¿Puedo cambiar un DAG mientras está corriendo?**
Mejor no. Airflow no guarda versiones de los archivos de `dags/`: las tareas que faltan
del run en curso usan el código **nuevo** (incluso una tarea recién agregada se ejecuta en
ese run), y si el archivo queda roto el run se queda en `running` sin avanzar ni avisar
hasta que lo corrijas. Despliega con el DAG sin runs en curso o pausado. Ver
[05 §6](05-desarrollo-de-dags.md#cambiar-un-dag-que-ya-está-en-producción).

**¿Cómo pruebo mi lógica sin Airflow?**
Las funciones de `scripts/` y `libs/` son Python normal: escribe un test en `tests/`
(mira `tests/test_example_etl.py`) y ejecuta `make test`.

**¿Cómo reproceso un día?**
Desde la UI: *Trigger DAG* con una fecha lógica concreta, o *Clear* sobre la corrida de
ese día. Funciona bien si tu carga es idempotente (borra el día antes de insertarlo).

## Sobre recursos

**Una tarea muere con `OOMKilled`. ¿Subo la memoria de todas?**
No. Dale más recursos solo a esa tarea con `executor_config`
([05](05-desarrollo-de-dags.md#receta-tarea-con-más-recursos)) o procésala por partes.

**¿Qué diferencia hay entre `requests` y `limits`?**
`requests` es lo que Kubernetes **reserva** para decidir si el Pod cabe. `limits` es el
**máximo** que puede usar antes de que lo maten. Conviene tener requests bajos y limits
generosos.

**¿Qué pasa si se reinicia el servidor?**
Las tareas en curso se pierden y Airflow las reintenta al volver, según `retries`.
Ver [11 §2](11-single-node.md#qué-pasa-con-las-tareas-si-el-nodo-se-reinicia).

## Sobre entornos y dependencias

**Necesito una librería nueva. ¿La agrego al Dockerfile?**
No. Va en `envs/p313/environment.yml` (con versión exacta), seguida de `make conda-env`
y un commit de `environment.yml` + `environment.lock.yml`. El Dockerfile
es solo para Airflow y sus providers. Ver [07](07-entornos-virtuales.md).

**¿Por qué Conda y no un `venv` normal?**
Un `venv` apunta al Python del servidor, que no existe dentro del contenedor. Un entorno
Conda trae su propio Python y funciona montado en cualquier Pod.

**El entorno quedó con paquetes corruptos.**
Ejecuta `make repair-env`: reinstala todo exactamente en las versiones del lock, sin
cambiar ninguna.

## Sobre alertas

**Configuré `smtp_default` y no llegan los correos.**
El error más común es usar el puerto 587 sin `"disable_ssl": true` en el Extra. Revisa el
log de la tarea: la plantilla registra el motivo exacto. Ver
[12 §3](12-alertas.md#3-cómo-interpreta-airflow-la-conexión-de-correo-smtp_default).

**¿Por qué no uso `email_on_failure=True`?**
Porque lee la configuración SMTP del proceso local, y los Pods efímeros no la tienen. La
plantilla usa la Connection, que funciona desde cualquier Pod.

**¿Si falla la alerta, falla la tarea?**
No. Las plantillas registran el error en el log y nunca lanzan excepción.
