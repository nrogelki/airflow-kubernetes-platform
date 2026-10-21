## Qué cambia

<!-- Resumen breve. Referencia el issue: Closes #123 -->

## Tipo de cambio

- [ ] Bug fix
- [ ] Nueva funcionalidad
- [ ] Documentación
- [ ] Infraestructura (Helm / pod template / imagen / scripts)

## Checklist

- [ ] `make lint` y `make test` pasan localmente
- [ ] `make check-dags` sin FAIL (si toca `dags/` o `libs/`)
- [ ] Documentación actualizada (`docs/`, README del DAG) si aplica
- [ ] `CHANGELOG.md` actualizado en `[Unreleased]`
- [ ] No incluye secretos, IPs reales ni `platform.env` / `values.yaml`

## Cómo se probó

<!-- Comandos, versión de MicroK8s/Helm/Airflow, capturas si aplica -->
