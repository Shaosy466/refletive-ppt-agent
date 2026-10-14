# Refletive PPT Agent

A Codex-driven harness for reconstructing PPTBench scientific diagrams as **native, editable, single-slide PowerPoint files**. It generates Python code, builds and renders the PPTX, evaluates the rendered result in three rounds, then diagnoses and repairs defects within a bounded budget.

所有智能阶段统一通过 **Codex CLI** 调用。默认 `gpt-6-astra / high`，可配置你自己的 Codex 账号或 provider 支持的模型。仅安装 Codex 不够：所选模型必须支持图像输入、工具执行及结构化输出，并拥有访问权限。项目不提供模型账号、额度或密钥。

## Requirements / 环境

- Python **3.12** recommended; project requires Python 3.11+.
- Git and an installed, authenticated **Codex CLI** with `codex exec`, `--image`, `--output-schema`, `--ephemeral` support. Tested with CLI 0.160.0. See [Codex CLI](https://developers.openai.com/codex/cli/).
- LibreOffice Impress / `soffice` for rendering.
- macOS was tested end to end. Linux and Windows **WSL2** are intended environments but have not completed end-to-end validation. Native Windows is unsupported (POSIX locks/process groups are used).

macOS: `brew install python@3.12 git` and `brew install --cask libreoffice`.
Linux/WSL2: install Python with venv support, Git, LibreOffice Impress and suitable fonts using your distribution's package manager. Font availability affects output; proprietary macOS fonts are not included.

## Install / 安装

```bash
git clone https://github.com/Shaosy466/refletive-ppt-agent.git
cd refletive-ppt-agent
python3.12 -m venv .venv
source .venv/bin/activate
python scripts/bootstrap.py
```

Bootstrap fetches PPTBench at the pinned commit and installs both packages in editable mode. By default it resolves dependencies for your platform. To recreate the tested macOS dependency versions, use `python scripts/bootstrap.py --locked` instead; the lock may not be portable to every Python/OS combination.

This is a source-checkout installation: keep `configs/`, `prompts/`, `schemas/` and `vendor/` beside `src/`. Standalone wheel installation is not supported.

## Configure your Codex model / 配置模型

```bash
cp configs/default.toml config.local.toml
```

Edit these fields in `config.local.toml`:

```toml
[agent]
executable = "codex"
model = "gpt-6-astra"
reasoning_effort = "high"
```

Replace the model ID with one available to your own Codex account/provider. All intelligent roles use this same configuration. Effort values accepted by this harness are `minimal`, `low`, `medium`, `high`, `xhigh`; not every model supports every value. Unsupported combinations fail explicitly, with no silent model substitution. Authentication/provider settings are inherited from your local Codex installation; the harness does not change global settings.

```bash
ppt-harness doctor --config config.local.toml
# Optional: makes a real model call to check image reading, structured output and tool writes
ppt-harness doctor --config config.local.toml --agent-probe
```

New results use `codex_internal_v1` and record the requested model/effort. The historical Astra tests used `astra_internal_v1`. A recorded requested model is not independent proof of a provider's backend identity. Scores from different configurations should be treated as different experiments.

## Run a new benchmark task / 测试新题

Example: `task_0021` is in the frozen upstream task set.

```bash
# --accept-arxiv-terms acknowledges the upstream download terms
ppt-harness materialize --config config.local.toml \
  --task task_0021 --accept-arxiv-terms --resume
ppt-harness run --config config.local.toml --task task_0021
```

On macOS, prefix the run command with `caffeinate -ims` to prevent automatic sleep. Runs make real Codex calls and consume your provider's quota. Defaults: at most 4 candidates, 3 judge rounds per valid candidate, threshold 90, 64 agent calls and 4 hours per task, 15 minutes per agent call. Increase `agent.call_timeout_seconds` to 1800 for the timeout used by the development batch.

To list available task IDs:

```bash
python -c 'import json; from pathlib import Path; print("\n".join(json.loads(s)["task_id"] for s in Path("vendor/PPTBench/benchmark/materialization_manifest.jsonl").read_text().splitlines()))'
```

For multiple tasks, create a text file with one task ID per line, and replace `--task task_0021` with `--task-file your-tasks.txt` in both materialize and run. Default execution is serial. `configs/dev-batch.toml` allows 3 concurrent tasks/agents and serial rendering; configure your model there before using it.

Materialization verifies official frozen hashes. Retry download failures with `--resume`; never change a hash to bypass verification. In our tests `task_0017` required Linux x86_64 materialization for exact reference pixels. `scripts/check_reference_linux.sh` is an optional Docker helper, not a requirement for other tasks.

## Results, inspect and resume / 结果与恢复

The CLI prints `RUN_DIR=...`. Outputs are stored under:

```text
runs/<run_id>/tasks/<task_id>/final/
  reconstruction.pptx
  screenshot.png
  source.zip
  result.json
```

Look at `quality_pass`, `evaluation_complete`, `internal_score` and `stop_reason`. A valid PPT can exist even when evaluation is incomplete. Incomplete scores are null, not zero. A semantic gate failure can produce zero even for a visually plausible PPT. Normal command completion does not imply quality pass; use `--require-quality-pass` to require that in the exit status.

```bash
ppt-harness resume --run-id <run_id>
ppt-harness report --run-id <run_id>
# Detection only: compare an existing single-slide PPTX against a materialized benchmark task
ppt-harness inspect --config config.local.toml --task task_0021 \
  --pptx /absolute/path/reconstruction.pptx
```

Resume uses the run's frozen configuration. Do not change code, prompts, models or environment during a run. Completed checkpoints avoid repeated paid calls. After environment changes, `replay --from-run <run_id> --config config.local.toml` creates a new run reusing verified generation while redoing rendering/evaluation. Replay requires the original model/effort. `--recover-compatible` additionally preserves verified evaluation stages only when the relevant environment matches; prefer ordinary resume.

Current inputs must come from the frozen PPTBench task manifest. Arbitrary personal reference images and slide-deck authoring from text are not implemented. `inspect` evaluates but does not repair the supplied PPTX.

## Architecture / 数据如何连接

The Python controller passes files between independent Codex sessions:

```text
reference + approved assets → diagram-spec.json → build.py
→ reconstruction.pptx → native validation + LibreOffice rendering
→ screenshot.png → three-round findings + official deterministic scoring
→ feedback.json → revised source → rebuild and re-evaluate
```

Prompts live in `prompts/`; official judge prompts/schemas/scoring are loaded from the pinned upstream. Candidate directories preserve source, render, object maps, raw judgments and per-call prompt/schema/JSONL/stderr. Best-candidate selection rolls back regressions; budgets and no-improvement limits stop the loop. Do not publicly share raw run logs without reviewing them for local paths and tool output.

## Validation and limitations / 实测与边界

Historical local-dev experiment: **10 distinct tasks attempted, 7 quality passes, 1 evaluated quality failure, 2 incomplete**. Thus 70% achieved the internal target across all attempts, or 87.5% among the 8 completed evaluations. This small development set is not a full benchmark result. A controlled reversed-arrow experiment verified detection, repair and the actual repaired OOXML endpoint. See [VALIDATION.md](VALIDATION.md) for details; raw runs/data are intentionally not published.

- Scores are internal model judgments, **not official PPTBench paper scores**. Local rendering used LibreOffice 26.8 rather than the paper's version. `official_comparable=false`.
- `local-dev` is the only supported mode. Codex workspace-write is not full read isolation. The planned Linux Bubblewrap benchmark environment is not implemented; `benchmark` mode fails explicitly.
- Local Codex plugins/instructions can affect runs. Generated code executes locally; use a separate development environment if you need stronger isolation.
- Known issues include invalid model-generated bounding boxes and provider timeouts. The harness records failures rather than claiming success. Arbitrary-image import, independent official Luna export and a unified run-level event stream are not implemented.
- Source/runtime changes invalidate old resume fingerprints. Historical results stay historical; do not overwrite them to match a new protocol.

The [original implementation specification](IMPLEMENTATION_SPEC.md) is a historical design, not a statement that all planned interfaces are implemented. README describes the delivered scope.

## Development

```bash
python -m pytest -q
python -m pip check
```

Tests use local fixtures/mocked calls and actual LibreOffice rendering; they do not make paid model calls. Real model experiments are separate and are not automatically launched on installation.

## License and upstream

Project code: [MIT](LICENSE), copyright 2026 Shaosy466. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

PPTBench: https://github.com/Einsia/PPTBench, pinned commit `d64c09f10a4376fa46532dc82048d1b5228e8b76`. Bootstrap downloads it with its own MIT license and data terms intact. Scientific figures and assets retain their original rights; this repository's MIT license does not relicense them. No dataset, credentials, vendor checkout or generated PPT is bundled.

Framework inspiration: https://github.com/jiangjin1999/awesome-multimodal-agentic-coding .

## Multimodal adapters (development)

An incremental multi-benchmark entry point is available as `reflective-harness`.
Run `reflective-harness list` to inspect implemented versus blocked adapters.
See [multimodal usage and limitations](docs/MULTIMODAL_USAGE.md). The new local
profiles are not official leaderboard reproductions; catalog entries do not
imply runnable benchmark support. Existing `ppt-harness` commands remain valid.

## Continue development on a server

Start with [the server Codex handoff](docs/SERVER_CODEX_HANDOFF.md). It contains
repository orientation, Linux setup, exact next tasks for EditHero and Code4Scene,
acceptance criteria, known reliability gaps, and a copyable Codex starting prompt.
Historical smoke summaries are in [validation/](validation/multimodal-smoke-20261014.json);
full local runs, datasets, vendor code and credentials are not included in Git.
