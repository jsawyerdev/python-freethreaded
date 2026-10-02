"""Micro-benchmarks for CPython builds: single-thread speed, threads, memory.

Prints one JSON object. Standard library only, so it runs unchanged in any image.
"""

import json
import statistics
import subprocess
import sys
import sysconfig
import threading
import time
from dataclasses import dataclass

REPEATS = 7


def bench_loop() -> None:
    total = 0
    for i in range(3_000_000):
        total += i


def _add(a: int, b: int) -> int:
    return a + b


def bench_calls() -> None:
    x = 0
    for i in range(1_500_000):
        x = _add(x, i)


def bench_dict() -> None:
    keys = [f"key{i}" for i in range(100_000)]
    for _ in range(5):
        d = {k: i for i, k in enumerate(keys)}
        for k in keys:
            d[k] += 1


def bench_float() -> None:
    x, y, vx, vy = 1.0, 0.0, 0.0, 1.0
    for _ in range(600_000):
        r3 = (x * x + y * y) ** 1.5
        vx -= x / r3 * 0.001
        vy -= y / r3 * 0.001
        x += vx * 0.001
        y += vy * 0.001


def bench_strings() -> None:
    parts = [f"{i}:{i * 2:x}" for i in range(300_000)]
    ",".join(parts).split(",")


@dataclass(slots=True)
class Point:
    x: int
    y: int


def bench_objects() -> None:
    points = [Point(i, i) for i in range(400_000)]
    sum(p.x + p.y for p in points)


SINGLE = {
    "loop": bench_loop,
    "calls": bench_calls,
    "dict": bench_dict,
    "float": bench_float,
    "strings": bench_strings,
    "objects": bench_objects,
}


def timed(fn) -> float:
    start = time.perf_counter()
    fn()
    return time.perf_counter() - start


def cpu_work(n: int) -> None:
    total = 0
    for i in range(n):
        total += i * i % 7


def scaling(total_iters: int = 16_000_000) -> dict[str, float]:
    """Wall time for a fixed total amount of work split across N threads."""
    out = {}
    for n in (1, 2, 4, 8):
        per = total_iters // n
        runs = []
        for _ in range(3):
            threads = [threading.Thread(target=cpu_work, args=(per,)) for _ in range(n)]
            start = time.perf_counter()
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            runs.append(time.perf_counter() - start)
        out[str(n)] = round(statistics.median(runs), 3)
    return out


MEMORY_CASES = {
    "start": "pass",
    "1m_floats": "x = [float(i) for i in range(1_000_000)]",
    "300k_dicts": "x = [{'a': i, 'b': i} for i in range(300_000)]",
    "1m_slots_objects": (
        "class P:\n    __slots__ = ('x',)\n    def __init__(self, x): self.x = x\n"
        "x = [P(i) for i in range(1_000_000)]"
    ),
}


# VmHWM is the peak RSS of this address space. ru_maxrss survives execve on Linux,
# so a child would report the parent's peak instead of its own.
PEAK_RSS = (
    "\nfor line in open('/proc/self/status'):\n"
    "    if line.startswith('VmHWM:'):\n"
    "        print(line.split()[1])"
)


def memory() -> dict[str, float]:
    """Peak RSS in MiB of a fresh interpreter per case, so cases share no memory."""
    out = {}
    for name, code in MEMORY_CASES.items():
        proc = subprocess.run(
            [sys.executable, "-c", code + PEAK_RSS],
            capture_output=True,
            text=True,
            check=True,
        )
        out[name] = round(int(proc.stdout) / 1024, 1)
    return out


def main() -> None:
    results = {}
    for name, fn in SINGLE.items():
        fn()  # warm-up: lets the specializing interpreter settle
        results[name] = round(statistics.median(timed(fn) for _ in range(REPEATS)), 4)
    print(
        json.dumps(
            {
                "version": sys.version.split()[0],
                "compiler": sys.version.split("[")[-1].rstrip("]"),
                "free_threaded": bool(sysconfig.get_config_var("Py_GIL_DISABLED")),
                "single_thread_s": results,
                "scaling_s": scaling(),
                "memory": memory(),
            }
        )
    )


if __name__ == "__main__":
    main()
