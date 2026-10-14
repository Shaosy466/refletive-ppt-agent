> 2026-10-14 实施更新：本文保留完整目标架构，不能将其中拟议能力视为已实现。当前可执行范围见 [MULTIMODAL_USAGE.md](MULTIMODAL_USAGE.md)，真实测试见 [MULTIMODAL_VALIDATION.md](MULTIMODAL_VALIDATION.md)。本次新增 EditHero、Witness、LongPuzzleBench；Code4Scene 与原列表重复。共九个新增 benchmark，加原 PPT 为十项。

# 多任务 Codex Harness 改造规划

日期：2026-10-14。状态：设计稿，尚未实施。范围：保留 PPTBench，增加 4DCodeBench、Code4Scene、A2Z GameSpec-Bench、GameDevBench、SciVisAgentBench、IChart2Code；未来可新增插件。本轮不运行新模型实验、不修改现有执行代码、不推送 GitHub。

## 1. 决策摘要

保留 Codex 作为生成、观察、诊断、修复的智能执行入口；将控制器、任务适配器、执行环境、证据存储和最终评测分开。六个 benchmark 不是六套复制的 PPT 脚本，也不是一个巨大万能 prompt。

核心变化：

1. TaskSpec 替代主控中的 DiagramSpec；DiagramSpec 留在 PPT 插件。
2. ArtifactBundle 替代单一 PPTX，EvidenceBundle 替代单张截图。
3. 支持短命令、长期服务、交互会话及 GPU 作业。
4. 反馈只来自当前轨迹可用的公开信息；最终评测有独立权限，默认不回传。
5. 每个 benchmark 保留原始指标、分母、失败规则、任务版本和评测协议，不统一改成“90 分、三轮、取最好”。
6. 重用上游 runner/checker/scorer；只为缺失的连接写适配层。缺失公开实现时不声称已复现官方协议。

## 2. 阅读依据和需要纠正的结论

本设计依据六篇论文 HTML v1 的任务定义、实验设置、评分与附录，以及可取得的官方仓库 README/接口说明；尚未对六套上游代码完成逐文件审计或部署验证。下文接口名是本项目建议接口，不是假称已经存在的上游 API。

- 4DCodeBench：<https://arxiv.org/html/2610.03715v1>，重点 §2.1–2.4、§4.5、附录 D/G；代码 <https://github.com/4DCodeBench/4DCodeBench>。
- Code4Scene：<https://arxiv.org/html/2609.36777v1>，重点 §2、附录 A/C；代码 <https://github.com/SimWorld-AI/Code4Scene>。
- A2Z：<https://arxiv.org/html/2609.39564v1>，重点 §3、§4.5、附录 B/C/D；代码入口 <https://github.com/krafton-ai/a2z-gamespec-bench>。
- GameDevBench：<https://arxiv.org/html/2602.11103v1>，重点 §3–4、附录 D；代码 <https://github.com/waynchi/gamedevbench>。
- SciVis：<https://arxiv.org/html/2603.29139v1>，重点 §4、§6；代码 <https://github.com/KuangshiAi/SciVisAgentBench>，接口 <https://github.com/KuangshiAi/SciVisAgentBench/blob/main/benchmark/evaluation_framework/README.md>。
- IChart2Code：<https://arxiv.org/html/2609.32413v1>，重点 Evaluation Protocol、TRAIL/Inspector、Experimental Configuration。

### 版本与公开程度

GameDevBench v1 是 132 题；当前官方仓库是 333 题、Godot 4.4.1。官方结果目录 `results/gpt6_astra_codex_runtime_video_high_full_333` 报告 Astra High + Codex CLI 0.153.4 + runtime-video + strict confinement，229/333=68.77%，600 秒 solver 限时，截图 MCP 关闭。此前“没有 Astra 直接证据”的判断应撤回。官方还披露 Linux 下两个 ground-truth 任务文件名大小写问题（331/333 GT 通过）；不得隐藏此类问题或静默删题。来源：<https://github.com/waynchi/gamedevbench/tree/main/results/gpt6_astra_codex_runtime_video_high_full_333>。

