# 10 · Operación y recursos

## 1. Dos archivos, dos comportamientos

| Cambio | Dónde | Aplicar |
|---|---|---|
| `PARALLELISM`, `MAX_ACTIVE_TASKS_PER_DAG` | `platform.env` → `values.yaml` | `make deploy` |
| Recursos de scheduler/api-server/etc. | `helm/values.template.yaml` | `make deploy` |
| Recursos / deadline del Pod de tarea | `platform.env` → `pod_template.yaml` | `make render && make restart-scheduler` |
| Un DAG, una librería de `libs/`, un input de `files/` | el archivo | nada (hostPath) |
| Librerías de datos | `envs/p313/environment.yml` | `make conda-env` |
| Dependencias de la imagen | `docker/airflow/requirements.txt` + tag nuevo | `make build deploy` |

## 2. Concurrencia

```
PARALLELISM=5                 # tareas simultáneas en TODO Airflow = Pods de tarea máximos
MAX_ACTIVE_TASKS_PER_DAG=2    # por DAG: ningún DAG acapara todos los slots
```

Con 5 y 2: DAG A toma 2 slots, DAG B 2, queda 1 para un tercero. Para garantizar reparto
en familias de tareas críticas o limitar el acceso a un sistema frágil (una base que no
aguanta 5 conexiones), usa **pools**:

```bash
airflow pools set db_legacy 2 "Máx. 2 tareas contra la base legacy"
```

```python
@task.external_python(python=PYTHON_ENV, pool="db_legacy")
```

## 3. Dimensionamiento

**Presupuesto de memoria** (ejemplo 64 GB, defaults):

| | Requests | Limits (peor caso) |
|---|---|---|
| Componentes fijos (5) | ~3 GB | ~6.5 GB |
| 5 Pods de tarea × 512Mi / 8Gi | 2.5 GB | 40 GB |
| **Total** | **~5.5 GB** | **~46.5 GB** |

- `requests` es lo que Kubernetes **reserva** para agendar: mantenlo bajo.
- `limits` es el **techo**: el riesgo real es que muchas tareas lo alcancen a la vez.
  Regla práctica: `PARALLELISM × WORKER_MEMORY_LIMIT + 6.5 GB < RAM del nodo`.
- Tareas excepcionales: `executor_config` por tarea, no subir el default.

| Nodo | `PARALLELISM` | `WORKER_MEMORY_LIMIT` |
|---|---|---|
| 16 GB / 4 cores | 3 | 3Gi |
| 32 GB / 8 cores | 5 | 4Gi |
| 64 GB / 8–16 cores | 5–8 | 6–8Gi |

`WORKER_ACTIVE_DEADLINE_SECONDS` (default 90 min) mata Pods colgados. Si tienes tareas
legítimamente más largas, súbelo o dales `executor_config` con su propio deadline.

## 4. Monitoreo y diagnóstico

Los comandos usan `kubectl`: en MicroK8s es `microk8s kubectl`, o el alias que crea la
instalación ([03](03-instalacion-desde-cero.md): `alias kubectl='microk8s kubectl'`). En Pods
con varios contenedores (scheduler, dag-processor, triggerer), `logs` usa el principal; para
otro, agrega `-c <contenedor>`.

```bash
# Panorama
kubectl get pods -n airflow -o wide
kubectl get pods -n airflow -w                         # en vivo

# ¿Por qué falló / se reinicia?
kubectl logs <pod> -n airflow --tail=200
kubectl logs <pod> -n airflow -p                       # intento anterior (crash)
kubectl describe pod <pod> -n airflow                  # Last State / Events

# Línea de tiempo (los eventos viven ~1 h)
kubectl get events -n airflow --sort-by=.lastTimestamp
kubectl get events -n airflow --field-selector type=Warning

# Recursos (addon metrics-server)
kubectl top pods -n airflow
kubectl top nodes
kubectl describe node | grep -A6 Conditions            # DiskPressure / MemoryPressure

# Airflow CLI (dentro del scheduler: de a UN comando a la vez, ver nota abajo)
make shell
airflow dags list-import-errors
airflow dags list-runs <dag_id>                        # en Airflow 3 el dag_id va sin -d
airflow tasks states-for-dag-run <dag_id> <run_id>
airflow db check
```

> Cada comando `airflow ...` que corres dentro del scheduler (`make shell`, `kubectl exec ...
> airflow ...`) levanta otro proceso con Airflow completo y usa memoria **del contenedor del
> scheduler**. Por eso su límite es 2 GiB: con 1 GiB, un solo comando llegó al tope y
> Kubernetes mató al **scheduler** (`OOMKilled`). Corre los comandos de a uno.

| STATUS del Pod | Mirar |
|---|---|
| `Pending` / `ContainerCreating` | `describe` → Events (recursos, hostPath, imagen, CNI) |
| `CrashLoopBackOff` / `Error` | `logs -p` |
| `OOMKilled` | subir límite o procesar por lotes |
| `Evicted` | disco/memoria del nodo |
| `ErrImageNeverPull` | `make build` |

## 5. Backups

Lo que **no** está en git y hay que respaldar:

| Qué | Cómo |
|---|---|
| Metadata DB (Connections cifradas, Variables, historial) | `pg_dump` periódico |
| `config/platform.env` (secret key) | gestor de secretos |
| Connections/Variables en claro (para DR) | `airflow connections export` → gestor de secretos |
| Inputs de `files/` no versionados | backup del filesystem |

```bash
PG=$(kubectl get pods -n airflow -l app.kubernetes.io/name=postgresql -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n airflow "$PG" -- bash -c 'PGPASSWORD=$POSTGRES_PASSWORD pg_dump -U postgres postgres' \
  | gzip > "airflow-metadata-$(date +%F).sql.gz"
```

> La Connection se cifra con la **Fernet key** que genera el chart (Secret
> `<release>-fernet-key`). Sin ella, un backup de la DB no descifra las Connections:
> respáldala también (`kubectl get secret airflow-fernet-key -n airflow -o yaml`).

Prueba la restauración al menos una vez. El DR completo es: reinstalar con el runbook
[03](03-instalacion-desde-cero.md) + restaurar la DB (o reimportar Connections).

## 6. Actualizaciones

| Componente | Cómo |
|---|---|
| DAGs / libs | `git pull` en el nodo |
| Librerías de datos | `environment.yml` → `make conda-env` → commit de `environment.yml` + `environment.lock.yml` |
| Airflow (minor/patch) | leer release notes → `AIRFLOW_VERSION` + `AIRFLOW_IMAGE_TAG` nuevos + `apache-airflow==` en `environment.yml` → `make build` → `make conda-env` → `make deploy` (el chart corre las migraciones) |
| Chart | fija `AIRFLOW_CHART_VERSION` nueva → `make deploy-dry-run` → `make deploy` |
| MicroK8s | planificado: `snap refresh microk8s --channel=1.36/stable`, probar, volver a `--hold` |

**Siempre** con backup de la DB previo y en ventana de mantenimiento: es un solo nodo.

## 7. Auto-sanación

Ver [01 §6](01-arquitectura.md#6-auto-sanación). Estado:

```bash
kubectl get cronjobs -A | grep -E "pod-cleaner|calico-watchdog"
kubectl logs -n kube-system -l app=calico-watchdog --tail=20
```

Para probar el watchdog sin riesgo, edita el CronJob y pon `DRY_RUN: "1"`.
