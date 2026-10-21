"""Load parametrised .sql files from ``dags/<dag_id>/sql/``.

Keeps SQL out of Python strings (reviewable, syntax-highlighted, diffable).
Placeholders use ``$name`` / ``${name}`` (``string.Template``): meant for
IDENTIFIERS and dates you control (table names, ``ds``). For user-provided
VALUES always use the driver's bind parameters instead.
"""

from __future__ import annotations

import re
from pathlib import Path
from string import Template

DAGS_ROOT = Path("/opt/airflow/dags")
_SAFE_VALUE = re.compile(r"^[\w\-.:/ ]*$")


def load_sql(dag_id: str, name: str, params: dict | None = None, root: str | Path = DAGS_ROOT) -> str:
    """Read ``<root>/<dag_id>/sql/<name>.sql`` and substitute ``params``.

    Raises ``KeyError`` on a missing parameter and ``ValueError`` on values
    with characters that could break out of an identifier/literal.
    """
    filename = name if name.endswith(".sql") else f"{name}.sql"
    path = Path(root) / dag_id / "sql" / filename
    text = path.read_text(encoding="utf-8")
    params = params or {}
    for key, value in params.items():
        if not _SAFE_VALUE.match(str(value)):
            raise ValueError(f"Unsafe value for SQL parameter '{key}': {value!r}")
    return Template(text).substitute(params)


def split_statements(sql: str) -> list[str]:
    """Split a script on ';' (ignores empty statements and '--' comment lines).

    Simple on purpose: not meant for procedural code containing ';' in bodies.
    """
    cleaned = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    return [s.strip() for s in cleaned.split(";") if s.strip()]