Code4Scene 论文 v1 有 construction/editing 共 190 题、95 题公开评测；当前仓库主要发布 Text-to-Scene：README 宣传 160 题完整集、20 题 Research Track，同时注明仓库当前含 150 个定义。这不是同一份 manifest。优先锁定实际可取得的 Research Track；图像编辑轨道需另行确认发布，不得拿 T2S 名义替代 I2S。

A2Z 官方 README 明确写明数据集已发布、代码将发布。其 100 GDD 可以用于开发生成与试玩，但没有官方 evaluator 的情况下，只能输出本项目实验协议结果。

IChart2Code 论文可读，但本轮未定位并核实官方代码与完整任务发行包。没有找到不等于确认不存在；正式适配前应继续核实作者链接/数据发布，不能凭论文自造 377 题冒充原任务。

SciVis 官方已提供完整工具链 Docker 和 BaseAgent 插件接口。4DCodeBench 官方提供 inference/scorer 分离的容器、public checker、数据和预计算参考估计；正式评分还需模型检查点与 NVIDIA 环境。

## 3. 六个适配器的具体设计

### 3.1 IChart2Code：交互图表重建

输入：参考截图、文字要求、任务本地数据。不能向 generator/inspector 提供参考 HTML、私有 rubric、评测反馈。Inspector 从公开输入自行生成检查计划。

产物：HTML/JS 与本地数据/依赖，离线打开可用。执行环境为受控 Chromium/Playwright；固定 viewport、浏览器版本、缩放、字体、locale、时区。

观察不是“截一张图”：保存初始画面、动作目标、hover/click/filter/selection/legend 操作、执行前后截图、DOM/console 状态、数据结果以及未受影响区域。每项 evidence 绑定 check_id、候选 hash、轨迹 seed。动作目标解析失败记为 observation_error，不能直接记图表功能失败。

自检：本地数据与 tooltip/过滤结果一致性、公开需求是否实现、截图差异。最终评测：复用可取得的官方执行门槛及三维 rubric（Data、Static、Interaction）与辅助 OCR/SSIM。保留各维分，不自行创造官方总分。执行门槛失败按原协议处理。

最小验收：一题静态、一题 hover、一题过滤/联动；故意注入 tooltip 数值错误，截图外观不变也必须检出。若上游数据未发布，先做自有 fixture 验证浏览器 runtime，明确不是 benchmark 验收。

### 3.2 GameDevBench：Godot 项目修改

输入：官方任务说明与过滤后的起始项目、多种素材。不是从空目录生成整个游戏。输出完整修改项目或可应用补丁；继承文件必须保留。

运行：固定 Godot 4.4.1，Linux 显示任务需 Xvfb/xauth；录屏需 FFmpeg。优先复用上游 strict confinement、资源导入和验证流程，不另写一套容易泄漏 tasks_gt 的 runner。绝不能把含答案的上游根目录挂给 solver。

观察：编辑器截图可选、runtime-video、关键帧、节点树、运行日志、公开可用的状态检查。官方隐含测试由 evaluator 独立执行，能否回传由 track 决定；默认不回传私有测试细节。

最终评分：官方确定性 Godot 测试和 pass@1，不用 VLM 美观分替代。Codex 的视觉自检服务于改进，不能推翻测试结果。

最小验收：逻辑、2D 图形、UI 各一题；修改碰撞/镜头/动画中一个条件的负例；验证干净起始项目与隐藏 GT 隔离。版本锁记录任务 archives 和 evaluator 哈希；已知坏 GT 单独报告，不悄悄修改官方题目。

### 3.3 A2Z GameSpec-Bench：完整浏览器游戏

输入：长 GDD、允许的项目模板和 runtime-interface specification。固定 contract 在初稿生成时不可见。主要环境 Phaser 4.1 + TypeScript + Vite，浏览器运行生产 build。

