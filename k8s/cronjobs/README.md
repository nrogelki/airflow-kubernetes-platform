# CronJobs de auto-sanación

Dos CronJobs que resuelven, sin intervención humana, los dos incidentes más frecuentes
de un clúster MicroK8s de un nodo corriendo Airflow con KubernetesExecutor.

| CronJob | Namespace | Frecuencia | Qué hace | Código fuente |
|---|---|---|---|---|
| `pod-cleaner-cron` | `airflow` | cada 10 min | Borra Pods fallidos o atascados | [`scripts/cleanup-failed-pods.sh`](scripts/cleanup-failed-pods.sh) |
| `calico-watchdog-cron` | `kube-system` | cada 5 min | Reinicia Calico si perdió su token | [`scripts/watchdog-calico.sh`](scripts/watchdog-calico.sh) |

```
k8s/cronjobs/
├── kustomization.yaml          ← empaqueta scripts/*.sh como ConfigMaps (montados en /scripts)
├── cleanup-failed-pods.yaml    ← ServiceAccount + Role + RoleBinding + CronJob
├── watchdog-calico.yaml        ← ServiceAccount + ClusterRole + Binding + CronJob
└── scripts/
    ├── cleanup-failed-pods.sh  ← código del limpiador
    ├── watchdog-calico.sh      ← código del watchdog
    └── test-watchdog.sh        ← suite de pruebas del watchdog (se ejecuta desde tu terminal)
```

Los scripts son archivos reales (no texto embebido en YAML): se leen con resaltado, se
revisan en los PR y `shellcheck` los valida en CI.

## Instalar / actualizar / desinstalar

```bash
make cronjobs                                    # = kubectl apply -k k8s/cronjobs/
kubectl get cronjobs -A | grep -E "pod-cleaner|calico-watchdog"

kubectl kustomize k8s/cronjobs/                  # ver lo que se aplicará, sin aplicar
kubectl delete -k k8s/cronjobs/                  # desinstalar
```

Editar un script → `make cronjobs` otra vez (regenera el ConfigMap; la siguiente
ejecución ya usa la versión nueva).

> Si tu namespace de Airflow no es `airflow`, cámbialo en `cleanup-failed-pods.yaml`
> (todas las apariciones) y en `kustomization.yaml`.

> **Imagen.** Ambos usan `docker.io/bitnami/kubectl` (Debian: trae `kubectl` y `date` de
> GNU, que los scripts necesitan). En producción fija un tag concreto y
> pre-descárgalo en el nodo. Cualquier imagen Debian con `kubectl` sirve.

---

## 1. Limpiador de Pods (`pod-cleaner`)

**Por qué.** Con KubernetesExecutor nacen cientos de Pods al día. Los que fallan
(`Error`, `Evicted`, `OOMKilled`, `DeadlineExceeded`) o se atascan
(`ImagePullBackOff`, `CrashLoopBackOff`...) se acumulan, ensucian `kubectl get pods` y
consumen entradas en etcd/dqlite.

| Acción | Estado del Pod |
|---|---|
| **Borra** | `phase=Failed`: Error, Evicted, DeadlineExceeded, OOMKilled, ContainerStatusUnknown |
| **Borra si lleva >10 min** | ImagePullBackOff, ErrImagePull, CrashLoopBackOff, CreateContainerConfigError, CreateContainerError, InvalidImageName, RunContainerError, StartError |
| **Respeta** | Running, Pending/ContainerCreating, Succeeded/Completed, Terminating |

- El umbral de 10 min evita matar estados transitorios legítimos.
- **Los logs de tareas no se pierden**: viven en `logs/` del nodo (lo que se pierde es
  el `kubectl logs` del contenedor muerto).
- RBAC con `Role` **solo en el namespace de Airflow**: no puede tocar nada más.

```bash
# Ejecutar ya, sin esperar al schedule
kubectl create job --from=cronjob/pod-cleaner-cron cleaner-now -n airflow
kubectl logs -n airflow job/cleaner-now
kubectl delete job cleaner-now -n airflow

# Modo prueba (solo informa)
kubectl set env cronjob/pod-cleaner-cron -n airflow DRY_RUN=1
kubectl set env cronjob/pod-cleaner-cron -n airflow DRY_RUN=0      # re-armar

# Prueba E2E: un Pod condenado a fallar -> desaparece entre 10 y 20 min después
# (no toca Pods con menos de 10 min + espera la siguiente ejecución del CronJob, cada 10 min)
kubectl run broken-pod --image=image-that-does-not-exist:v0 -n airflow --restart=Never
```

## 2. Watchdog de Calico (`calico-watchdog`)

**El incidente.** El clúster deja de crear Pods. Todo Pod nuevo queda en
`ContainerCreating` con el evento:

```
Failed to create pod sandbox: plugin type="calico" failed (add): error getting
ClusterInformation: connection is unauthorized: Unauthorized
```

