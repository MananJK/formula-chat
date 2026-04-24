import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

_metrics_lock = asyncio.Lock()


@dataclass
class Metrics:
    sql_cache_hits: int = 0
    sql_cache_misses: int = 0
    embedding_cache_hits: int = 0
    embedding_cache_misses: int = 0
    
    sql_latencies_ms: list[float] = field(default_factory=list)
    embedding_latencies_ms: list[float] = field(default_factory=list)
    rag_search_latencies_ms: list[float] = field(default_factory=list)
    
    total_requests: int = 0
    
    _last_reset: float = field(default_factory=time.time)

    def reset(self) -> None:
        self.sql_cache_hits = 0
        self.sql_cache_misses = 0
        self.embedding_cache_hits = 0
        self.embedding_cache_misses = 0
        self.sql_latencies_ms.clear()
        self.embedding_latencies_ms.clear()
        self.rag_search_latencies_ms.clear()
        self.total_requests = 0
        self._last_reset = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "sql_cache_hits": self.sql_cache_hits,
            "sql_cache_misses": self.sql_cache_misses,
            "sql_cache_hit_rate": self._hit_rate(self.sql_cache_hits, self.sql_cache_misses),
            "embedding_cache_hits": self.embedding_cache_hits,
            "embedding_cache_misses": self.embedding_cache_misses,
            "embedding_cache_hit_rate": self._hit_rate(self.embedding_cache_hits, self.embedding_cache_misses),
            "avg_sql_latency_ms": self._avg(self.sql_latencies_ms),
            "avg_embedding_latency_ms": self._avg(self.embedding_latencies_ms),
            "avg_rag_search_latency_ms": self._avg(self.rag_search_latencies_ms),
            "p50_sql_latency_ms": self._percentile(self.sql_latencies_ms, 50),
            "p95_sql_latency_ms": self._percentile(self.sql_latencies_ms, 95),
            "p50_embedding_latency_ms": self._percentile(self.embedding_latencies_ms, 50),
            "p95_embedding_latency_ms": self._percentile(self.embedding_latencies_ms, 95),
            "total_requests": self.total_requests,
            "uptime_seconds": time.time() - self._last_reset,
        }

    @staticmethod
    def _hit_rate(hits: int, misses: int) -> float:
        total = hits + misses
        return round(hits / total * 100, 1) if total > 0 else 0.0

    @staticmethod
    def _avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 2) if values else 0.0

    @staticmethod
    def _percentile(values: list[float], p: int) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        idx = int(len(sorted_vals) * p / 100)
        return round(sorted_vals[min(idx, len(sorted_vals) - 1)], 2)


metrics = Metrics()


async def increment_sql_cache_hit() -> None:
    async with _metrics_lock:
        metrics.sql_cache_hits += 1


async def increment_sql_cache_miss() -> None:
    async with _metrics_lock:
        metrics.sql_cache_misses += 1


async def increment_embedding_cache_hit() -> None:
    async with _metrics_lock:
        metrics.embedding_cache_hits += 1


async def increment_embedding_cache_miss() -> None:
    async with _metrics_lock:
        metrics.embedding_cache_misses += 1


async def record_sql_latency(latency_ms: float) -> None:
    async with _metrics_lock:
        metrics.sql_latencies_ms.append(latency_ms)


async def record_embedding_latency(latency_ms: float) -> None:
    async with _metrics_lock:
        metrics.embedding_latencies_ms.append(latency_ms)


async def record_rag_search_latency(latency_ms: float) -> None:
    async with _metrics_lock:
        metrics.rag_search_latencies_ms.append(latency_ms)


async def increment_total_requests() -> None:
    async with _metrics_lock:
        metrics.total_requests += 1


def get_metrics() -> dict[str, Any]:
    return metrics.to_dict()


def reset_metrics() -> None:
    metrics.reset()