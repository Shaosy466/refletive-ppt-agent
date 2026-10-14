# 验证记录

此文件区分工程测试和真实模型测量。模型固定 gpt-6-astra / Codex / high。内部检测不是论文官方评分。

## 已完成的真实验收

- Codex 图像与工具探针：正确读取三个图像标签并写入指定文件，原始事件在 `runs/probe/`。
- 首题 `task_0004`：运行 `20261013T151415Z-7e5f27`，原生文件有效，三轮内部检测合并分 93.62，终态 QUALITY_PASS。
- 首题在 author 检查点完整提交后被主动中断，随后通过 `resume` 恢复；作者响应仅一份，源码未重新生成。
- 首题对象映射有 69 条逻辑映射，覆盖 68 个实际形状（包括组），其中一个网络对象同时表示逻辑边与可视形状。原生组件检查统计 63 个叶组件、0 张图片。
- 首题总计 12 次 agent 调用（包含被中断调用），累计约 38.8 分钟。中断调用用量不可完整恢复，因此 usage 和 cost_usd 均为 null，没有伪造精确成本。

## 工程测试

最新完整测试：25 项 pytest 测试通过，pip check 无依赖冲突。覆盖固定模型参数、Schema 与路径边界、三轮混合门槛失败、官方评分 CLI 一致性、跨轮缺陷合并、最佳候选回滚、预算、检查点/锁、子进程超时、事件流、避免重复调用、实际原生 PPT 渲染、非法 PPT/多页/截图替代/批准素材缺失、对象映射真实 ID、共享并发限制、未完成样本分母。

## 最初开发批次（历史记录）

运行 `20261013T160118Z-72638d` 使用 `configs/tasks-dev.txt` 的十个固定任务，配置 `configs/dev-batch.toml`（任务与 agent 并发 3，渲染并发 1）。此批次后来因字体环境修复而停止；最终采用的恢复运行见下文。

## 已确认的环境与边界

- Python 3.12，Codex CLI 0.160.0，LibreOffice 26.8.0.3。
- 模型请求参数已验证；provider 未提供可独立验证的后端模型身份证据。
- `task_0017` 官方源码 PDF SHA256 验证通过，但 macOS arm64 上 PyMuPDF 1.28.0 / MuPDF 1.29.0 重建的参考图像素哈希与冻结清单不同，禁止作为有效题目输入。详见 `runs/task0017-materialization-failure.json`。
- 预期像素哈希：`7bdb264a89884aa51d0dc8e464c8e436abc25105f9cc2489535efb5e3aa26cc4`。
- 本机实际像素哈希：`b49bc3facb28c96cbb8f8b38c1af4a8a3fc4cfe0c87700262b9b541185078194`。
- 没有修改任务哈希或替换题目。需要在匹配的渲染环境继续解决这一兼容性问题。
- 本机 local-dev 没有实现 Linux Bubblewrap 的读隔离，且 LibreOffice 与论文版本不同，所有运行 official_comparable=false。

## 字体环境修复与新批次

实测导出的 PDF 揭示默认 LibreOffice Fontconfig 未搜索 macOS Supplemental 字体，即使 PPTX 指定 Comic Sans MS，也使用了 FrankRuhlHofshi/LinuxLibertine 替代字体。新增 `configs/fonts-macos.conf` 后 PDF 确认使用 ComicSansMS；已增加真实字体回归测试。

旧开发批次 `20261013T160118Z-72638d` 已主动中断，保留历史。新批次 `20261013T162947Z-replay-eba881` 通过 `replay` 只复用 task_0001/task_0004 的已验证初稿，不复用任何 validation/render/judge。旧调用预算继续计入，usage 标记不完整。新批次单次调用超时统一为 1800 秒。当前工程测试 21 项通过。

修正字体后的 `task_0004` 已完成三轮，内部合并分 95.50。`task_0001` 初稿三轮合并分 87.25，已自动进入诊断/修复。真实反馈定位了 Stepwise 文字与橙色连接线接触、OPT1/OPT2 字重、Agent 斜体、机器人原生图形细节，并提供对应对象 ID 与源码符号。

批次还暴露了 `task_0008` 的结构化理解输出缺失 uncertainty 引用；被模型业务校验拒绝，记为不完整而非零分。该案例需要补上规格规定的有界格式修复路径。

## task_0017 已解决

在 Linux amd64（x86_64）容器中运行同一个冻结上游 materializer、PyMuPDF 1.28.0 和 Pillow 12.1.1，`task_0017` 的原始 PDF、参考图像素与素材全部通过官方哈希。macOS arm64 与 Linux arm64 均无法产生相同像素。因此严格复现需要使用 x86_64 图像构建环境，而非修改哈希。已生成的冻结图像随后在 macOS 再次通过官方 verify_materialized_task。