产物：源码、lockfile、可运行 build、按上游要求导出的接口。观察包括 source evidence、固定 scenario replay、正常与对抗性 adaptive playtest。每个动作标时间/帧/输入持续长度，保存状态转移和画面，避免“截图看似死亡，但 Hull 没归零”。

两种不可混淆的轨道：

- blind-development：从 GDD 派生自检，最终 contract 只对冻结产物评分。
- contract-feedback：按论文 §4.5 的实验设置允许特定 requirement-level feedback；标注反馈暴露范围、轮数、初稿和预算，不能混入盲测主表。

contract 必须一次冻结，不随候选重新生成。对同一 build 的随机种子、重复试玩和 judge 次数与独立 build repeats 分开记录。论文主结果每 GDD 三次独立生成；三次 judge 不等于三次生成。

官方代码未发布时先接入 GDD 与浏览器执行/自有需求检查，协议命名 `a2z_experimental`，official-compatible 状态为 unavailable。不要编造官方 scorer CLI。

最小验收：一份 Small GDD，覆盖正常通路和失败/惩罚通路；改变数值阈值或状态更新后观察应能定位到规则，并验证修复未破坏另一通路。

### 3.4 SciVisAgentBench：科学分析与可视化

108 个论文案例横跨 ParaView、分子、bioimage、topology、object identification。当前发行版规模与子集须以锁定数据 manifest 为准。它应是一个 benchmark 插件配多个 toolchain profile，而非强行一个 Python 环境。

优先实现上游 BaseAgent.run_task 适配：上游负责任务加载、产物位置和最终评价，我们负责受限工作区内 Codex 迭代。导入 task_config 时只允许公开字段，不能把其可能含有的参考答案直接给模型。

Runtime profiles：paraview/pvpython、napari、VMD/分子工具链、TTK/拓扑。优先使用上游 Docker；底层 Python 与主控 Python 隔离，不能为了统一依赖破坏 VTK/Qt/科学计算 ABI。

输入一般是数据与专家任务描述；参考图/参考脚本是 evaluator 资产，不能像 PPT 一样默认给 solver。可见性以每题实际协议为准。输出可能是脚本、软件 state、图像、结构化分析结果。

观察：固定相机重渲染、多个 canonical views、数组名、物理量/单位、数据范围、transfer function、过滤条件、缺失值和分析结果。不是所有子集都应用同一种图像比较。

最终评分保留上游各 suite 的 rubric/assertion/拓扑规则及 completion、pass@k、pass^k 定义；PSNR/SSIM/LPIPS 的 scaled 聚合在 benchmark 层计算，不能对每题做随意平均。首次只验收一个 ParaView 小任务，随后每个支持的 suite 至少一个正例/负例；没有完成其他 profiles 时标 partial。

### 3.5 4DCodeBench：视频到显式动态世界

输入仅参考视频、公共任务 prompt、world-format 和 render settings。场景名、参考几何、隐藏问答与 scorer 不可见。

输出严格遵循上游：`solution/build.sh` 和代码；`world/camera.json`、`render.mp4`、`meshes/*.npz`、`dynamics/*.npz` 以及需要时的 solver bake。统一 world-space 米制、z-up、帧索引/时间对齐、稳定对象身份；详细数组布局直接复用 docs/spec.md 和 checker，不凭论文摘录重新定义。

生成容器可读参考视频；产物 rebuild 则必须在无参考输入、无外网、无外部素材的新环境中完成，防止用视频贴图/读参考绕过重建。

观察支持视频抽帧、短片段、轨迹与对象状态。提供 ffprobe 元数据、稀疏预览、针对碰撞/分裂等事件的密集采样；所有抽样保留 timestamp/frame index，原视频不被抽样图替代。抽帧只能作为给 Codex 的输入手段，官方 full-rate 检测不降采样冒充等价。

