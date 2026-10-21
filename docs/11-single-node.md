# 11 · Single-node: implicancias

Esta plataforma está diseñada para **un único servidor** con MicroK8s. Es una decisión
deliberada ([ADR 0004](adr/0004-single-node-microk8s.md)), no una limitación accidental.
Entiende lo que implica antes de adoptarla.

## 1. Lo que ganas

| Beneficio | Por qué es posible en un solo nodo |
|---|---|
| **Código vivo sin CI/CD de imágenes** | `hostPath`: todos los Pods ven el mismo disco |
| **Sin registry de contenedores** | La imagen se importa al containerd local una vez |
| **Sin almacenamiento en red** (NFS, Ceph, S3 para logs) | Logs y staging en disco local, rápido y simple |
| **Arranque de tareas en segundos** | Imagen ya local (`pullPolicy: Never`) |
| **Costo mínimo** | Un servidor (o VM) que muchas áreas ya tienen subutilizado |
| **Operación abordable** | Un equipo de datos puede operarlo con la guía de [10](10-operacion-y-recursos.md) |

## 2. Lo que asumes

| Implicancia | Qué significa en la práctica | Mitigación |
|---|---|---|
| **Punto único de falla** | Si el servidor cae, Airflow cae: no se ejecuta nada hasta que vuelve | Monitoreo externo (ping a la UI), UPS, reinicio automático, runbook de DR probado |
| **Capacidad acotada al nodo** | CPU/RAM total = la del servidor; `PARALLELISM` tiene un techo físico | Dimensionar ([10 §3](10-operacion-y-recursos.md#3-dimensionamiento)); escalar vertical primero |
| **Mantenimiento = downtime** | Actualizar SO, kernel o MicroK8s detiene todo | Ventanas fuera del horario de los ETLs; `catchup` controlado al volver |
| **Disco compartido** | Logs, staging, imágenes y PostgreSQL compiten por el mismo disco | Alertas de disco, limpieza de logs, SSD, `--image-gc` |
| **Backups manuales** | La metadata DB vive en un PVC local | `pg_dump` programado fuera del servidor ([10 §5](10-operacion-y-recursos.md#5-backups)) |
| **Fix de Docker incompatible con HA** | `--advertise-address=0.0.0.0` rompe `microk8s join` | Quitarlo antes de pasar a multinodo |
| **Componentes con 1 réplica** | Scheduler, API server, PostgreSQL sin redundancia | Aceptable: si el nodo cae, las réplicas caerían igual |

### ¿Qué pasa con las tareas si el nodo se reinicia?

Las tareas en curso mueren. Al volver, el scheduler las marca como fallidas (o *zombie*)
y las **reintenta** según `retries`. Por eso importa que las cargas sean
**idempotentes** ([05 §4](05-desarrollo-de-dags.md#4-reglas-de-oro)). Las corridas
programadas que no se ejecutaron durante la caída se lanzan al volver solo si
`catchup=True`; con `catchup=False` se ejecuta la más reciente.

## 3. ¿Es suficiente para mí?

Sí, típicamente, si:
- Tus pipelines son batch (horarios/diarios) y toleran un retraso de horas ante una falla
  de hardware.
- Tienes hasta cientos de DAGs y decenas de tareas simultáneas.
- Cabe en un servidor de 32–128 GB.

No, si:
- Necesitas **alta disponibilidad** con SLA estricto (minutos).
- Tu carga excede lo que un servidor grande puede ejecutar en paralelo.
- Varios equipos necesitan aislamiento fuerte (multi-tenant con cuotas, redes separadas).
- Necesitas **varios nodos**: esta plantilla está pensada y probada solo para un servidor
  (usa `hostPath` para código, datos y el entorno). Llevarla a multinodo queda fuera de
  su alcance.

## 4. Seguridad

Un solo nodo concentra todo: protégelo en proporción.

- **Grupo `microk8s` = admin del clúster.** Solo para quienes operan la plataforma. Para
  developers que solo inspeccionan: RBAC con un `Role` de solo lectura
  (`get`,`list`,`watch` sobre `pods`, `pods/log`, `events`) y un kubeconfig por usuario.
- **La UI por NodePort es HTTP.** Exponla solo en la red interna, o pon delante un
  Ingress/reverse proxy con TLS.
- **SSH** con llaves, sin contraseña; `ufw` abriendo solo SSH y el NodePort a la red
  corporativa.
- **Secretos:** `platform.env` con `640`; Connections cifradas con Fernet; nunca
  credenciales en `files/` ni en git (pre-commit con `detect-secrets` incluido).
- Mantén el SO parchado (`unattended-upgrades` para seguridad), en ventana controlada.
