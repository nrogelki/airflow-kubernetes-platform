# ADR 0002 · Inyección de código por hostPath

- **Estado:** Aceptada
- **Contexto:** Con KubernetesExecutor, cada Pod necesita ver los DAGs y librerías. Las
  opciones estándar son hornearlos en la imagen o sincronizarlos con git-sync.
- **Decisión:** Montar `dags/`, `libs/`, `files/`, `logs/` y `pod_templates/` desde el
  disco del nodo con volúmenes `hostPath` (`type: Directory`), con mínimo privilegio por
  componente y solo lectura en los Pods de tarea para código.
- **Alternativas:**
  - *Código en la imagen*: un build + import + deploy por cada cambio de DAG; ciclo lento.
  - *git-sync*: requiere que todo pase por el remoto y agrega un sidecar por componente;
    razonable en multinodo, innecesario en uno.
  - *PVC RWX (NFS)*: infraestructura extra sin beneficio en un solo nodo.
- **Consecuencias** (✅ beneficio · ⚠️ costo que se acepta):
  - ✅ Un `git pull` en el nodo publica cambios; sin registry ni pipelines de imagen.
  - ✅ Staging y logs en disco local (rápido).
  - ⚠️ **Solo válido en single-node.** Multinodo queda fuera del alcance de esta plantilla ([docs/11](../11-single-node.md#3-es-suficiente-para-mí)).
  - ⚠️ Los permisos del host importan (UID 50000): se automatizan con `make bootstrap`.
