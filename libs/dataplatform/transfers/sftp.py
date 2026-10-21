"""SFTP transfers resolved from an Airflow Connection (type SFTP/SSH).

Runs inside the isolated environment (requires apache-airflow-providers-sftp).
Downloads land in the DAG data folder (files/<dag_id>/), owned by UID 50000.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from airflow.providers.sftp.hooks.sftp import SFTPHook


def list_matching(conn_id: str, remote_dir: str, pattern: str = "*") -> list[str]:
    """File names in ``remote_dir`` matching a glob ``pattern`` (sorted)."""
    hook = SFTPHook(ssh_conn_id=conn_id)
    return sorted(n for n in hook.list_directory(remote_dir) if fnmatch.fnmatch(n, pattern))


def download_matching(
    conn_id: str, remote_dir: str, pattern: str, local_dir: str, skip_existing: bool = True
) -> list[str]:
    """Download every file matching ``pattern``. Returns local paths (primitives -> XCom-safe)."""
    hook = SFTPHook(ssh_conn_id=conn_id)
    Path(local_dir).mkdir(parents=True, exist_ok=True)
    downloaded = []
    for name in list_matching(conn_id, remote_dir, pattern):
        local_path = os.path.join(local_dir, name)
        if skip_existing and os.path.exists(local_path):
            continue
        hook.retrieve_file(f"{remote_dir.rstrip('/')}/{name}", local_path)
        downloaded.append(local_path)
    print(f"Downloaded {len(downloaded)} file(s) from {remote_dir} ({pattern})")
    return downloaded


def upload_file(conn_id: str, local_path: str, remote_dir: str) -> str:
    """Upload one file; returns the remote path."""
    remote_path = f"{remote_dir.rstrip('/')}/{os.path.basename(local_path)}"
    SFTPHook(ssh_conn_id=conn_id).store_file(remote_path, local_path)
    return remote_path