评分采用上游五类指标及各自适用域：real 视频的估计量与 synthetic 世界 GT 不混用；保留 not_applicable/excluded/error/uncomputable。几何合法性诊断与 Overall 中的指标区分。VQA/Elo 是另一个评测模块，pairwise Elo 需要固定对手池与 judge，不能由单题自评分推导。

环境：论文 Ubuntu 24.04/CUDA 13/Blender 5.2，发行版依照冻结容器；官方 README 要求 NVIDIA GPU、独立 scorer 和检查点。Mac 可调度远端 Linux GPU worker，不能声称原生 Mac 等价。

最小验收：短 rigid synthetic 正例 + 运动方向/速度错误负例，再一个 real 视频；核对帧数、fps、分辨率、坐标系与独立 rebuild。预览允许低成本，最终评测必须回到规定设置。

### 3.6 Code4Scene：Unreal 原生场景

先接公开 T2S Research Track。输入为空场景、公开 prompt、限定资产 catalog 和工具说明，产物为真正保存的 Unreal 场景及所需项目文件，不能仅交截图。

Runtime 是长期运行的 UE editor 与任务工具代理。支持 asset search/metadata/preview、actor edits、Python job、viewport、measurements、save/reopen。复用上游可取得的工具 contracts。引擎修改不是天然幂等：每条操作带 operation_id 和结果；崩溃后恢复到已保存候选，禁止盲重放 spawn。

可复用 assets 只读共享，候选可写 package 隔离。每轮保存后在新 editor/干净 session 重新打开并导出官方 evidence bundle，保证评分对象是磁盘提交而非未保存 GUI 状态。

最终使用公开 verifier 的 native integrity、alignment、physical safety 与官方聚合。当前公开 T2S 公式/指标以冻结代码为准，不混入论文 I2S Repair F1。

I2S 扩展需先取得完整任务和 scorer；再提供 reference views、初始错误场景、目标修复与 preservation 检查。隐藏正确场景不提供给 solver。

UE 5.8 与 Fab 素材是明确外部依赖：代码可以公开，商用素材不能随仓库打包。没有素材时 doctor 列出缺失 pack/资源，不换廉价模型冒充相同任务。论文八 GPU 是实验主机规格，不应误称每题最低需要八卡。

## 4. 架构和职责

建议新增 `src/reflective_harness/`（Python 包名可正确拼写，不改变已发布 GitHub 仓库名），旧 `pptbench_harness` 保留兼容 CLI。

```text
reflective_harness/
  core/        contracts, state_machine, budgets, checkpoints, scheduler
  agents/      codex, prompt_builder, capabilities, response_validation
  evidence/    artifact_store, manifests, image/video/trace indexing
  runtimes/    process, browser, godot, science, blender, unreal, remote
  evaluation/  feedback_policy, final_evaluator, compatibility, reporting
  plugins/     pptbench, ichart2code, gamedevbench, a2z, scivis, fourdcodebench, code4scene
```

BenchmarkAdapter 规定数据与评测语义；Runtime 提供执行/观测机制；Controller 负责生命周期；Codex 负责推理和修改。IChart/A2Z 共享 browser runtime，但不共享 rubric。4D/Code4Scene 共享视频/多视角 evidence 类型，但不强行共享引擎操作。

最低插件合同（以下均为拟新增接口）：

```python
class BenchmarkAdapter(Protocol):
    def describe(self) -> AdapterManifest: ...
    async def doctor(self, profile) -> CapabilityReport: ...
    async def prepare(self, case_id, version) -> TaskBundle: ...
    def public_view(self, task, role) -> PublicTaskView: ...
    async def start(self, task, parent, runtime) -> WorkspaceHandle: ...
    async def execute(self, workspace, budget) -> ExecutionResult: ...
    async def observe(self, execution, plan, budget) -> EvidenceBundle: ...
    async def check(self, candidate, evidence) -> PublicCheckResult: ...
    async def snapshot(self, workspace) -> CandidateRef: ...
    async def export(self, selected) -> SubmissionBundle: ...
    async def close(self, runtime) -> None: ...

class FinalEvaluator(Protocol):
    async def evaluate(self, submission, private_case, protocol) -> EvaluationResult: ...
```

