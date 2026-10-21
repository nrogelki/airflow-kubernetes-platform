# 03 · Instalación desde cero (runbook)

Guía secuencial para levantar la plataforma en un servidor **vacío**. Cada paso deja
listo lo que necesita el siguiente: **ejecútalos en orden**. Todos los scripts son
idempotentes (puedes repetirlos sin romper nada).

```
 0. Requisitos          1. Clonar y configurar     2. MicroK8s        3. Acceso developers
 4. Helm                5. Bootstrap del host      6. Entorno p313    7. Imagen
 8. Render + deploy     9. Primer acceso a la UI  10. Connections    11. Smoke test
12. CronJobs           13. Checklist final
```

---

## 0. Requisitos

| Recurso | Mínimo | Recomendado |
|---|---|---|
| SO | Ubuntu 22.04 / 24.04 (x86_64; el lock de `p313` es linux-64) | Ubuntu Server LTS |
| CPU / RAM | 4 cores / 16 GB | 8+ cores / 32–64 GB |
| Disco | 60 GB libres | SSD, con alertas de uso |
| Red | **IP fija** | + NTP activo |

> **NTP no es opcional.** Un reloj desincronizado produce errores `Unauthorized` en
> Calico y certificados "no válidos todavía".

```bash
sudo apt-get update
sudo apt-get install -y git make curl openssl gettext-base snapd docker.io
timedatectl status          # "System clock synchronized: yes"
```

`gettext-base` provee `envsubst` (render de plantillas). `docker.io` solo se usa para
**construir** la imagen; MicroK8s la ejecuta con su propio containerd.

Crea el usuario dueño del proyecto (si no existe):

```bash
id airflow-admin || sudo adduser --disabled-password --gecos "" airflow-admin
sudo usermod -aG docker "$USER"      # quien construya imágenes
```

## 1. Clonar y configurar

Clona **en la ruta definitiva**: los volúmenes `hostPath` apuntarán a ella.

```bash
sudo mkdir -p /opt/airflow-platform
sudo chown "$USER" /opt/airflow-platform
git clone https://github.com/nrogelki/airflow-kubernetes-platform.git /opt/airflow-platform
cd /opt/airflow-platform

make init                    # crea config/platform.env (ignorado por git)
nano config/platform.env
```

Como mínimo revisa: `PROJECT_PATH` (= la ruta del clon), `PROJECT_OWNER`, `SERVER_IP`
(o déjalo vacío para autodetectar), `NODE_PORT` y `ALERT_TIMEZONE`. Todas las variables
están explicadas en [04-configuracion.md](04-configuracion.md).

## 2. MicroK8s (versión fijada)

```bash
make install-microk8s                         # sin Docker standalone en el nodo
make install-microk8s ARGS="--docker-fix"     # si el nodo TAMBIÉN corre Docker (lo normal si construyes aquí)
make install-microk8s ARGS="--docker-fix --image-gc"   # + protege la imagen local del GC
```

Qué hace [`scripts/install_microk8s.sh`](../scripts/install_microk8s.sh):

1. Instala MicroK8s del canal `1.35/stable` y **congela** las actualizaciones
   (`snap refresh --hold`). Un salto de versión automático puede romper Calico o el chart.
