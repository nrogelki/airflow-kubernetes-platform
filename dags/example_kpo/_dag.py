"""example_kpo — run a step in a DEDICATED image with KubernetesPodOperator (KPO).

The task pod (Airflow image) does not do the work itself: it asks the Kubernetes API
to create a SIBLING pod with another image (another Python, libraries, compilers...),
waits for it, streams its logs and deletes it. The result travels through
files/<dag_id>/, and the rest of the pipeline goes back to the standard
external_python + p313. Details and evidence: docs/14-imagenes-dedicadas-kpo.md

Two ways to define the sibling pod:
  - extract_other_image:       everything in the KPO arguments (image, cmds, volumes).
  - extract_with_pod_template: a YAML base (k8s/pod_templates/example_kpo_pod.yaml) with a
                               native sidecar + in-memory volume (the Kerberos-like shape);
                               the KPO arguments are applied on top of it.

RBAC: creating a pod needs permission. KPO_LAUNCHER gives ONLY these task pods the
worker ServiceAccount, so this DAG works with and without RBAC (see README.md).
"""

import pendulum
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.sdk import dag, task
from kubernetes.client import models as k8s

DAG_ID = "example_kpo"
PYTHON_ENV = "/opt/conda/envs/p313/bin/python"
PROJECT_PATH = "/opt/airflow-platform"  # HOST path of the repo (hostPath volumes)
FILES = f"/opt/airflow/files/{DAG_ID}"
# A public image, pulled once from Docker Hub. In production, build your own image,
# import it into containerd and use image_pull_policy="Never" (docs/14 §2).
# A Python different from the Airflow image (3.12) on purpose, to make the switch visible.
DEDICATED_IMAGE = "python:3.11-slim"

# Task pod (the one running the operator) -> worker ServiceAccount, which may create
# pods. Required when the cluster enforces RBAC; harmless when it does not. Affects only
# the tasks that use it; the global pod_template is untouched.
KPO_LAUNCHER = {
    "pod_override": k8s.V1Pod(
        spec=k8s.V1PodSpec(
            service_account_name="airflow-worker",  # <HELM_RELEASE>-worker
            containers=[k8s.V1Container(name="base")],
        )
    )
}

# The sibling pod only sees what you mount: files/ so it can hand over its result.
FILES_VOLUME = k8s.V1Volume(
    name="files", host_path=k8s.V1HostPathVolumeSource(path=f"{PROJECT_PATH}/files", type="Directory")
)
FILES_MOUNT = k8s.V1VolumeMount(name="files", mount_path="/opt/airflow/files")

OTHER_IMAGE_SCRIPT = f"""
import os, platform
os.makedirs("{FILES}", exist_ok=True)
open("{FILES}/other_image.txt", "w").write(f"python={{platform.python_version()}}")
print("written by python", platform.python_version())
"""

TEMPLATE_SCRIPT = f"""
import os, platform
token = open("/shared/token").read()  # left by the sidecar defined in the YAML template
os.makedirs("{FILES}", exist_ok=True)
open("{FILES}/with_template.txt", "w").write(
    f"python={{platform.python_version()}} from_template={{os.environ['FROM_TEMPLATE']}} token={{token}}")
print("sidecar token:", token)
"""


@task.external_python(python=PYTHON_ENV, expect_airflow=True)
def read_results(files_dir: str) -> dict:
    import sys

    other = open(f"{files_dir}/other_image.txt").read()
    templated = open(f"{files_dir}/with_template.txt").read()
    assert other.startswith("python=3.11") and "token=ok" in templated, (other, templated)
    return {"p313_python": sys.version.split()[0], "other_image": other, "with_template": templated}


@dag(
    dag_id=DAG_ID,
    description="KubernetesPodOperator: a step in another image, with and without a pod template",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["example", "kpo"],
)
def example_kpo():
    common = dict(
        namespace="airflow",
        image=DEDICATED_IMAGE,
        image_pull_policy="IfNotPresent",
        volumes=[FILES_VOLUME],
        volume_mounts=[FILES_MOUNT],
        security_context=k8s.V1PodSecurityContext(run_as_user=50000, run_as_group=0),  # same UID as Airflow
        container_resources=k8s.V1ResourceRequirements(
            requests={"cpu": "100m", "memory": "128Mi"}, limits={"cpu": "500m", "memory": "512Mi"}
        ),
        get_logs=True,
        on_finish_action="delete_pod",
        executor_config=KPO_LAUNCHER,
    )

    other_image = KubernetesPodOperator(
        task_id="extract_other_image", cmds=["python", "-c", OTHER_IMAGE_SCRIPT], **common
    )
    with_template = KubernetesPodOperator(
        task_id="extract_with_pod_template",
        # Read by the TASK pod: it lives in k8s/pod_templates/ (mounted at /opt/airflow/pod_templates).
        pod_template_file="/opt/airflow/pod_templates/example_kpo_pod.yaml",
        cmds=["python", "-c", TEMPLATE_SCRIPT],
        **common,
    )

    [other_image, with_template] >> read_results(FILES)


example_kpo()
