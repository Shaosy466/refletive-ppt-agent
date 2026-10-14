# 服务器 Codex 交接：先理解，再继续实现

## 任务与边界

用户要一个可扩展多模态 harness：公开目标 → Codex 编码或动作 → 程序执行/渲染 → Codex 观察与诊断 → 修复或探索 → 冻结产物 → 最终评价。智能阶段默认 Astra + Codex + high，模型可配置，但调用统一通过 Codex CLI。不要换成其他厂商 SDK，也不要把本会话模型当成被测模型。

当前重点：**完善 EditHero，然后接通 Code4Scene**。其他 benchmark 保留现状，不展开全量实验。每个新接入数据集先一道真实题目，完整执行并诚实报告。用户希望自主推进可完成的工作；仅在确实缺机器权限、账号授权、付费素材或必需信息时询问。

本仓库不是全部 benchmark 已完成的产品。不要根据 registry 或 README 的任务清单推断已支持。全部新增结果都是 `official_comparable=false`。本文件是交接任务书；完整目标设计不等于当前实现。

## 十分钟阅读顺序

1. 本文件。
2. `docs/MULTIMODAL_USAGE.md`：实际命令和限制。
3. `docs/MULTIMODAL_VALIDATION.md`、`validation/multimodal-smoke-20261014.json`：已有结果与失败。
4. `src/reflective_harness/contracts.py`、`registry.py`、`adapters.py`、`cli.py`。
5. `controller.py`、`artifacts.py`，然后重点读 `edithero.py`、`mesh_preview.py`。
6. `src/pptbench_harness/codex_runner.py`、`checkpoints.py`：模型调用和预算复用点。
7. `docs/MULTI_BENCHMARK_ARCHITECTURE.md`：完整设计愿景。`IMPLEMENTATION_SPEC.md` 是早期 PPT 专项规范，不是全部新任务的执行标准。

## 仓库地图

- `src/pptbench_harness/`：已发布的 PPT 专用 pipeline，保留旧命令及历史协议；不要为了新适配器破坏它。
- `src/reflective_harness/`：增量通用实现，仍依赖上面的 Codex runner、Budget 和文件工具。
- `controller.py`：artifact 循环，候选快照、执行副本、review、最多一次补采、冻结后 evaluate。
- `contracts.py`：Pydantic 数据合同；`strict_schema()` 将对象所有字段设为 required，以适配 Codex structured output。
- `artifacts.py`：路径和 symlink 检查、SHA256、manifest、快照校验。
- `registry.py`：Python entry points，组名 `reflective_harness.adapters`；factory 接收 repo root。
- `adapters.py`：目录和能力状态，部分条目仅是受阻声明。
- `gamedev.py`：公开项目剥离原始测试，Godot 执行/取帧，冻结后恢复不可修改的原始测试。
- `longpuzzle.py`：复用上游单关 runner；Codex 收截图/公开反馈，输出记忆和 GUI 动作；私有状态留给上游评价。
- `a2z.py`、`browser.py`：GDD→静态离线网页的开发协议；尚非官方 Phaser starter 与三轴评分。
- `scivis.py`：仅 `shrink-sphere` VTK profile，冻结后 Codex 按四项 rubric 内部评价。
- `edithero.py`：仅官方示例链的五步生成；VTK preview；GLB 交付检查，非官方质量评分。
- `command_adapter.py`：可信操作者的 argv 扩展点；不是安全沙箱。
- `configs/multimodal.toml`：新任务配置；`configs/default.toml` 是 PPT 配置，不要互换。
- `configs/benchmark-sources.lock.json`：已核实的上游 commit；vendor/data/runs 全部忽略。
- `scripts/fetch_benchmark_source.py`、`fetch_smoke_data.py`：按固定版本下载。
- `tests/test_multimodal*`：通用合同、恢复、数据分离测试；其余大多是 PPT 回归。

## 在服务器开始：可复制命令

以下假设 Linux、Python 3.12 可用，当前登录用户有仓库目录写权限。先检查机器，缺什么再按实际 OS 安装，不要盲装 CUDA/驱动或修改系统服务。

