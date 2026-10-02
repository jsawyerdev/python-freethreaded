"""Summarise results.jsonl from run.sh: medians across rounds, relative to the GIL build."""

import json
import statistics
import sys
from collections import defaultdict


def main(path: str) -> None:
    rows = [json.loads(line) for line in open(path, encoding="utf-8")]
    by_image: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_image[row["image"]].append(row)
    baseline = next(img for img, rs in by_image.items() if not rs[0]["free_threaded"])
    names = list(rows[0]["single_thread_s"])

    def median(image: str, section: str, key: str) -> float:
        return statistics.median(r[section][key] for r in by_image[image])

    for image in by_image:
        ratios = [
            median(image, "single_thread_s", n) / median(baseline, "single_thread_s", n)
            for n in names
        ]
        print(image)
        for name, ratio in zip(names, ratios, strict=True):
            ms = median(image, "single_thread_s", name) * 1000
            print(f"  {name:8} {ms:7.1f} ms  {(ratio - 1) * 100:+6.1f}%")
        print(
            f"  geomean vs GIL build: {(statistics.geometric_mean(ratios) - 1) * 100:+.1f}%"
        )
        one = median(image, "scaling_s", "1")
        speedups = {
            t: one / median(image, "scaling_s", t) for t in ("1", "2", "4", "8")
        }
        print("  threads:", "  ".join(f"{t}: x{s:.2f}" for t, s in speedups.items()))
        mem = {m: median(image, "memory", m) for m in by_image[image][0]["memory"]}
        print("  peak RSS MiB:", mem)


if __name__ == "__main__":
    main(sys.argv[1])
