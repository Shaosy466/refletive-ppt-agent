# 多任务框架：当前可执行版本

这是原 PPT 项目上的增量实现。原 `ppt-harness` 保留。通用入口是 `reflective-harness`；**注册表有条目不表示适配器已完成**。使用 `list`/`doctor` 检查实际能力。

新增四个链接中 Code4Scene 已在原六项内，因此去重后为九个新 benchmark，加 PPTBench 共十项。新增的三个是 EditHero、Witness、LongPuzzleBench。

## 安装

新服务器请先按 [服务器交接文档](SERVER_CODEX_HANDOFF.md) 创建环境并运行 `scripts/bootstrap.py`，再完成源代码 editable 安装与 Codex 登录。所有模型调用仍通过已有 Codex CLI，不需要改用 SDK。

```bash
python -m pip install -e ".[multimodal]"
python scripts/fetch_benchmark_source.py LongPuzzleBench
python -m pip install -e vendor/LongPuzzleBench
```

浏览器开发 profile 当前使用本机 Google Chrome (`channel=chrome`)；仅安装 Playwright Chromium 不能替代这一配置。模型配置在 `configs/multimodal.toml`，默认 Astra/high。只写当前账号 Codex 可用的模型 ID。

上游代码和数据不随我们的仓库重新分发。固定版本记录在 `configs/benchmark-sources.lock.json`。下载工具保留已有目录，不覆盖本地修改：

```bash
python scripts/fetch_benchmark_source.py LongPuzzleBench
python scripts/fetch_benchmark_source.py GameDevBench
python scripts/fetch_benchmark_source.py SciVisAgentBench
python scripts/fetch_benchmark_source.py EditHero
python scripts/fetch_smoke_data.py a2z
python scripts/fetch_smoke_data.py edithero
```

GameDevBench 完整仓库约 1.4 GB 未压缩；本次开发只取得源码和 task_0002，lock 记录了 sparse_files。通用下载脚本下载整个指定提交。

## 查询和运行

```bash
reflective-harness list
reflective-harness doctor --benchmark longpuzzlebench
reflective-harness tasks --benchmark longpuzzlebench
reflective-harness run --benchmark longpuzzlebench \
  --task bolt_unscrew.easy.level_01.seed_0 --max-steps 12

# 设置 Godot 4.4.1 原生可执行文件路径
export GODOT_EXEC_PATH=/absolute/path/to/Godot
reflective-harness run --benchmark gamedevbench --task task_0002

reflective-harness run --benchmark scivisagentbench --task shrink-sphere
reflective-harness run --benchmark a2z --task small/bin_bit
reflective-harness run --benchmark edithero --task A/1a3267df_s0

# 原有 PPT 命令继续使用原有配置
ppt-harness run --task task_0004
```

可以指定 `--config configs/multimodal.toml` 和全新的 `--output runs/my-run`。不要把已完成 run 目录当成新运行目录。CLI 的 `status=complete` 表示执行及配置的评价完成，不表示质量通过。检查 `evaluation.metrics` 或 LongPuzzle 的 `task_success`。

## 两种循环

产物任务：公开任务 → Codex 编写/修改 → 候选快照 → 在副本执行/渲染 → Codex 根据真实证据诊断 → 修复或补采证据 → 冻结提交 → 独立最终评价。

交互任务：上游环境 reset → 截图 → Codex 输出观察、诊断、短记忆与一次 GUI 动作 → 上游执行动作 → 新截图。LongPuzzle 使用上游单关 runner、终止判断、轨迹和评分器。Codex 的同步回调在独立线程中调用异步 CLI runner，避免与 Playwright 的事件循环冲突。

`contracts.py` 定义 Task、Execution、Evidence、Review、Evaluation。大图/视频/场景留在磁盘，JSON 传相对路径、SHA256、candidate ID。产物源码快照在 `candidates/`，执行副本在 `stages/*/execution/`，模型输入输出在各角色 `.harness/`。观察者读取当前 candidate，而不是初始项目。

作者 prompt 包含公开题目、产物合同、上一轮公开反馈。观察者 prompt 包含同一公开题目、当前源码、截图和日志。Finding 的 evidence 字段只能使用 manifest 内准确的文件名。最终 evaluator 不把结果传回作者。本次 GameDev 失败后没有根据隐藏测试修复或重挑版本。

## 扩展方式

外部 Python 包通过 entry point `reflective_harness.adapters` 注册 factory(root)。实现 `doctor`、`prepare`、`execute`、`evaluate`，数据接口见 `contracts.py`。具体领域逻辑写在插件，通用控制器不判断 PPTX/Godot/HTML 的内部结构。

- `prepare` 只复制公开输入；GT、rubric、测试代码留在 evaluator 一侧。
- `execute` 在执行副本中运行真实工具，输出带哈希的证据。
- `evaluate` 在冻结后使用官方 scorer 或明确命名的内部变体。
- 交互环境可以实现 `run_episode`，复用上游 episode lifecycle。
- `command_adapter.py` 接收可信操作者配置的 argv 数组，提供自定义程序执行和评价扩展点。此接口不能接收模型生成的“评分程序”当作可信裁判。

测试新插件应包含真实小题、错误产物、隐藏数据不进入公开目录、执行超时、证据变更检测。框架单元测试不算 benchmark 题目。

## 当前限制

- **PPT**：仍走成熟的原有 pipeline；没有完成物理模块搬迁。
- **GameDev**：本地 Godot 4.4.1 执行与原始测试；没有 Linux strict confinement，因此不能称 leaderboard comparable。
- **LongPuzzle**：单关 controlled development，非从主菜单开始的完整 autonomous cell。模型可以使用 Codex 工具，协议不能冒称原生 GUI-only。
- **SciVis**：目前只实现 `shrink-sphere` 的 VTK profile；公开任务、实际 PNG、官方四项 rubric 的 Codex 内部评分。不包含全部科学软件、官方图像参考指标或完整 suite 聚合。
- **A2Z**：真 GDD 的离线 HTML/JS 生成与公开浏览器 smoke。没有官方 Phaser starter/三轴 scorer；无官方分数。
- **EditHero**：官方示例链全部五步的本地编辑、VTK 预览和 mesh delivery 检查。不是官方 Blender rig；没有区域质量/保持性评分。
- **4DCodeBench**：已锁定源码；缺 NVIDIA Linux worker、数据/模型检查点以及完整执行适配，未跑题。
- **Code4Scene**：已锁定源码，公开树含 T2S/I2S 定义（README 与 PACKS 文档数量有差异）；缺 UE 5.8、对应 Fab 素材及执行 worker，未跑题。
- **Witness**：论文主协议是 ASCII、六动作、禁止代码执行；尚未取得可验证的官方 validation SDK。网站可玩不等于实现论文协议。未跑题。
- **IChart2Code**：尚未核实官方任务包/代码，未跑题。

所有新运行均 `official_comparable=false`。本地目录分离与 prompt 边界不是 OS 隔离；Codex workspace-write 不等于无法读取宿主其他目录。正式比较仍需要容器/远端 worker 的访问隔离。通用 GPU/UE worker 尚未实现。

## 恢复边界

```bash
reflective-harness resume --run runs/<artifact-run>
```

目前只恢复已经完成 `execution.json` 的产物阶段，验证候选和证据哈希后继续诊断。已完成 run 直接返回原结果并校验提交。中途引擎状态、冻结后评分中断、交互 episode 的自动恢复尚未实现，明确拒绝而不盲目重放。模型配置和公开任务发生变化时必须新建 run。历史 PPT 的恢复机制不变。
