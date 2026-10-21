#!/usr/bin/env python3
"""check_dags.py — static sanity check of every dags/<dag_id>/ before deploying.

Standard library only: runs anywhere (laptop, CI) without Airflow or the
isolated environment. It validates structure and first-party references,
not that third-party libraries are installed.

Checks per DAG:
  FAIL  _dag.py missing or does not parse
  FAIL  import dataplatform.* does not resolve under libs/
  FAIL  import <dag_id>.scripts.* does not resolve under dags/
  FAIL  _dag.py imports heavy libraries at module level (pandas, polars, ...)
  FAIL  dag_id="..." in _dag.py differs from the folder name
  WARN  missing README.md, scripts/__init__.py or files/<dag_id>/

Usage:
    python tools/check_dags.py            # all DAGs
    python tools/check_dags.py <dag_id>   # one DAG
Exit code 1 if any FAIL (pre-commit / CI friendly).
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LIB_PACKAGE = "dataplatform"

# Libraries that must never be imported at parse time in _dag.py: they are not
# in the Airflow image (they live in the isolated env) and slow the parser.
HEAVY_MODULES = {
    "pandas",
    "polars",
    "numpy",
    "pyarrow",
    "sklearn",
    "torch",
    "clickhouse_connect",
    "psycopg",
    "psycopg2",
    "pymysql",
    "mysql",
    "openpyxl",
}


@dataclass
class Result:
    dag_id: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "FAIL" if self.errors else ("WARN" if self.warnings else "OK")


def module_resolves(dotted: str, base: Path) -> bool:
    path = base.joinpath(*dotted.split("."))
    return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file() or path.is_dir()


def iter_imports(tree: ast.AST, top_level_only: bool = False):
    nodes = tree.body if top_level_only else ast.walk(tree)
    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


def declared_dag_ids(tree: ast.AST) -> set[str]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "dag_id" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    ids.add(kw.value.value)
    return ids


def check_dag(dag_id: str, repo: Path = REPO) -> Result:
    res = Result(dag_id)
    dags, libs, files = repo / "dags", repo / "libs", repo / "files"
    dag_dir = dags / dag_id
    dag_py = dag_dir / "_dag.py"

    if not dag_py.is_file():
        res.errors.append("missing _dag.py")
        return res
    try:
        dag_tree = ast.parse(dag_py.read_text(encoding="utf-8"), filename=str(dag_py))
    except SyntaxError as exc:
        res.errors.append(f"_dag.py does not parse: {exc}")
        return res

    for mod in iter_imports(dag_tree, top_level_only=True):
        if mod.split(".")[0] in HEAVY_MODULES:
            res.errors.append(f"_dag.py imports '{mod}' at module level (move it inside the task)")

    for declared in declared_dag_ids(dag_tree):
        if declared != dag_id:
            res.errors.append(f"dag_id='{declared}' differs from folder name '{dag_id}'")

    scripts_dir = dag_dir / "scripts"
    sources = [dag_py]
    if scripts_dir.is_dir():
        sources += [p for p in scripts_dir.rglob("*.py") if "__pycache__" not in p.parts]

    for src in sources:
        rel = src.relative_to(dag_dir)
        try:
            tree = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
        except SyntaxError as exc:
            res.errors.append(f"{rel} does not parse: {exc}")
            continue
        for mod in iter_imports(tree):
            top = mod.split(".")[0]
            if top == LIB_PACKAGE and not module_resolves(mod, libs):
                res.errors.append(f"import '{mod}' does not resolve in libs/ (from {rel})")
            elif top == dag_id and not module_resolves(mod, dags):
                res.errors.append(f"import '{mod}' does not resolve in dags/ (from {rel})")

    if not (dag_dir / "README.md").is_file():
        res.warnings.append("missing README.md")
    if scripts_dir.is_dir() and not (scripts_dir / "__init__.py").is_file():
        res.warnings.append("scripts/ without __init__.py")
    if not (files / dag_id).is_dir():
        res.warnings.append(f"missing data folder files/{dag_id}/")
    return res


def discover(repo: Path = REPO) -> list[str]:
    dags = repo / "dags"
    return sorted(p.name for p in dags.iterdir() if p.is_dir() and not p.name.startswith((".", "__")))


def main(argv: list[str]) -> int:
    if not (REPO / "dags").is_dir():
        print(f"ERROR: {REPO / 'dags'} not found", file=sys.stderr)
        return 2
    dag_ids = argv[1:] or discover()
    results = [check_dag(d) for d in dag_ids]
    for r in results:
        print(f"[{r.status:<4}] {r.dag_id}")
        for e in r.errors:
            print(f"        x {e}")
        for w in r.warnings:
            print(f"        ! {w}")
    counts = {s: sum(r.status == s for r in results) for s in ("OK", "WARN", "FAIL")}
    print(f"\nSummary: {counts['OK']} OK · {counts['WARN']} WARN · {counts['FAIL']} FAIL ({len(results)} DAGs)")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
