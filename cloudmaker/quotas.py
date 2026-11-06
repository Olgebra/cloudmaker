"""Квоты vCPU и памяти на одну виртуальную машину."""

from __future__ import annotations


class QuotaError(Exception):
    """Запрос превышает max_vcpus или max_memory_mb."""


def assert_within_quota(
    vcpus: int,
    memory_mb: int,
    max_vcpus: int,
    max_memory_mb: int,
) -> None:
    if vcpus > max_vcpus:
        raise QuotaError(
            "Превышена квота CPU: запрошено "
            + str(vcpus)
            + ", максимум "
            + str(max_vcpus)
        )
    if memory_mb > max_memory_mb:
        raise QuotaError(
            "Превышена квота RAM: запрошено "
            + str(memory_mb)
            + " МиБ, максимум "
            + str(max_memory_mb)
            + " МиБ"
        )