```bash
git clone https://github.com/Shaosy466/refletive-ppt-agent.git
cd refletive-ppt-agent
git status --short
uname -a
python3.12 --version
command -v codex
codex --version
nvidia-smi  # 没有 NVIDIA GPU 可以失败，先记录即可
```

仓库采用 editable 安装；PPT 上游依赖并未剥离，不能直接跳过 bootstrap 再期待全部测试通过。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python scripts/bootstrap.py
python -m pip install -e '.[dev,multimodal]'
python -m pip check
python -m pytest -q
reflective-harness list
```

不要在 Linux 默认使用 `bootstrap.py --locked`：旧 lock 来自测试过的本机环境，应先按平台解析依赖。Python 3.12 也满足 LongPuzzle 上游的 `<3.13` 限制。bootstrap 从网络取得固定 PPT 上游；网络失败要解决网络或取得同提交，不要伪造通过。

服务器需要独立配置 Codex 登录/已有用户 provider 配置。GitHub 克隆不会带来本机登录。不要打印、提交或要求用户在聊天中发送 token、密码、私钥；不要默认复制 Mac 的配置与凭据。先用 `codex --help` / `codex exec --help` 核对已装版本，确认 `--output-schema`、`--image`、`--ephemeral` 等 runner 参数兼容。仅在必要时做一次低成本能力探针，记录 requested model 与实际可获得的身份信息。

### 下载 EditHero 的当前小样本

```bash
python scripts/fetch_benchmark_source.py EditHero
python scripts/fetch_smoke_data.py edithero
reflective-harness doctor --benchmark edithero
# 以下发起真实模型调用；完成环境修复后只跑一次选定题
reflective-harness run --benchmark edithero --task A/1a3267df_s0 \
  --config configs/multimodal.toml --output runs/server-edithero-001
