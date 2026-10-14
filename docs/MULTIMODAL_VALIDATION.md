# 多任务小样本验收（2026-10-14）

本轮只测试每个已接入数据集的一道真实题目，不做全量评测。四个新增链接里 Code4Scene 重复，因此目标集合是九个新增 benchmark，加原 PPT。

**目前不是十项全部完成。** 运行成功、任务成功、内部评分、官方可比性分别记录；不跨 benchmark 平均分数。所有新运行 `official_comparable=false`。

## LongPuzzleBench：成功

- 题目：`bolt_unscrew.easy.level_01.seed_0`。
- 结果：上游 `task_success=true`，原始 `game_score=1.0`，`termination_reason=success`。
- Astra + Codex + high，3 次调用。
- 路径：`runs/multi-smoke-longpuzzle-002/result.json`；完整截图/动作轨迹位于同目录 `trajectories/`。
- 这是 controlled 单关，不是论文自主选择游戏、难度并解完整 cell 的分数。
- 首次启动暴露同步 Playwright 内调用 asyncio.run 的错误（0 次模型调用）；修复为独立线程调用后重测同题成功。首次错误不是模型解题失败。

## GameDevBench：流程完成，官方测试未通过

- 题目：`task_0002`，Projectile Step Tracker。
- 原生 Godot 4.4.1 导入、运行、电影 PNG 渲染均成功。
- 原始测试返回：`Projectile must react to enemies inside _on_area_entered`；binary pass=0。
- 路径：`runs/multi-smoke-gamedev-001/result.json`、`evaluation/test.stdout.log`。
- 测试文件在公开工作区被移除，冻结提交后再覆盖回原始测试；没有根据最终隐藏测试结果修复或选择另一个候选。
- 上游原始未解决项目负例失败、上游 GT 正例通过：`runs/gamedev-control-tasks/result.json` 和 `runs/gamedev-control-tasks_gt/result.json`。这是验证器控制实验，不算额外 agent 解题次数。
- macOS 本地开发，未实施 Linux strict confinement。

## SciVisAgentBench：本地流程成功，内部 rubric 8.25/10

- 题目：官方 `shrink-sphere`。
- 生成 Python/VTK 产物，实际执行生成 1920×1080 PNG；公开视觉检查 done。
- 冻结后独立 Astra/high 根据上游四项视觉 rubric 评分：7、9、9、8，均分 8.25。
- 路径：`runs/multi-smoke-scivis-001/result.json`；图像 `stages/000/evidence/result.png`。
- 3 次作者/观察调用（含修复接口错误后的重试）+1 次最终 judge。模型内部工具调用不等同此计数。
- 不是官方 judge/全 suite 复现；没有计算参考图 PSNR/SSIM/LPIPS，不从单题推导 pass@k。

## A2Z：真题生成与公开行为检查完成，无官方评分

- 题目：`small/bin_bit`（Sort Left or Right），GDD 数据版本 `74343b5fa8522b4167a355bedbe8c004cb7450e2`。
- 生成完整本地 HTML/JS；浏览器离线运行无报错。
- 首轮固定 Enter/方向键都未映射，不能声称验证了游戏。追加公开检查改用 GDD 的 A/L 键，覆盖开始、分类、45 秒结算和重开。
- 追加视觉检查 done：看到了两个正确分类、26 次超时、28 个结算条目与重开归零。这些数字是该游戏内测试会话的统计，**不是 benchmark 正确率**。
- 路径：`runs/multi-smoke-a2z-001/result.json`；追加证据和检查在 `additional-public-check/`。
- 精确计时、音频、手柄和全部输入边界未验证。没有官方三轴 scorer；HTML/JS profile 也偏离官方 Phaser/TypeScript/Vite starter，因此没有官方分数。

## EditHero

执行的是官方示例 `A/1a3267df_s0` 的五步完整链，不将五步算成五道题。只给作者原始 `turn00.glb`、公开指令和 conditioning views；不提供目标 GLB、held-out views、part masks。使用本地 VTK 预览和 GLB 交付校验，不冒称官方区域质量评测。

- 实际结果：5/5 个逐轮 GLB 均可加载，build 和 VTK 渲染退出码均为 0，公开检查 `done`。
- 2 次 Astra + Codex + high 调用（作者 1、观察诊断 1）。
- `build.py` 每一步重新读取自己的上一轮 GLB，确认执行的是 self-rollout。
- 路径：`runs/multi-smoke-edithero-001/result.json`；五步图像在 `stages/000/evidence/turn01.png` 至 `turn05.png`。
- 最终状态仍是 `evaluation_incomplete`，因为交付检查不是官方编辑区域/保持性/外观评分。

## 尚未运行的四个 benchmark

- **4DCodeBench**：源码固定为 `6c466be34107d7f388f30f97bf059b68ba1a21b0`。本机无 NVIDIA Linux worker、CUDA scorer/模型检查点/完整数据，GPU worker adapter 也未完成。没有生成或评分题目。
- **Code4Scene**：源码固定为 `2716e4397f768bf16b1f33dd34680d48aed0601f`。本机无 UE 5.8 和对应 Fab packs；公开任务定义不等于可运行原生场景。没有生成或评分题目。
- **Witness**：读过论文与官方项目网站；未取得可验证的官方 validation SDK/API。其主设置是 ASCII、六动作且禁止代码执行，不能把网页试玩或自造关卡算作论文题目。
- **IChart2Code**：未核实可取得的官方任务数据和 evaluator，GitHub 搜索未发现对应官方仓库。没有用自造图表代替。

这些是阻塞/未实现项，不计为模型做题错误或测试通过。用户已被询问可用远程机器/UE 环境，尚无已配置 worker 可用。

## PPT 与工程回归

原 `ppt-harness` 保留。历史真实测试记录仍见 `VALIDATION.md`，本轮没有把历史 PPT 结果算成新的运行。工程回归包含原 29 项及新增多任务测试，最终 **38 项测试通过**，`pip check` 通过。

新增检查覆盖 registry 去重、公开输入剥离隐藏测试、路径逃逸/符号链接拒绝、候选哈希防篡改、最终分数不进入反馈、断点恢复不重复作者/执行调用、Codex 严格 schema，以及插件目录的 401 警告不误报成模型认证失败。

`python scripts/multimodal_status.py` 只汇总已有结果，不发起新模型调用。

## 本轮汇总

五个新增 benchmark 各尝试一道真实题（EditHero 的五轮属于同一条题目链）。LongPuzzle 解题成功；GameDev 上游测试失败；SciVis 完成本地内部评分；A2Z、EditHero 完成生成/执行/公开诊断，但官方最终评分未完成。另外四项未运行。没有可据此声称的九个 benchmark 总正确率。

代码和本报告随仓库发布；完整运行轨迹仍保留在本地，Git 中仅包含 `validation/multimodal-smoke-20261014.json` 历史摘要。可用部分已实现，完整目标架构（尤其隔离 worker、官方评价齐全和所有任务自动恢复）尚未达到验收条件。