2. Habilita `dns`, `hostpath-storage`, `rbac` y `metrics-server` (la lista está en
   `scripts/install_microk8s.sh`, en la línea `for addon in dns hostpath-storage rbac metrics-server`).

   > **RBAC (los permisos de Kubernetes) queda ACTIVADO por defecto.** Para el uso normal
   > no cambia nada: los componentes de Airflow y los CronJobs traen sus propios permisos,
   > y las tareas `@task` / `@task.external_python` no hablan con la API de Kubernetes.
   >
   > Lo único que lo nota son las tareas con **`KubernetesPodOperator` (KPO)**, las que
   > corren un paso en otra imagen: para crear su Pod necesitan permiso, y con RBAC
   > activado no lo tienen salvo que se lo des. Hay dos caminos:
   >
   > | | Qué haces | Dónde se configura | Efecto |
   > |---|---|---|---|
   > | **A. Mantener RBAC** (recomendado) | Agregas `executor_config=KPO_LAUNCHER` a cada tarea KPO | En el **DAG**, en la propia tarea. Copia `KPO_LAUNCHER` de [`dags/example_kpo/_dag.py`](../dags/example_kpo/_dag.py) | Solo esas tareas pueden crear Pods; el resto del clúster sigue protegido |
   > | **B. Desactivar RBAC** (más simple) | Nada en los DAGs | Antes de instalar: quita `rbac` de la lista en `scripts/install_microk8s.sh`. Con el clúster ya instalado: `sudo microk8s disable rbac` | Las KPO funcionan sin configurar nada, pero **cualquier tarea puede hacer cualquier cosa** en el clúster (leer Secrets, borrar Pods de Airflow) |
   >
   > Si eliges B y algún día vuelves a activar RBAC, antes agrega `KPO_LAUNCHER` a las
   > tareas KPO o fallarán con `403 Forbidden`. Detalle y pruebas:
   > [14 §3](14-imagenes-dedicadas-kpo.md#3-permisos-con-rbac-y-sin-rbac).
3. `--docker-fix`: agrega `--advertise-address=0.0.0.0` al API server. **Sin esto, cada
   `docker network create/rm` reinicia todo el plano de control** (y Airflow cae 1–3 min).
   Explicación en [09-troubleshooting.md](09-troubleshooting.md#reinicios-por-redes-de-docker).
4. `--image-gc`: sube los umbrales de *image garbage collection* a 95/90. Con
   KubernetesExecutor la imagen de Airflow queda "sin uso" entre tareas y el kubelet
   podría borrarla con el disco al 85 %.

## 3. Acceso de los developers a MicroK8s

El grupo Unix `microk8s` da acceso al clúster. Los grupos no se anidan: se agrega **a
cada usuario**.

```bash
sudo groupadd -f developers                        # lo hace un admin (idempotente)
sudo usermod -aG microk8s,developers <usuario>
```

Cada developer, **en su propia sesión** (una vez):

```bash
newgrp microk8s                                   # o salir y volver a entrar por SSH
mkdir -p ~/.kube && microk8s config > ~/.kube/config && chmod 600 ~/.kube/config
echo "alias kubectl='microk8s kubectl'" >> ~/.bashrc && source ~/.bashrc
kubectl get nodes
```

> **Seguridad:** el grupo `microk8s` es **admin total del clúster**. Para usuarios de
> solo lectura usa RBAC + un kubeconfig por usuario ([docs/11](11-single-node.md#4-seguridad)).

## 4. Helm (versión fijada)

```bash
make install-helm            # binario oficial v3.19.2 con verificación sha256 (no el snap)
helm repo add apache-airflow https://airflow.apache.org && helm repo update
```

## 5. Bootstrap del host

```bash
make bootstrap
```

[`scripts/bootstrap_host.sh`](../scripts/bootstrap_host.sh) crea el grupo `developers`,
las carpetas que no vienen en git (`logs/`, `files/`...) y aplica el modelo de permisos:

| Ruta | Dueño:grupo | Permisos | Por qué |
|---|---|---|---|
| `dags/`, `libs/`, `k8s/` | `PROJECT_OWNER:developers` | `2775` (setgid) | Los developers editan sin `sudo`; lo nuevo hereda el grupo |
| `files/`, `logs/` | `50000:developers` | `775` | Los Pods corren como **UID 50000** y deben escribir aquí |

Detalle: [06-files-y-permisos.md](06-files-y-permisos.md).

## 6. Entorno aislado `p313`

```bash
make conda-env
```

[`scripts/create_conda_env.sh`](../scripts/create_conda_env.sh):

1. Instala Miniconda en `CONDA_HOME` si no existe.
2. Crea `CONDA_ENVS_HOST_PATH/p313` desde **`envs/p313/environment.lock.yml`**: cada
   paquete (Python 3.13, Airflow + providers, librerías de datos y todas sus
   dependencias) en la versión exacta commiteada. Solo canal conda-forge.
3. Aplica `envs/p313/environment.yml` encima (instala lo que se haya agregado o cambiado).
4. `chmod -R a+rX` (los Pods lo leen como UID 50000) y vuelve a exportar el lock.

Por qué Conda y no `python -m venv`: [07-entornos-virtuales.md](07-entornos-virtuales.md).

## 7. Imagen de Airflow

```bash
make build
```

Construye `AIRFLOW_IMAGE_REPO:AIRFLOW_IMAGE_TAG` desde
[`docker/airflow/`](../docker/airflow/) y la **importa al containerd de MicroK8s**
(`docker save | microk8s ctr image import -`). Verifica:

```bash
sudo microk8s ctr images ls | grep airflow-k8s-base
```

## 8. Render + deploy

```bash
make deploy          # = make render + scripts/deploy.sh
```

1. `make render` genera `helm/values.yaml` y `k8s/pod_templates/pod_template.yaml` desde
   las plantillas. Si `WEBSERVER_SECRET_KEY` está vacía, la genera
   (`openssl rand -base64 32`) y la **guarda** en `platform.env`.
2. `deploy.sh` valida que existan las carpetas `hostPath`, crea el namespace y ejecuta
   `helm upgrade --install`.

Sigue el arranque (la primera vez tarda: migraciones de la DB + probes):

```bash
kubectl get pods -n airflow -w
```

Esperado: `scheduler`, `dag-processor`, `api-server`, `triggerer` y `postgresql` en
`Running`. Si algo queda en `CrashLoopBackOff` → [09-troubleshooting.md](09-troubleshooting.md).

## 9. Primer acceso a la UI

```bash
make ui-url          # http://<SERVER_IP>:<NODE_PORT>
```

El chart crea un usuario administrador inicial: **usuario `admin`, contraseña `admin`**
(valores por defecto de `createUserJob.defaultUser` en el chart 1.22.0). **Cámbiala de
inmediato:**

```bash
kubectl exec -n airflow deploy/airflow-scheduler -c scheduler -- \
  airflow users reset-password --username admin --password '<nueva-contraseña>'
```

(Probado: después del cambio la contraseña anterior responde `401` y la nueva entra.)

## 10. Connections, Variables y Pools

Las credenciales **nunca** van en el repo. Se crean en la UI (Admin → Connections) o se
importan desde un respaldo:

```bash
POD=$(kubectl get pods -n airflow -l component=scheduler -o jsonpath='{.items[0].metadata.name}')
kubectl cp ./connections.json airflow/$POD:/tmp/connections.json -c scheduler
kubectl exec -n airflow $POD -c scheduler -- airflow connections import /tmp/connections.json --overwrite
kubectl exec -n airflow $POD -c scheduler -- rm /tmp/connections.json     # ¡limpiar!
```

Mínimo recomendado: `smtp_default` para alertas por correo
([12-alertas.md](12-alertas.md)). Guarda los respaldos en un gestor de secretos
(KeePassXC, Vault, 1Password...), nunca en git ni en chats.

## 11. Smoke test

1. En la UI, activa y ejecuta **`example_etl`**. Debe terminar en verde.
2. Mientras corre: `kubectl get pods -n airflow -w` → verás nacer y morir un Pod por tarea.
3. Abre los logs de una tarea en la UI (si salen vacíos: [fix](09-troubleshooting.md#logs-vacíos-en-la-ui)).
4. En `files/example_etl/` debe quedar `summary_<fecha>.csv`.

Crea tu primer DAG real con `make new-dag NAME=mi_pipeline`.

## 12. CronJobs de auto-sanación

```bash
make cronjobs
kubectl get cronjobs -A | grep -E "pod-cleaner|calico-watchdog"
```

> Si cambiaste `AIRFLOW_NAMESPACE`, ajusta el namespace en
> `k8s/cronjobs/cleanup-failed-pods.yaml` antes de aplicarlo.

Pruébalos sin esperar al *schedule*:

```bash
kubectl create job --from=cronjob/pod-cleaner-cron test-cleaner -n airflow
kubectl logs -n airflow -l app=pod-cleaner --tail=50
kubectl delete job test-cleaner -n airflow
```

## 13. Checklist final

- [ ] NTP sincronizado, IP fija
- [ ] MicroK8s fijado (`snap list microk8s` → `held`), addons activos, `--docker-fix` si hay Docker
- [ ] Helm fijado + repo `apache-airflow`
- [ ] `make bootstrap` OK: `files/` y `logs/` con dueño `50000`
- [ ] `make conda-env` OK: `CONDA_ENVS_HOST_PATH/p313/bin/python` existe
- [ ] Imagen en containerd
- [ ] `make deploy` OK, todos los Pods `Running`
- [ ] Contraseña del admin cambiada
- [ ] Connections importadas; archivos temporales con credenciales borrados
- [ ] `example_etl` en verde, logs visibles en la UI
- [ ] CronJobs aplicados
- [ ] `make doctor` sin FAIL
- [ ] Backups de PostgreSQL programados ([10-operacion-y-recursos.md](10-operacion-y-recursos.md#5-backups))

## Desinstalar

```bash
make uninstall                                   # quita el release (el PVC de PostgreSQL queda)
kubectl delete pvc -n airflow --all              # ⚠️ borra la metadata DB
kubectl delete -k k8s/cronjobs/
```
