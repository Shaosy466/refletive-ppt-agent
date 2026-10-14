#!/bin/sh
# Read-only upstream protocol; requires a running Docker-compatible Linux environment.
# The source archive must already exist in upstream .cache/arxiv-sources.
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
docker run --rm --platform linux/amd64 \
  -v "$project_root:/work" -w /work/vendor/PPTBench \
  python:3.12-slim sh -c 'pip install -q PyMuPDF==1.28.0 Pillow==12.1.1 certifi && PYTHONPATH=src python -m arxiv_flow_dataset.task_materializer --task-id task_0017 --output-root ../../data/pptbench-tasks --offline --resume --accept-arxiv-terms'
