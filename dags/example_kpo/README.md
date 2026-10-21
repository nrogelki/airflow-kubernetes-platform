# example_kpo

**Qué hace:** ejecuta un paso en una **imagen distinta** a la de Airflow (aquí
`python:3.10-slim`) con `KubernetesPodOperator` (KPO), de dos formas, y después lee los
resultados con `external_python` en el entorno `p313`.

| Tarea | Qué muestra |
|---|---|
| `extract_other_image` | El Pod KPO definido solo con argumentos (`image`, `cmds`, `volumes`) |
| `extract_with_pod_template` | El Pod KPO a partir de un YAML ([`k8s/pod_templates/example_kpo_pod.yaml`](../../k8s/pod_templates/example_kpo_pod.yaml)) con un **sidecar nativo** y un volumen en memoria compartido: la misma forma que un sidecar de Kerberos que renueva tickets |
| `read_results` | `p313` (Python 3.13) lee lo que dejaron los Pods de Python 3.10 en `files/example_kpo/` |

| Campo | Valor |
|---|---|
| Schedule | manual (`None`) |
| Imagen dedicada | `python:3.10-slim` (se descarga una vez; en producción usa tu imagen importada con `image_pull_policy="Never"`) |
| Resultado | `files/example_kpo/other_image.txt`, `files/example_kpo/with_template.txt` |

## Qué pasa al ejecutarlo

1. El scheduler crea el **Pod de la tarea** con la imagen de Airflow (como cualquier tarea).
2. Ese Pod ejecuta el código del operador, que **le pide a la API de Kubernetes otro Pod**
   con la imagen dedicada. Son Pods **hermanos**: distinta imagen, distinta IP; el segundo
   no vive "dentro" del primero.
3. El Pod de la tarea espera, muestra los logs del otro en Airflow y lo borra al terminar.

Para verlo en vivo:

```bash
microk8s kubectl get pods -n airflow -w
# example-kpo-extract-other-image-xxxx   -> Pod de la tarea (imagen de Airflow)
# extract-other-image-xxxx               -> Pod KPO (python:3.10-slim)
```

## RBAC: qué es y por qué este DAG trae `KPO_LAUNCHER`

**RBAC** (*Role-Based Access Control*) es el sistema de permisos de Kubernetes. Cada Pod
habla con la API de Kubernetes con una identidad (su **ServiceAccount**), y RBAC decide
qué puede hacer esa identidad: crear Pods, leer Secrets, borrar cosas, etc.

- **Con RBAC activado** (`microk8s enable rbac`; lo hace `make install-microk8s`): todo lo
  que no está permitido explícitamente está prohibido. Los Pods de tarea usan la cuenta
  `default`, que **no** puede crear Pods. Un KPO sin más falla con:

  ```text
  403 Forbidden: User "system:serviceaccount:airflow:default" cannot list resource "pods"
  ```

- **Sin RBAC** (MicroK8s sin el addon: modo `AlwaysAllow`): **todo está permitido a todos**.
  El KPO funciona sin configurar nada, pero cualquier tarea de cualquier DAG también puede
  borrar los Pods de Airflow, leer cualquier Secret (contraseñas, keytabs) o crear Pods
  privilegiados.

`KPO_LAUNCHER` (`executor_config` con `service_account_name="airflow-worker"`) le da
**solo al Pod de estas tareas** la cuenta que el chart de Airflow creó para lanzar Pods.
Así el DAG funciona **en los dos modos**, y el día que alguien active RBAC no se rompe.
No toca el `pod_template` global: el resto de las tareas sigue con `default`.

| | Con RBAC | Sin RBAC |
|---|---|---|
| KPO **sin** `KPO_LAUNCHER` | ❌ 403 | ✅ |
| KPO **con** `KPO_LAUNCHER` | ✅ | ✅ |
| Lo que puede hacer una tarea cualquiera | solo lo suyo | **todo** en el clúster |

¿Cuál tienes? Compruébalo en el nodo:

```bash
sudo grep -q -- '--authorization-mode=.*RBAC' /var/snap/microk8s/current/args/kube-apiserver \
  && echo "RBAC: SÍ" || echo "RBAC: NO (AlwaysAllow)"
```

Si tu release de Helm no se llama `airflow`, la cuenta es `<HELM_RELEASE>-worker`
(`microk8s kubectl get sa -n airflow`). Detalle completo y pruebas:
[docs/14](../../docs/14-imagenes-dedicadas-kpo.md#3-permisos-con-rbac-y-sin-rbac).