选择/停止策略由注册的纯函数配置指定，不能把数据库/评分实现藏进模型 prompt。适配器提供结果解析器与指标 schema。最终 scorer 可以是上游容器/CLI，也可以是上游 Python 插件，不要求重写成 Codex 工具。

插件发现使用 Python entry points，例如 `reflective_harness.adapters`，manifest 声明 adapter_api_version、task_schema、runtime capabilities、source lock、可用 tracks 与评测范围。注册失败/版本不匹配 fail-fast。

## 5. 数据合同

所有 envelope 有 schema_version；路径使用 artifact ID 或工作区相对路径，拒绝逃逸与 symlink；各插件 payload 由其版本化 JSON Schema 校验。

- TaskSpec：benchmark/version/split/case_id/task_kind，公开说明/素材引用、环境 profile、预算、允许工具与反馈策略。理解输出是 agent 假设，不能改写官方需求。
- PrivateCase：隐藏 GT、rubric、tests、参考源码等，只存 evaluator。不要放进 TaskSpec 然后依靠 prompt 让模型“忽略”。
- ArtifactRef：id、kind、sha256、size、producer、candidate_id、visibility、relative_path；大视频/mesh 不塞 JSON。
- CandidateRef：candidate_id、parent_id、源码/资产/引擎状态 manifest、构建配置、seed、环境 fingerprint、是否完整提交。
- EvidenceItem：image/video/trace/log/state/measurement；关联 artifact hash、candidate hash、check_id、frame/timestamp/view、采集工具版本和 seed。
- Finding：claim、expected/observed、severity、证据 ID、reproduction、定位 locator、suggested_edit、preserve_targets、confidence。locator 是带类型联合：image bbox、time interval、DOM/selector、Godot node path、UE actor ID、mesh ID、data array。
- EvaluationResult：execution_status、submission_valid、evaluation_complete、指标字典与每项 direction/unit/status、可选 aggregate、protocol hash、judge identity、source revision、feedback_exposure、costs。

不能沿用旧 `bbox` 到所有任务。图像框为归一化 xywh 且宽高正；线段/点给单独类型或有记录的像素 padding；时间区间必须绑定对应视频；world geometry 必须注明坐标系、单位与变换。

## 6. 状态机、prompt 和数据流

```text
prepare → understand/inspect-existing → author/edit → execute
→ capture evidence → public check/diagnose
→ explore（补采证据）或 revise（从策略选择的 parent 修改）
→ freeze selected submission → final evaluation → export/report
```

理解阶段可选：修改已有 Godot 项目时更像项目探索，Code4Scene 可在 agent session 中交替工具操作，不要求强制先生成一份完整 graph。

Prompt 分四块拼装并逐次保存：通用角色/工具边界；插件操作合同；本题公开输入；当前候选代码和 evidence/feedback manifest。每次记录 prompt/schema hashes 与实际模型/effort。

Author 接收公开需求、可修改文件、产物合同、当前 parent 和 feedback。Observer 接收需要回答的检查问题与候选证据，不能把作者“已修好”的自述当作验证。Diagnoser 必须把修改建议绑定 observed/expected 与可定位证据；证据不足返回 explore，不编造观测。Repair 明确必须保留的对象/行为并输出修改摘要；通过与否由后续执行决定。

视频不默认直接作为 Codex 原生输入：按运行时能力探针选择图片帧、带时间标记的 contact sheets、可读文件及本地分析工具，记录该转换；不能把“有视频文件”当成模型已观看视频。

交互任务增加内层循环：reset(seed) → observe → action → step/wait → observe。固定 replay 和自适应 policy 分开，策略与轨迹都有版本。每个独立 test 在规定起始状态运行；跨步状态只在同一 scenario 内延续。

## 7. 评分权限和可比性

保留三种 protocol profile：

