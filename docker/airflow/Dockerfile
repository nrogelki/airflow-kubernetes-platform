# syntax=docker/dockerfile:1
# -----------------------------------------------------------------------------
# Immutable Airflow image for the KubernetesExecutor.
#
# Contains the Airflow core + the integrations needed at parse/orchestration
# time (providers, hooks). Data libraries for task code (pandas, polars,
# drivers...) are NOT added here: they live in the isolated Conda environment
# mounted into the task pods (envs/). See
# docs/adr/0003-entornos-aislados-external-python.md
#
# Some providers pull data libraries in as their own dependencies (e.g. the
# Hive provider brings pandas). Those copies belong to this image's interpreter
# and are only used by the providers themselves: @task.external_python code runs
# in the isolated env, with its own (independent) versions.
#
# Build with: make build   (reads versions from config/platform.env)
# -----------------------------------------------------------------------------
ARG AIRFLOW_VERSION=3.2.1
ARG PYTHON_VERSION=3.12
FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}

ARG AIRFLOW_VERSION
ARG PYTHON_VERSION

LABEL org.opencontainers.image.title="airflow-k8s-base" \
      org.opencontainers.image.description="Apache Airflow image for KubernetesExecutor on MicroK8s" \
      org.opencontainers.image.licenses="Apache-2.0"

COPY requirements.txt /tmp/requirements.txt

# Pinning apache-airflow in the same command + official constraints prevents
# pip from silently upgrading/downgrading Airflow while resolving providers.
RUN pip install --no-cache-dir \
      "apache-airflow==${AIRFLOW_VERSION}" \
      -r /tmp/requirements.txt \
      --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"