El token de ServiceAccount del plugin CNI expiró y no se renovó (conocido en MicroK8s
tras rotación de certificados o reloj desincronizado). Con KubernetesExecutor esto es
fatal: **ninguna tarea puede arrancar**. `kubectl rollout restart daemonset/calico-node
-n kube-system` regenera el token; el watchdog lo automatiza.

**Candados de seguridad** (actúa solo si se cumplen TODOS):

1. Hay eventos `Warning` con la firma exacta (`plugin type="calico" failed` **y** `Unauthorized`).
2. Son **recientes** (últimos 15 min). Los eventos viven ~1 h: sin esta ventana,
   contaría errores ya resueltos y reiniciaría Calico en bucle.
3. No hubo un reinicio en la última **hora** (anotación `watchdog.last-restart-ts` en el
   DaemonSet = *cooldown* anti-bucle).

**Decisiones de diseño:**

- `hostNetwork: true`: el Pod del watchdog no necesita a Calico para arrancar. Sin esto,
  el watchdog no podría ejecutarse justo cuando Calico está caído.
- `date -d` (GNU), no `date -D` (BusyBox): con la sintaxis equivocada el cálculo fallaba
  en silencio y el cooldown nunca operaba.
- `DRY_RUN=1` detecta y registra sin reiniciar.

**Qué NO cubre (a propósito):** `CrashLoopBackOff` de `calico-node` (BGP/BIRD), IPAM
agotado, conflictos iptables/nftables, datastore corrupto, reloj desincronizado. Esos
requieren diagnóstico manual; un restart no arregla la causa. Complementos: **NTP activo**
y `sudo microk8s refresh-certs --check` periódico.

```bash
# Última ejecución
kubectl logs -n kube-system -l app=calico-watchdog --tail=20

# Ejecutar ya
kubectl create job --from=cronjob/calico-watchdog-cron watchdog-now -n kube-system
kubectl logs -n kube-system job/watchdog-now
kubectl delete job watchdog-now -n kube-system

# ¿Cuándo fue el último reinicio automático?
kubectl get ds calico-node -n kube-system -o jsonpath='{.metadata.annotations.watchdog\.last-restart-ts}' \
  | xargs -I{} date -d @{}
```

## 3. Suite de pruebas del watchdog (`test-watchdog.sh`)

Prueba cada condición de activación de forma **individual, combinada y completa**,
inyectando eventos sintéticos. Cada caso lanza un Job desde el CronJob y se autoevalúa
leyendo sus logs. **Nunca reinicia Calico**: aborta si el watchdog no está en `DRY_RUN=1`.

| Comando | Qué prueba | Esperado |
|---|---|---|
| `prepare` | Pone `DRY_RUN=1` y guarda la anotación de cooldown real | — |
| `case1` | Línea base, sin eventos | No actúa |
| `case2` | Firma de Calico **sin** `Unauthorized` | No actúa |
| `case3` | `Unauthorized` **fuera** del CNI | No actúa |
| `case4` | Firma completa pero de hace 30 min | No actúa (ventana anti-bucle) |
| `case5` | Firma completa + reciente + sin cooldown | **ALERTA** (en dry-run, sin reinicio) |
| `case6` | Firma válida + reinicio reciente (anotación) | **COOLDOWN** lo bloquea |
| `rbac` | 3 permisos que deben ser `yes` y 3 que deben ser `no` | 6 PASS |
| `all` | case1–case6 + rbac | Todos PASS |
| `finish` | Borra eventos/jobs de prueba, restaura la anotación, `DRY_RUN=0` (armado) | — |

```bash
k8s/cronjobs/scripts/test-watchdog.sh prepare
k8s/cronjobs/scripts/test-watchdog.sh all
k8s/cronjobs/scripts/test-watchdog.sh finish        # ¡no olvidar: re-arma el watchdog!
```

Variables: `KUBECTL` (default `microk8s kubectl`), `AIRFLOW_NAMESPACE` (default
`airflow`). Ejecútala en una ventana tranquila: errores **reales** de Calico en los
últimos 15 min alterarían los resultados.

### Verificar RBAC a mano

```bash
kubectl auth can-i patch daemonsets -n kube-system --as=system:serviceaccount:kube-system:calico-watchdog  # yes
kubectl auth can-i delete pods -n airflow          --as=system:serviceaccount:airflow:pod-cleaner          # yes
kubectl auth can-i delete pods -n kube-system      --as=system:serviceaccount:airflow:pod-cleaner          # no (¡debe ser no!)
```

### Prueba real (solo en ventana de mantenimiento)

Romper el token de Calico a propósito (editar el `calico-kubeconfig` del nodo con un
token inválido) prueba el escenario completo, pero **detiene la creación de Pods de todo
el clúster**. Hazlo solo con respaldo del archivo y el failback a mano listo:
restaurar el archivo + `kubectl rollout restart daemonset/calico-node -n kube-system`.