1. `development`：全部智能阶段可继续使用配置的 Astra/Codex/high；从公开输入派生检查并优化，结果标 internal。
2. `benchmark_submission`：主控只导出冻结提交，调用上游最终 scorer；最终分数不进入修复/选择。需要非 Codex 官方 judge 时单独明确依赖；用户只允许 Codex 的实验不能伪称完整官方复现。
3. `feedback_experiment`：允许某些 benchmark 指定反馈，例如 A2Z contract feedback；记录曝光范围和预算，单独成表。

不把三个不同概念混合：judge 重复次数、独立 agent attempts、同一 attempt 的 repair rounds。PPT 的固定三轮保留在 PPT 配置，不能全局硬编码。

选择版本只能依据允许暴露的开发信号。冻结之后可对首稿和 final 做配对最终评分，但不得再据此重新挑选版本。Code4Scene 的首个有效提交规则与 PPT 的 best-of-loop 分开实现。

报告保留各 benchmark 官方聚合与失败记分；工程状态继续记录 infrastructure_error、invalid_artifact、quality_failure、budget_stop、cancelled。某官方协议把缺失提交计零时，在 official view 使用该规则，同时保留 infra cause。禁止全局强制 null 或零，禁止跨六个任务直接平均 raw score。

Compatibility 是多项证据而非一个随意布尔值：task revision、runtime、assets、tool access、budget、retries、judge、scorer、feedback scope、selection。只有核对齐全才声明指定 track-compatible。

## 8. 执行、安全、缓存和成本

主控可在 Mac；轻量浏览器与已有 PPT 本机开发；标准 benchmark worker 优先 Linux；4D/UE 在 NVIDIA GPU 主机。统一 CLI 不等于任何一台装 Codex 的电脑都能本机运行所有环境。

Worker 提供 capability discovery、创建沙箱、提交作业、查询状态、取证据、取消和清理；支持本地进程、容器、后续远端 worker。一次 GPU lease 对应明确作业，浏览器/UE 会话有独占端口和显示。

Solver 只挂载公开任务与可写 candidate；Scorer 单独挂载隐藏数据、无 solver credentials。生成时仅放行必要模型端点；依赖安装与资产下载在准备阶段完成；rebuild/test 按 benchmark 限制网络。验证不能执行 solver 可修改的判分器。

检查点只提交完整 candidate manifest，不保存仍在写入的引擎文件。长服务恢复采用 reset + last committed state；resume 校验 model/prompt/adapter/runtime/task hashes。stale feedback、旧图像、旧浏览器缓存与候选 hash 不匹配时拒绝使用。

预算分开计：agent calls/tokens、tool actions、wall time、CPU/GPU seconds、render frames/pixels、interaction steps、judge calls、storage。共享 GPU、CPU、浏览器、模型并发各有 semaphore。没有可靠价格就 cost=null。故障重试与质量修复分别计数，重试仍计预算。

内容寻址缓存只用于同环境同输入的确定性操作。随机游戏轨迹必须包含 seed 与动作 policy；最终 judge 不能以同文件名错误命中缓存。

## 9. 与现有项目的迁移关系

- `codex_runner.py` → agents/codex：保留命令构造、schema 验证、预算、事件；补 role capabilities、session/工具代理接入。
- `checkpoints.py`、`runtime.py`、`workspace.py` → core：保留时间与锁逻辑，扩展多资源/服务生命周期。
- `orchestrator.py` → core/state_machine：删去 task_四位ID、build.py、PPTX、固定三轮/90分等假设。
- `dataset.py`、`native/`、`validator.py`、上游评分耦合 → plugins/pptbench。
- `observer.py` → evidence：保留图片 crop/comparison，增加视频/轨迹/状态；PPT 特有盲比较布局留在插件。
- `models.py` → 通用 envelope + 各插件 payload，DiagramSpec 不再是所有任务入口。
- `reporting.py` → 通用覆盖/成本 + benchmark 原始指标视图。

