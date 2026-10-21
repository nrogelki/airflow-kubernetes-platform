# ADR 0001 · KubernetesExecutor en lugar de CeleryExecutor

- **Estado:** Aceptada
- **Contexto:** Airflow con CeleryExecutor en un servidor compartido. Los recursos se
  definían por worker y no por tarea (tareas pandas con consumos muy distintos compartiendo
  la misma RAM), las dependencias de datos convivían con las de Airflow en el mismo
  entorno, y había un broker + Flower que mantener.
- **Decisión:** KubernetesExecutor: un Pod efímero por tarea con `requests`/`limits`.
  Redis y Flower eliminados.
- **Alternativas:**
  - *Celery con más workers/colas*: permite separar cargas, pero los recursos y el entorno siguen siendo por worker, no por tarea.
  - *CeleryKubernetesExecutor*: dos sistemas que operar; no había tareas de latencia crítica que lo justificaran.
  - *LocalExecutor*: mismo problema de contención, en un solo proceso.
- **Consecuencias** (✅ beneficio · ⚠️ costo que se acepta):
  - ✅ Aislamiento por tarea, cero estado residual, recursos por tarea (`executor_config`).
  - ✅ Menos componentes.
  - ⚠️ ~3–10 s de arranque por tarea (medido: mediana 5 s): inadecuado para miles de tareas muy cortas.
  - ⚠️ El equipo necesita nociones básicas de Kubernetes.
