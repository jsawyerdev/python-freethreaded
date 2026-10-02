#!/bin/bash
# Run bench.py in three CPython 3.14.8 images, three rounds, rotating the order so drift
# on the host does not favour one image. Writes results.jsonl next to this script.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
gil=python:3.14.8-slim
ft_gcc14=ghcr.io/jsawyerdev/python:3.14.8t-slim-trixie
ft_gcc16=ghcr.io/jsawyerdev/python:3.14.8t-ubuntu26.04-gcc16.2.0
: > "$here/results.jsonl"
for round in 1 2 3; do
  case $round in
    1) order=("$gil" "$ft_gcc14" "$ft_gcc16") ;;
    2) order=("$ft_gcc14" "$ft_gcc16" "$gil") ;;
    3) order=("$ft_gcc16" "$gil" "$ft_gcc14") ;;
  esac
  for image in "${order[@]}"; do
    docker run --rm -v "$here:/bench:ro" "$image" python /bench/bench.py \
      | python3 -c 'import json, sys; d = json.load(sys.stdin); d["image"] = sys.argv[1]; d["round"] = int(sys.argv[2]); print(json.dumps(d))' "$image" "$round" \
      >> "$here/results.jsonl"
  done
done
python3 "$here/summarize.py" "$here/results.jsonl"