旧 `ppt-harness` 命令继续有效并路由到 PPT 插件；旧 run schema 不原地改写。历史结果只读导入，新协议另建 run。重构第一阶段必须保证原 PPT fixture 的原始评分、产物校验、恢复行为不退步。

## 10. 用户接口（拟议，当前不可执行）

```bash
reflective-harness adapters list
reflective-harness doctor --benchmark gamedevbench --profile linux-godot
reflective-harness prepare --benchmark gamedevbench --task-file configs/smoke/gamedev.txt
reflective-harness run --benchmark gamedevbench --config configs/experiments/astra-high.toml --task <upstream-id>
reflective-harness evaluate --run <id> --protocol <frozen-protocol>
reflective-harness resume --run <id>
reflective-harness export --run <id>
```

`adapters list` 显示 declared/experimental/ready/partial/blocked，而不是只要写了类就显示 supported。doctor 输出缺失软件、资产许可、任务发行包、模型能力和可用 worker。配置允许每插件独立预算；不把 PPT 的四小时写死到所有任务。

## 11. 实施顺序与验收

P0：锁定上游版本与可用性。为六项建立 source-lock，包含论文版本、code commit、dataset revision、license、公开题目 manifest、环境与评分入口；核对正例能通过原始验证。Code4Scene 素材、IChart 发行包、A2Z scorer 缺失单独登记。

P1：抽取 core + 迁移 PPT。保留现有 29 项工程测试；新增插件 API 合约、隐藏数据拒读、candidate/evidence hash、恢复与 cancel、同名不同插件任务的隔离测试。只做少量真实 smoke，不跑全量。

P2：browser runtime + IChart 实验适配 + A2Z GDD/游戏生命周期。两者共用 browser，不共用评测规则；上游缺失时用有明确名字的自有 fixture 验证 runtime，不算官方 benchmark 支持。

P3：GameDevBench 正式适配。它已有完整公开任务和确定性验证，也有 Astra 直接基线，应作为新增任务第一个完整 official-adapter 验收。若 P2 上游尚不可用，不等待，优先推进本阶段。

P4：SciVis 集成上游 BaseAgent 与 Docker。先 ParaView，逐步覆盖其余 suites；记录各 profile 支持状态，不把一个 suite 跑通当作全覆盖。

P5：4DCodeBench GPU worker、世界导出与官方 scorer。先短 rigid synthetic，再 real 视频，随后覆盖 deformable/liquid；不要求 smoke 阶段跑完 200 题。

P6：Code4Scene UE worker + Research Track。先获许可素材、保存/重开、官方 evidence/verifier；I2S 轨道按公开实现情况追加。

每一适配器最小完成定义：官方样本成功加载；一个真实 end-to-end submission；正例与注入失败负例评分正确；独立干净运行复现；中断恢复不重复已完成付费调用；隐藏数据不对 solver 可见；日志/成本/协议完整。小样本验收证明接入可用，不证明模型整体表现。

## 12. 实验设计

统一 Astra/high 与 Codex 版本作为首轮研究配置，但不同 runtime 不强求同一分钟预算。比较同题同初稿、同环境、预注册预算下：原生 Codex baseline；仅执行错误反馈；视觉/交互反馈；加入结构化定位与回归保护。禁止把外层一次 author 称为一次模型 completion，Codex 内部仍可多工具回合。

按任务报告质量增益、运行有效率、最终评分覆盖、成本和修复退步率。只在官方独立 attempts 上计算 pass@k；迭代候选不能伪装独立样本。为长视频/游戏分别记录证据采样预算和动作预算。

## 13. 尚需落实的外部条件

不是本轮要求用户重新批准的事项，而是实施前应由 doctor/source-lock 核实的条件：

- IChart2Code 正式任务包与 evaluator 是否可取得。
- A2Z 官方 contract/scorer/test policy 代码何时公开，已发布数据具体包含哪些字段。
- Code4Scene 实际 public manifest、Fab pack 授权/下载与 I2S 发行状态。
- NVIDIA Linux worker、显存/存储与容器可用性；不能从论文主机规格直接推算最低需求。
- 官方 scorer 的 judge/视觉模型权重、许可证与凭据要求；坚持全 Codex 智能调用时，明确哪些最终评测只能称为内部变体。