```

现有下载脚本拒绝覆盖已有 vendor。若已存在，检查其 `.source-lock.json` 和内容，不要直接删除用户修改。下载包的 tar SHA 受 GitHub 打包方式影响；当前脚本固定 commit URL，但没有独立验证每个文件。这是待加强的供应链完整性，不要称为已完成严格校验。

## 服务器第一阶段：先修可靠性和可移植性

先创建工作分支，记录 OS/CPU/GPU/显存/磁盘、Python、Codex、浏览器、Blender、UE、容器状态。按能力报告，而不是预设 Ubuntu/GPU 已经齐全。

需要优先检查的实际限制：

1. 浏览器固定 `channel='chrome'`，本机使用 Google Chrome。服务器的 Playwright Chromium 安装不能自动匹配这个 channel；改成配置化 browser executable/channel，实际 launch 验证后 doctor 才返回 ready。VTK offscreen 在 Linux 可能仍需要 EGL/Xvfb，不能仅检查 import 成功。
2. 多个 doctor 只检查文件或 Python 包，未完整探测运行能力；应扩展分阶段能力报告，注册成功、执行可用、最终评分可用分别记录。
3. `controller.py` 的 explore 只重复 adapter.execute，**没有将具体诊断目标传给 adapter**；这不是完整定向探索。增加 ObservationPlan/检查目标接口，避免反复收集同一无效证据。
4. 恢复只支持执行 checkpoint 完成后的 artifact 阶段。explore 结果恢复/证据绑定、review prompt/schema/model/hash 完整性、冻结后 evaluate 恢复、会话锁和取消清理需要加强。不要直接修改旧 run 输入来绕过 signature。
5. 最终质量失败与工程失败、评价缺失要分开；CLI 目前可能对 `evaluation_incomplete` 返回 0。增加清晰退出码和测试。检查 `execution_ok=false` 或 review 仍 explore 时不能被 complete 状态误导。
6. 当前 frozen source 中可能包含输入、预览和生成器输出，缺少插件独立的 export contract；EditHero 要导出规范提交，而非整个目录即官方 submission。
7. 目前模型目录分离是约定，不是 OS 访问隔离。正式比较前用容器/独立用户/worker 隔离 solver 与 hidden GT/scorer；凭据只在必要进程中使用。
8. 通用 CLI 的 PPT 路由目前在转交旧 CLI 前加载新配置；修复配置分派，继续支持两套独立配置，并加回归测试。

修复已有范围，不要为了“架构统一”一次重写所有插件。先让原测试通过；补充有意义的失败/恢复/数据泄漏测试。历史 Mac 结果不是服务器通过证据。

## 重点任务 A：完成 EditHero 官方接入

### 已有什么

官方源码 `AlayaLab/EditHero`，固定提交见 lock。数据 `AlayaLab/EditHero` 固定 revision `dba807e8c98f995bc0fad144da38b574d4539fb5`。当前题是 `A/1a3267df_s0` 五步完整链。5/5 GLB 可加载、VTK 渲染和公开检查通过，无官方质量分数。

### 执行顺序

1. 阅读固定源码的 `README.md`、`scripts/render_state.py`、数据 card、论文第 4/10/16 节和附录。重新核实官方 scorer 是否发布；若更新可用，新增版本锁，不要静默替换历史版本。
2. 安装 Blender 4.2，取得并锁定 `AuroraRyan0301/Blender-Visualization-Skill` (`blender_kit`) 的兼容版本。确认脚本需要的 HDRI（如 studio.exr）、Python 依赖和资源来源/许可，实际运行官方 render_state.py。设置 PXFORM_BLENDER/PXFORM_RENDER_SCRIPT；不能仅 `blender --version` 就宣称完成。
3. 按官方 cameras.json 的坐标系、归一化、相机、灯光、分辨率渲染。允许 conditioning view 用于优化；held-out view 和 GT mesh 保持 evaluator-only。输出/保留相机与工具指纹。
4. 从硬编码示例扩展成链 manifest 导入器：case ID、turn 数、指令、原始 source、允许 target views；按需下载，不下载全库。数据 tar 解包拒绝路径逃逸。许可证信息随任务记录。
5. 将 edit_chain 从“单次 author 写五步”扩展成可选逐轮生命周期：每轮 agent 操作自己上一轮提交、保存有效全模型、校验、观测、修复，完成后再进入下一轮。缺失 turn 要按上游协议阻塞后续；预算、attempt、turn、repair 分开计数。若保留整链一次生成 track，要显式命名，不混算。
6. 接入官方 edited/preserved regions、几何和外观指标，保留原单位、方向、适用域、缺失/失败规则。**先确认实际公开实现**；没有官方 scorer 时把模块明确标 unavailable 或独立 reproduction，不用 Codex 自评分或 mesh count 代替。
7. 用 GT 产物作为仅 evaluator 可见正例，再用删除错误部件/保持区域破坏等负例验证评分器；这些是评测器控制测试，不算 agent 解题。
8. 同一道真实链端到端验证：生成→官方渲染→允许的观察修复→冻结→评价→导出；在干净执行环境重建一次，确认无 GT 输入依赖。记录每轮 mesh、代码、图像、hash、指标及成本/调用次数。

验收：任意合法 manifest 可加载；至少一条真实链端到端；官方评价是否完整一目了然；恢复不会重复已完成付费调用；GT 不进入 solver。未达到官方评价时明确列缺项，不写“EditHero 全部支持”。

## 重点任务 B：Code4Scene 从环境到真实场景

### 先核实环境，不先购买整套素材

下载固定源：`python scripts/fetch_benchmark_source.py Code4Scene`。读 README、docs/BUILD_DATASET.md、PACKS.md、SCORING.md、EVIDENCE_BUNDLE.md 和具体 task.yaml。

README、PACKS 和公开目录数量有差异：README 宣称 T2S-focused，实际树含 T2S/I2S 定义。按固定 task manifest 选择一个公开 T2S 案例，别混用论文 I2S 指标。先检查 Research Track 中哪一道素材已在机器上；否则列出候选题对应素材包、确切链接和需要的授权，再向用户请求缺失项。不要假设免费，不购买素材，不用自制替代素材冒充官方任务。

### 需要用户/环境具备的东西

- 可用 UE 5.8 安装路径、项目路径及引擎所需图形驱动/显示能力。
- 选定题所用 Fab packs 已获授权并安装，保持 `/Game/<Folder>` 的原始路径。
- 如当前服务器不能跑 UE，另一个可连接的 UE worker 地址/SSH 别名。不得把 UE 环境缺失仅靠“有 CUDA”判为满足。

### 实现顺序

1. doctor 真实探测 UE 启动、脚本执行、资产目录、指定素材加载、创建空图、保存/重开；记录错误和版本。
2. 实现 Unreal runtime/worker 生命周期：启动、连接、工具调用、保存、截图/多视角证据、退出、超时取消。优先复用可取得的上游工具合同。状态修改操作加 operation_id，崩溃后恢复已提交快照，不盲重放 spawn。
3. 实现 Code4Scene adapter 的公开任务转换：prompt、允许资产 catalog、初始场景、工具合同给 solver；参考场景/私有标签/隐藏评分不给 solver。
4. 作者/修复者通过 Codex 调用受限的 UE 工具或脚本，产物必须是实际 `.umap` 及必要依赖。截图漂亮不等于提交有效。
5. 每轮保存后独立 session 重开，导出官方 evidence bundle；验证评价对象是落盘提交。
6. 接通固定上游 scorer，原样保留 native integrity、alignment、physical safety 和指定 track 聚合。若官方 judge 要求非 Codex 模型，先明确与用户“只用 Codex”约束的冲突；内部替代必须独立命名，不能声称等价。
7. 核对 track 的提交选择/反馈规则；禁止按隐藏最终分数反复修复或 best-of 选版本。若 track 规定首个有效提交，就按该规则实现。
8. 一道真实题完成生成、保存重开、观察修复、冻结、评分；正例和无效场景负例检查 verifier；不要跑全量。

缺少引擎/素材时可继续实现合同、worker 客户端和模拟协议测试，但它们不能算官方真题通过。给出具体剩余依赖，不造一个成功结果。

## 当前实测和数据迁移

已测试五个新增 benchmark 各一道：LongPuzzle 成功（3 calls）；GameDev 失败（官方 test missing handler）；SciVis 内部 8.25/10；A2Z 浏览器流程有效无官方分数；EditHero 五轮交付有效无官方分数。38 项工程测试通过。不要因此推断整体正确率或优于原生 Codex。

**GitHub 不包含** `.venv/`、`vendor/`、`data/`、`runs/`、`.cache/`、本机 Chrome/Godot、任何登录凭据。验证报告提到的 Mac runs 路径在服务器不存在是正常的。`validation/multimodal-smoke-20261014.json` 是移除本机路径的历史摘要，不是可重放的完整轨迹。新的服务器证据需重新生成到新的 run。不要为读取旧轨迹默认要求迁移全部 runs（含完整模型日志）。

## 完工时交付

更新实际使用说明、环境/数据/源码锁、测试报告。逐项报告：实现状态、实际题号、生成是否有效、公开检查、官方/内部评价、具体分数、失败原因、调用预算和剩余依赖。保持原始证据，测试成功不覆盖失败记录。只做小样本，禁止自动展开全量测试或未经请求的 baseline 大规模对照。

## 可以直接粘给服务器 Codex 的启动指令

> 先阅读 docs/SERVER_CODEX_HANDOFF.md，按阅读顺序理解仓库并检查服务器环境。继续完成 EditHero 官方渲染/数据接入/评分与恢复，然后推进 Code4Scene 的 UE worker、原生场景和上游评价。保留 PPT 兼容性，所有智能阶段使用配置的 Codex 模型。先修文档列出的可靠性和服务器兼容问题。每个数据集只测试一道真实题；缺官方评分器或 UE/Fab 环境时如实登记，不能用模拟测试冒充跑通。无需重新询问是否开始软件工作；仅请求确实缺少的账号授权、素材或环境信息。记录结果和剩余工作，不跑全量 benchmark。
