"""Helpers for the per-DAG data folder ``/opt/airflow/files/<dag_id>/``.

Standard library only: safe to import anywhere (scheduler or isolated env).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

FILES_ROOT = Path("/opt/airflow/files")


def dag_files_path(dag_id: str, root: str | Path = FILES_ROOT) -> Path:
    """Return the data folder of a DAG. Its name MUST equal the ``dag_id``."""
    return Path(root) / dag_id


def read_json(base_dir: str | Path, filename: str) -> dict:
    """Read a JSON input file (e.g. a column mapping) from a DAG data folder."""
    path = Path(base_dir) / filename
    if not path.is_file():
        raise FileNotFoundError(
            f"Input not found: {path}. Is the folder name equal to the dag_id "
            "and the file owned by UID 50000? (docs/06-files-y-permisos.md)"
        )
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def ensure_dir(path: str | Path) -> Path:
    """Create a staging directory if needed and return it."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def clean_dir(path: str | Path, keep: tuple[str, ...] = ()) -> list[str]:
    """Delete the contents of a staging directory, except the names in ``keep``.

    Returns the deleted names. Used at the end of a successful run so staging
    does not accumulate. Input configs should be listed in ``keep``.
    """
    p = Path(path)
    removed: list[str] = []
    if not p.is_dir():
        return removed
    for child in p.iterdir():
        if child.name in keep:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
        removed.append(child.name)
    return sorted(removed)