本方案可以立即开始 core、PPT 迁移及公开完整任务的适配，但“六个都支持”的最终声明必须逐项通过验收，不能用空插件替代缺失的官方数据或评分器。

## 附录：本轮查询到的代码 HEAD（供后续固定版本）

以下是查询时的 HEAD，不表示这些版本已安装或经过本项目验证。README 阅读与 HEAD 查询不是原子操作，正式 source-lock 阶段须按指定提交重新读取并审计。

- GameDevBench：`39952ba6341898380ff1c2c3336101c57c99196b`。
- 4DCodeBench：`6c466be34107d7f388f30f97bf059b68ba1a21b0`。
- Code4Scene：`2716e4397f768bf16b1f33dd34680d48aed0601f`。
- SciVisAgentBench：`b9435d13e9ff979226b1754e6c467efeb026978a`。
- A2Z GameSpec-Bench：`a61fe39d07cbd4a25e96bdad9ef2b28651fd7082`。
- IChart2Code：未核实官方代码，不填写虚构提交。

## 14. 新增三个不重复 benchmark

### EditHero（2610.02298v1）

官方仓库 AlayaLab/EditHero；数据 AlayaLab/EditHero。457 条编辑链、2755 个编辑、3212 个状态。每条链从原始分部件 GLB 开始，逐轮 add/remove/replace/retexture；下一轮必须基于 agent 自己的上一轮结果。只允许 conditioning view，不将 hidden GT mesh、held-out images 或 part masks 默认提供给作者。链不是五道独立题。

论文 Codex Astra/Sol 使用 medium effort，当前配置 high 属于实验差异。源码发布数据引擎和 Blender 4.2+blender_kit 渲染，不代表全部论文区域度量已集成。本轮实现只提供官方 sample 的完整五步本地链、VTK 预览、GLB 可加载性检查；不把交付数量当成编辑质量。官方编辑区域、保持区域、外观指标仍需接入。

### Witness（2609.32208v1）

官方项目 witnessbench.ai。8 个公开 validation games、17 个私有 test games、22 个训练 games。论文主设置使用 ground-truth ASCII 和六动作，不能把它描述为纯视觉 GUI 基准。动作方向映射和规则从交互推断；SUBMIT/RESET 的语义公开。官方 RHAE-L5 需要对应 human action baseline，不能从一局胜负推导。

需要 EpisodeAdapter 严格限制模型只看到允许的 board、legend、历史尝试反馈，不能读取游戏规则源码。Codex 带代码执行属于另外的实验 track。本轮未确认官方 validation SDK 的可下载入口，网页可玩不等于已取得可复现 SDK；注册 blocked，不编造 API。

### LongPuzzleBench（2609.34769v1）

官方仓库 AzureStarz/LongPuzzleBench，6 个游戏、114 关、16 个 game×difficulty cells。上游分 autonomous 和 controlled catalog 两种 lifecycle。论文整组任务从主菜单选择游戏/难度；单关 controlled smoke 不能冒充整组分数。

模型只收截图与 public action feedback，私有 benchmark bridge 留给 evaluator。复用 WebGameEnvClient、原始 episode runner、MiniGameEvaluator。将 Codex 的观察/诊断/记忆/动作写入 JSON，以当前截图像素坐标调用合法 GUI 输入；不直接更改游戏状态。每步保存截图、坐标、反馈、模型使用量和上游轨迹。

## 15. 实施时发现的版本差异

Code4Scene 固定提交的 README 宣称 T2S-focused，但实际 benchmark/public 树含 image-to-scene 的 indoor/outdoor 定义，PACKS 文档列出 225 public cases。不能继续断言完全没有 I2S 定义，也不能据此宣称 I2S engine assets 已发布：仍需要 UE 和 Fab 内容、构建场景以及逐轨道验证。
