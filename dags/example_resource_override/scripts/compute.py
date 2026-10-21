"""CPU-bound helper used by the example_resource_override DAG."""


def sum_of_squares(n: int) -> int:
    """Sum of squares 0..n*1000 (just enough work to watch the pod in kubectl top)."""
    limit = max(n, 1) * 1000
    return sum(i * i for i in range(limit))