为排查安装了 Colima、Docker CLI 和专用 `pptbench` Linux VM；虚拟机在完成 materialize 后已停止。需要重新复现时可用 `scripts/check_reference_linux.sh`，容器下载可能需要本地网络代理。源码归档缓存保留，不需要重复从 arXiv 下载。

## 运行器恢复加固

运行遇到主机长时间休眠和 provider 流式重连。已加入 macOS mach_continuous_time / Linux CLOCK_BOOTTIME 超时检查，并用 caffeinate 保持批次运行。运行器支持一次 JSON 格式/引用修复，修复不提供图像、不允许重新评价 gate，原始 JSON 永久保留。新增测试验证这一路径的调用数和原始响应保留。

新兼容恢复运行：`20261013T182413Z-replay-717e62`。仅运行器改变，字体、渲染器、提示词、上游与依赖指纹必须一致才能保留已完成判断；来源与历史调用预算均记录。

## 自然题反馈修复已经验证

兼容恢复运行中，`task_0001` 初稿 87.25，第二候选三轮合并 92.12，终态 QUALITY_PASS。真实 feedback.json 定位的问题由 Astra 写回 build.py，第二版重新构建、渲染和三轮检测。此 4.87 分变化属于 Astra 内部检测的实测配对变化，不是官方 judge 成绩或普遍提升保证。

受控实验 `runs/injected-task_0001-763f2d` 从该真实题最终版本复制源码，翻转原生连接 `instruction_to_agent`（shape_id=101）的箭头端点；原自然题文件保持不变。实验结果单独记录，不计入十题分数。

受控箭头实验的三轮 semantic gate 全部触发，均明确指出 Task Instruction→Agent 被反转为 Agent→Task Instruction，并检查了箭头端点。之后的修复与复测仍在执行，不能仅凭检测成功宣称完整干预实验通过。

四道自然题已完整达标：task_0000=97.00、task_0001=92.12、task_0004=95.50、task_0008=96.25（均 Astra 三轮内部合并分）。受控实验修复后实际 OOXML 的 instruction_to_agent 已恢复 headEnd=none、tailEnd=triangle；复测首轮语义门槛通过。最终实验状态仍以 result.json 为准。

## 受控箭头实验完整通过

`runs/injected-task_0001-763f2d/result.json`：翻转后 gate_count=3、score=0；反馈修复后 gate_count=0、score=92.12。独立读取实际 PPTX 的 arrow_restored=true。共 14 次 Astra/high 调用。该实验不计入自然十题均分。

## 验收停止状态（2026-10-14）

用户确认核心框架搭好且几道真实题通过即可停止，不要求继续完成测试集。因此不再重试、修复或扩大测试。已检查无本工程 ppt-harness / Codex exec 测试进程在运行。

运行 `20261013T182413Z-replay-717e62` 已有七题完成三轮且达到内部阈值：task_0004=95.50、task_0000=97.00、task_0001=92.12、task_0008=96.25、task_0011=96.25、task_0013=94.50、task_0017=100.00。

task_0010 以 STALLED / 0 分结束；task_0015 和 task_0016 记录 INFRA_ERROR / evaluation_complete=false / score=null。task_0015 的独立重试 `20261013T194708Z-94b29a` 同样未通过结构化校验，保留失败记录，不继续重试。不能报告完整十题均分。task_0016 已保存的有效候选及中间检测记录仍可审查。

核心 local-dev 闭环已通过真实题、受控箭头修复和恢复验证；25 项工程测试通过。未完成的坐标契约加固、Linux benchmark 隔离及其他扩展接口仍按 README 标注，未宣称全部规格或全量评测通过。

## 公开发布版本

按用户授权，公开版将模型及推理强度改为配置项，所有智能角色仍只通过 Codex CLI 执行。新运行记录 codex_internal_v1、请求模型与推理强度，改变模型后不能复用旧调用检查点或进行 generation replay。上面的真实题成绩属于原 Astra/high 版本，未因发布版修改而重新运行，也不能用来证明其他模型效果。

发布准备只运行无付费模型调用的工程测试，不恢复先前停止的题目测试。原始日志、PPT、数据集与个人配置不随公开仓库发布。

公开版本发布检查：29 项 pytest 测试通过（包括可配置模型、调用身份与缓存隔离、评分元数据和跨模型 replay 拒绝），pip check 无依赖冲突，editable 安装成功。
