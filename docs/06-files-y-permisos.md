# 06 · La carpeta `files/` y los permisos (UID 50000)

`files/` es el área de **datos** de los pipelines: configuraciones de entrada y archivos
de staging. Se monta en `/opt/airflow/files`. Sus permisos son **la causa #1 de fallos
evitables** al desplegar un DAG.

## 1. Qué va y qué no

```
files/<dag_id>/          ← nombre IDÉNTICO al dag_id
├── config.json          ← inputs versionados en git (.json/.yml)
└── sales_2026-01-01.parquet   ← staging: lo crea y lo borra el propio DAG
```

| Sí | No |
|---|---|
| Configs de entrada (`.json`, `.yml`) | Código Python (va en `dags/` o `libs/`) |
| Staging temporal (zip, csv, parquet) | Credenciales (van en Connections) |
| Salidas intermedias entre tareas | Históricos que deban persistir (van a una base de datos) |

El `.gitignore` versiona solo `.json`/`.yml`/`.gitkeep` de `files/`: el staging nunca
llega a git.

## 2. El problema, explicado

Dos identidades tocan la misma carpeta:

| Quién | Identidad | Cuándo |
|---|---|---|
| Tú en el servidor | tu usuario (grupo `developers`) | Crear/editar inputs |
| Los Pods de Airflow | **UID 50000** | Leer inputs, escribir/borrar staging |

Si creas un archivo `644 tu_usuario:tu_usuario`, el Pod lo lee pero **no puede
borrarlo**; si la carpeta no es escribible por 50000, la descarga falla con
`PermissionError`. Al revés: lo que crea el Pod pertenece a 50000.

## 3. La configuración correcta

```bash
sudo chown -R 50000:developers files/<dag_id>
sudo chmod -R 775              files/<dag_id>      # carpetas
sudo chmod 664                 files/<dag_id>/*.json
```

- Dueño **50000**: el Pod crea/borra staging.
- Grupo **developers**: cualquier developer edita inputs sin `sudo`.
- `make new-dag` y `make bootstrap` ya lo dejan así.

## 4. Síntomas y solución

| Síntoma en el log de la tarea | Causa | Fix |
|---|---|---|
| `PermissionError: [Errno 13] ... /opt/airflow/files/<dag>/x` | Carpeta no escribible por 50000 | `chown 50000:developers` + `chmod 775` |
| `FileNotFoundError` sobre un input que "existe" | Carpeta con nombre distinto al `dag_id`, o el archivo quedó en `dags/` | Renombrar/mover al espejo correcto |
| La limpieza de staging falla | Archivos creados a mano que el Pod no puede borrar | `chown 50000:developers` |
| No puedes editar un CSV de staging | Lo creó el Pod | `sudo`, o deja que el pipeline lo regenere |
| Pod en `ContainerCreating` para siempre, evento `hostPath type check failed` | Falta una carpeta montada | `make bootstrap` |

## 5. Buenas prácticas

1. Limpia el staging al final de una corrida exitosa (`dataplatform.utils.local_files.clean_dir`).
2. Si ves archivos viejos acumulados, **hubo corridas fallidas**: revisa el DAG antes de
   borrar (puede ser la única copia si el origen ya rotó).
3. Nombra el staging con `ds` (`sales_{ds}.parquet`) para que corridas de días distintos
   no se pisen.
