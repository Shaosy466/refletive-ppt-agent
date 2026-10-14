# Third-party notices

This repository's MIT license covers its original harness code and documentation. It does not override dependencies' licenses, source paper rights, or data download terms.

- **PPTBench** — https://github.com/Einsia/PPTBench, commit `d64c09f10a4376fa46532dc82048d1b5228e8b76`, MIT, copyright 2026 PPTBench Authors. Downloaded separately by bootstrap; its LICENSE and DATA_LICENSE.md remain in vendor/PPTBench. The harness imports its rendering, validation, prompts, schemas and scoring code rather than distributing a modified copy of its implementation. Exported judge schemas in schemas/Gate.json and schemas/Detail.json are derived from PPTBench; its full notice is included in licenses/PPTBench-MIT.txt.
- **Scientific figures and resources** — materialized from upstream-approved sources. Governed by source-paper permissions and PPTBench DATA_LICENSE.md, not the harness MIT license. No benchmark images are included in this repository.
- **Python dependencies, Codex CLI and LibreOffice** — separately installed and subject to their respective terms. Their installation does not grant model access or transfer ownership of third-party fonts.
