# ADR 0004 · Un solo nodo con MicroK8s

- **Estado:** Aceptada
- **Contexto:** Un área de datos con un servidor potente disponible, sin equipo de
  plataforma dedicado ni presupuesto para un clúster gestionado. Cargas batch diarias/horarias.
- **Decisión:** MicroK8s de un nodo, versión fijada (`snap refresh --hold`), Helm fijado,
  chart oficial de Airflow.
- **Alternativas:**
  - *K8s gestionado (EKS/GKE/AKS)*: costo y dependencia de nube; sobredimensionado para la carga.
  - *k3s / kind*: viables; MicroK8s aportó addons (dns, hostpath-storage, rbac, metrics) con un comando y soporte snap.
  - *Docker Compose con Celery*: el punto de partida que se quería dejar.
- **Consecuencias** (✅ beneficio · ⚠️ costo que se acepta):
  - ✅ Simplicidad operativa y costo mínimo; hostPath y sin registry ([ADR 0002](0002-inyeccion-de-codigo-por-hostpath.md)).
  - ⚠️ Punto único de falla y capacidad acotada al servidor ([docs/11](../11-single-node.md)).
  - ⚠️ El fix `--advertise-address` (convivencia con Docker) es incompatible con HA.
