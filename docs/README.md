# Documentación

## Por dónde empezar

**¿Primera vez?** Empieza por [00 · Conceptos clave](00-conceptos-clave.md): explica todo
el vocabulario (Pod, hostPath, Helm, XCom, `external_python`...) con analogías y sin
asumir que conoces Kubernetes. Si tienes una duda puntual, revisa las
[preguntas frecuentes](15-preguntas-frecuentes.md).

| Si eres… | Lee |
|---|---|
| Nuevo en Kubernetes o en Airflow | [00 Conceptos clave](00-conceptos-clave.md) → [01 Arquitectura](01-arquitectura.md) |
| Quien decide si adoptarla | [02 Celery vs Kubernetes](02-celery-vs-kubernetes-executor.md) → [11 Single-node](11-single-node.md) → [01 Arquitectura](01-arquitectura.md) |
| Quien la instala | [03 Instalación](03-instalacion-desde-cero.md) → [04 Configuración](04-configuracion.md) → [10 Operación](10-operacion-y-recursos.md) |
| Quien migra desde Celery | [08 Migración](08-migracion-desde-celery.md) |
| Quien escribe DAGs | [05 Desarrollo](05-desarrollo-de-dags.md) → [06 files/](06-files-y-permisos.md) → [12 Alertas](12-alertas.md) → [13 Librería](13-libreria-dataplatform.md) |
| Quien está apagando un incendio | [09 Troubleshooting](09-troubleshooting.md) |

## Índice

| # | Documento | Contenido |
|---|---|---|
| 00 | [Conceptos clave](00-conceptos-clave.md) | Glosario con analogías, qué archivo tocar para qué, errores de principiante |
| 01 | [Arquitectura](01-arquitectura.md) | Componentes, ciclo de vida de una tarea, hostPath, dominios de código |
| 02 | [Celery vs KubernetesExecutor](02-celery-vs-kubernetes-executor.md) | Cómo funciona cada uno, trade-offs, cuándo no migrar |
| 03 | [Instalación desde cero](03-instalacion-desde-cero.md) | Runbook completo en orden + checklist |
| 04 | [Configuración](04-configuracion.md) | `platform.env`, plantillas, fixes críticos de Airflow 3 |
| 05 | [Desarrollo de DAGs](05-desarrollo-de-dags.md) | PYTHONPATH, patrones de import, reglas, ejemplos, recetas |
| 06 | [`files/` y permisos](06-files-y-permisos.md) | UID 50000, síntomas y solución |
| 07 | [Entornos virtuales](07-entornos-virtuales.md) | Buenas prácticas, Conda vs venv, blue/green |
| 08 | [Migración desde Celery](08-migracion-desde-celery.md) | "Es mover carpetas": paso a paso, rollback, Airflow 2→3 |
| 09 | [Troubleshooting](09-troubleshooting.md) | Incidentes reales con causa y fix |
| 10 | [Operación y recursos](10-operacion-y-recursos.md) | Concurrencia, dimensionamiento, monitoreo, backups, upgrades |
| 11 | [Single-node](11-single-node.md) | Implicancias, cuándo alcanza y seguridad |
| 12 | [Alertas](12-alertas.md) | Plantillas; cómo Airflow resuelve `smtp_default` |
| 13 | [Librería `dataplatform`](13-libreria-dataplatform.md) | Referencia de building blocks |
| 14 | [Imágenes dedicadas (KPO)](14-imagenes-dedicadas-kpo.md) | Stacks especiales, caso Kerberos |
| 15 | [Preguntas frecuentes](15-preguntas-frecuentes.md) | Respuestas cortas a las dudas más comunes |
| — | [CronJobs de auto-sanación](../k8s/cronjobs/README.md) | Limpiador de Pods, watchdog de Calico, suite de pruebas |

## Decisiones de arquitectura (ADR)

| ADR | Decisión |
|---|---|
| [0001](adr/0001-kubernetes-executor.md) | KubernetesExecutor en lugar de CeleryExecutor |
| [0002](adr/0002-inyeccion-de-codigo-por-hostpath.md) | Inyección de código por hostPath (no git-sync ni imagen) |
| [0003](adr/0003-entornos-aislados-external-python.md) | Entorno Conda aislado + `@task.external_python` |
| [0004](adr/0004-single-node-microk8s.md) | Un solo nodo con MicroK8s |
