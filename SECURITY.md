# Política de seguridad

## Reportar una vulnerabilidad

**No abras un issue público.** Usa *Security → Report a vulnerability* (GitHub Private
Vulnerability Reporting) de este repositorio. Incluye descripción, impacto, pasos para
reproducir y versiones afectadas. Responderemos en un plazo de 7 días.

Las vulnerabilidades de Apache Airflow en sí deben reportarse a
security@apache.org según https://airflow.apache.org/docs/apache-airflow/stable/security/.

## Versiones soportadas

| Versión | Soporte |
|---|---|
| 1.x (última) | ✅ |
| anteriores | ❌ |

## Modelo de seguridad de la plataforma (resumen)

| Activo | Protección |
|---|---|
| `config/platform.env` (secret key) | Fuera de git (`.gitignore`), permisos `640` |
| `helm/values.yaml` renderizado | Fuera de git, permisos `640` |
| Credenciales de sistemas | Connections de Airflow (cifradas con Fernet) o secrets backend |
| Keytabs / certificados | Secrets de Kubernetes, nunca en imagen ni repo |
| Acceso al clúster | Grupo `microk8s` = admin; RBAC de solo lectura para el resto |
| UI | NodePort HTTP: solo red interna, o Ingress con TLS |
| Repositorio | `detect-secrets` y `detect-private-key` en pre-commit |

Detalle: [docs/11-single-node.md#4-seguridad](docs/11-single-node.md#4-seguridad).

Si por error commiteaste un secreto: **rótalo de inmediato** (borrarlo del historial no
basta: puede estar en clones y forks).
