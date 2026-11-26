# Auto Marketing System 接管入口

[统一交接页](https://app.notion.com/p/423f58e7c06e8149bb34d5b53c085811) · [用户指定的 Hub](https://app.notion.com/p/41ef58e7c06e81d3ba89e9864692a34d) · [业务记录与八库](https://app.notion.com/p/41cf58e7c06e80b2b852dcde8e4ff627) · [DK Service 验收与附件入口](https://app.notion.com/p/41ef58e7c06e81bfbe2ff2e3733df374)

## 技术决策
指定 Hub 作为导航。业务写入使用已有中文双语八库，完整字段和 Relation 目标见 research/notion-map.json。2026-11-26 清点了 20 条记录（品牌2、Topic 2、参考11、灵感0、素材1、创意1、任务1、报告2）；指定 Hub 八库均为空。禁止按标题自动建库或双写。查询自动化键后更新对应页面，多个匹配应停下排查；Notion 并发写入仍待接入唯一键队列。人工灵感需保留。

Supabase 可选作采集暂存，Notion 管研究关系和审核，现有 Windows 引擎负责制作和发布队列。引擎入口 README.zh-CN.md、engine/pipeline.py、engine/publishers.py；历史交付见 HANDOFF.md。回放使用 intelligence/n8n-real-dataset-replay.json（手动、已去作者和媒体链接）。build_n8n_replay.py 从脱敏快照重建它。禁止覆盖生产 state。重新领取 unknown 发布任务前先核实平台结果。

## 证据与任务状态
- 仓库含固定脚本英文样片、测试代码及历史 31 项通过记录。另一个已存档的 DK Service 验收记录载明 65 张关键帧、20.3 秒内部预览、25 项本地校验和 1 条合格采集；10 条缺链接记录已隔离。两套测试口径独立。
- 既有 n8n [历史回放 execution 2](https://alicesnack.app.n8n.cloud/workflow/VSKVIziZEzc0ZyPF/executions/2) 和 [实时读取草案](https://alicesnack.app.n8n.cloud/workflow/iOsLrhSyWy0Xbgjs) 由验收页记载。原始媒体、预览与实际剪辑蓝图附件保留在原 Notion 记录。本次未复跑这些云服务。
- GPT/Claude 实时多模态分析、自动同步 Notion、每日调度、云渲染和真实发布均待验收。YouTube/Instagram 有适配代码，TikTok/小红书输出手动包。尚缺留存和新增关注归因。研究输出须列事实、推断、未知和证据，不做综合打分。

## 操作顺序
1. 离线运行 `python -m unittest discover -s tests`。进入 intelligence 安装 requirements.txt 后运行 `python -m unittest test_core test_live_data`。运行 `python media_smoke.py` 验证合成素材处理；实际分镜示例为 examples/internal-preview.json。统一使用 blueprint.schema.json 的秒制时间轴和 core.validate_blueprint。匹配器 core.match_references 接收品牌、Topic、对标证据和授权素材。make_internal_preview.py 说明真实素材适配和 FFmpeg 渲染；复现须从内部资料取得原片和 Notion 导出。transcribe_local.py 还需 faster-whisper、numpy 和本地模型。
2. 云采集模板与部署流程见 [research/README.md](research/README.md)。先重放免费测试数据，检验缺 URL 隔离、两条以上笔记的模型结果归属、重复执行的唯一性；核对原始指标与未知值。真实调用需获批费用并设上限。
3. 深度研究使用 [video-analysis.md](research/video-analysis.md)。仅取得授权后准备真实关键帧、字幕及音轨，逐条附证据。Notion 自动回写须先在测试记录上验证重试、429 与冲突处理。每日调度以完整运行记录验收。
4. 保留内部预览审核。按 docs/STAGES.md 校验真实品牌、账号和结果，审核通过再启用相应平台。关联任务、输出与指标快照，报告曝光、留存及关注的采集窗口和分母。
