# example_resource_override

**Qué hace:** muestra cómo darle a **una sola tarea** más CPU/RAM que el default
del `pod_template` usando `executor_config={"pod_override": ...}`, y cómo
limitarla con un **pool**.

| Campo | Valor |
|---|---|
| Schedule | manual (`None`) |
| Entorno | `/opt/conda/envs/p313` |
| Recursos `heavy_task` | requests 1 CPU / 2Gi — limits 4 CPU / 12Gi |

Mientras corre, observa el pod con:

```bash
microk8s kubectl get pods -n airflow -w
microk8s kubectl top pods -n airflow
```
