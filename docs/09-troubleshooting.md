# 09 · Troubleshooting

Primero: `make doctor` y `kubectl get pods -n airflow`. Luego busca el síntoma aquí.

## Índice rápido

| Síntoma | Sección |
|---|---|
| El clúster "se reinicia solo"; Airflow cae 1–3 min | [Reinicios por redes de Docker](#reinicios-por-redes-de-docker) |
| La pestaña Logs sale vacía | [Logs vacíos en la UI](#logs-vacíos-en-la-ui) |
| Loop de `401 Unauthorized` | [401 en bucle](#401-en-bucle) |
| Redirecciones infinitas / errores CSRF | [Redirects y CSRF](#redirects-y-csrf) |
| `dag-processor` en `CrashLoopBackOff` | [dag-processor inestable](#dag-processor-inestable) |
| Pods nuevos en `ContainerCreating` para siempre, Calico `Unauthorized` | [Calico sin token](#calico-sin-token) |
| `ErrImageNeverPull` / `ImagePullBackOff` | [Imagen no encontrada](#imagen-no-encontrada) |
| `hostPath type check failed` | [Carpeta montada inexistente](#carpeta-montada-inexistente) |
| `PermissionError` en `files/` | [06-files-y-permisos.md](06-files-y-permisos.md) |
| `ModuleNotFoundError` | [07-entornos-virtuales.md §5](07-entornos-virtuales.md#5-errores-típicos) |
| Tareas `OOMKilled` | [Memoria](#oomkilled) |
| El DAG no aparece en la UI | [DAG no aparece](#el-dag-no-aparece) |
| El scheduler se reinicia (`OOMKilled`) al usar `make shell` o `kubectl exec ... airflow` | [Scheduler OOMKilled por la CLI](#scheduler-oomkilled-por-la-cli) |
| Run en `running` que no avanza; tareas sin estado | [Run detenido tras editar el DAG](#run-detenido-tras-editar-el-dag) |
| Pods `Evicted`, nodo `NotReady` | [Disco lleno](#disco-lleno) |

---

## Reinicios por redes de Docker

**Síntoma.** Si el nodo también corre Docker, cada `docker compose up/down` o
`docker network create/rm` reinicia kubelite y containerd: todos los Pods caen.

**Causa.** El daemon `apiserver-kicker` de MicroK8s compara cada 5 s las IPs del host
(`hostname -I`) contra las del certificado del API server. No excluye las *bridges* de
Docker (`docker0`, `br-*`): al crearse/destruirse una red cree que cambió la IP del nodo,
regenera certificados y mata los procesos del plano de control.

**Fix** (`make install-microk8s ARGS="--docker-fix"` lo aplica):

```bash
echo '--advertise-address=0.0.0.0' | sudo tee -a /var/snap/microk8s/current/args/kube-apiserver
sudo snap restart microk8s
```

**Implicancias.**
- Sobrevive a `snap refresh` (vive en `SNAP_DATA`).
- El kicker ya no reacciona a cambios de IP **reales**. Si cambias la IP del nodo:
  quita la línea, `snap restart microk8s`, espera `Ready`, regenera `~/.kube/config`
  (`microk8s config > ~/.kube/config`) y vuelve a agregarla. Actualiza también `SERVER_IP`
  y `make deploy`.
- **Incompatible con clúster HA multinodo** (rompe `microk8s join`, issue
  [canonical/microk8s#3785](https://github.com/canonical/microk8s/issues/3785)).
  Ver [11-single-node.md](11-single-node.md).

**Verificar:** `docker network create t && docker network rm t` y comprobar en
`journalctl -u snap.microk8s.daemon-apiserver-kicker` que no aparezca `cert change detected`.

## Logs vacíos en la UI

**Causa.** Los Pods de tarea escriben en `logs/` del nodo, pero quien los *lee* para la
UI es el **API Server**. Si no monta `logs/`, busca en una carpeta vacía.

**Fix.** Ya incluido en `values.template.yaml` (`apiServer.extraVolumes: logs`). Si lo
quitaste, restáuralo y `make deploy`. Verifica que `logs/` sea de UID 50000.

## 401 en bucle

Varios workers de API con estado de sesión propio. `config.api.workers: "1"`
([04 §3.2](04-configuracion.md#32-apiworkers-1--evita-el-loop-de-401-unauthorized)).
Limpia cookies del navegador tras aplicar.

## Redirects y CSRF

- Falta o está mal `api.base_url` → debe ser exactamente `http://SERVER_IP:NODE_PORT`.
- La secret key difiere entre los tres lugares o cambió en un upgrade → no la edites a
  mano en `values.yaml`; está en `platform.env` y `make render` la replica.

## dag-processor inestable

`CrashLoopBackOff` o `exit code 137`:
1. `kubectl logs -n airflow deploy/airflow-dag-processor -p`
2. ¿`OOMKilled`? Sube `dagProcessor.resources.limits.memory`.
3. ¿Timeouts de probe al parsear? Ya vienen relajados; revisa si algún `_dag.py` hace
   trabajo en parse-time (consultas, lecturas grandes, imports pesados). `make check-dags`
   detecta imports pesados globales.
4. Confirma `mp_start_method: spawn`.

## Calico sin token

**Síntoma:** `Failed to create pod sandbox: plugin type="calico" failed (add): error
getting ClusterInformation: connection is unauthorized: Unauthorized`.

**Causa:** el token de ServiceAccount del CNI expiró y no se renovó (conocido en MicroK8s
tras rotaciones de certificados o reloj desincronizado).

**Fix manual:** `kubectl rollout restart daemonset/calico-node -n kube-system`.
**Automático:** el CronJob `calico-watchdog` (`make cronjobs`). Revisa también NTP.

## Imagen no encontrada

`ErrImageNeverPull`: la imagen no está en el containerd de MicroK8s (se construyó en
Docker pero no se importó, o el kubelet la borró por GC).

```bash
sudo microk8s ctr images ls | grep airflow-k8s-base
make build                                  # la reimporta
```

Si se repite, aplica `--image-gc` ([03 §2](03-instalacion-desde-cero.md#2-microk8s-versión-fijada)).
El tag del `pod_template` y de `values.yaml` deben coincidir (`make render`).

## Carpeta montada inexistente

`MountVolume.SetUp failed ... hostPath type check failed: <ruta> is not a directory`.
Los volúmenes usan `type: Directory`: si la carpeta no existe en el nodo, el Pod no
arranca. `make bootstrap` (y para el entorno: `make conda-env`). Revisa que
`PROJECT_PATH` sea la ruta real del clon.

## OOMKilled

`kubectl describe pod <pod> -n airflow` → `Last State: Terminated, Reason: OOMKilled`.

1. ¿Es una tarea puntual? `executor_config` solo para ella
   ([05](05-desarrollo-de-dags.md#receta-tarea-con-más-recursos)).
2. ¿Carga todo en memoria? Procesa por lotes, usa `polars.scan_*` (lazy) o
   `read_database(..., iter_batches=True)`.
3. ¿Son todas? Sube `WORKER_MEMORY_LIMIT` (sin superar lo que el nodo aguanta con
   `PARALLELISM` tareas simultáneas: ver [10](10-operacion-y-recursos.md)).

## Scheduler OOMKilled por la CLI

**Síntoma:** el scheduler aparece con `RESTARTS` > 0 y
`kubectl describe pod <scheduler> -n airflow` muestra `Last State: Terminated, Reason:
OOMKilled` justo después de correr comandos `airflow ...` dentro de él.

**Causa:** cada comando de la CLI es otro proceso con Airflow completo dentro del mismo
contenedor. El scheduler solo ya usa ~570 MiB; con un límite de 1 GiB, un comando basta para
llegar al tope y Kubernetes mata al proceso más grande: el scheduler.

**Solución:** límite de memoria del scheduler en `2Gi` (`helm/values.template.yaml`, ya es
el valor de esta plantilla; si tu instalación es anterior, súbelo y `make deploy`). Probado:
tres comandos en paralelo dejan el pico en ~900 MiB. Igual, corre los comandos de a uno.

## El DAG no aparece

1. `make check-dags` — ¿parsea?
2. Errores de importación: banner rojo en la UI, o
   `kubectl exec -n airflow deploy/airflow-scheduler -c scheduler -- airflow dags list-import-errors`
3. ¿Está en `dags/<dag_id>/_dag.py` y no dentro de `scripts/` (ignorado)?
4. Espera el intervalo de escaneo del dag-processor (~5 min para carpetas nuevas) o
   `make restart-scheduler`.

## Run detenido tras editar el DAG

**Síntoma:** un run sigue en `running`, pero sus tareas siguientes quedan sin estado y no
aparecen Pods nuevos. No hay fallo ni alerta. En la UI el DAG desapareció o hay un banner
rojo de errores de importación.

**Causa:** el `_dag.py` se editó durante el run y quedó roto. El dag-processor marca el DAG
como `stale` y el scheduler deja de programar sus tareas pendientes.

**Solución:** corrige el archivo (`make check-dags`). En segundos el DAG vuelve y el run se
reanuda solo desde donde quedó. Las tareas que faltaban corren con el código corregido:
si el cambio altera la lógica, haz *Clear* del run completo. Prevención:
[05 §6](05-desarrollo-de-dags.md#cambiar-un-dag-que-ya-está-en-producción).

## Disco lleno

`DiskPressure: True` en `kubectl describe node` → expulsión de Pods.

```bash
df -h /
sudo du -sh /var/snap/microk8s/common/ logs/ files/
```

Limpia logs viejos (`find logs/ -type f -mtime +30 -delete`) o configura la limpieza de
logs del chart; elimina imágenes viejas de containerd
(`sudo microk8s ctr images rm <ref>`); revisa staging acumulado en `files/`.

---

## Kit de diagnóstico

```bash
kubectl get pods -n airflow                         # panorama
kubectl describe pod <pod> -n airflow               # Events: por qué no arranca
kubectl logs <pod> -n airflow -p                    # logs del intento anterior (crash)
kubectl get events -n airflow --sort-by=.lastTimestamp | tail -30
kubectl top pods -n airflow ; kubectl top nodes     # consumo en vivo
```

Más en [10-operacion-y-recursos.md](10-operacion-y-recursos.md#4-monitoreo-y-diagnóstico).
