# 本地多公司 AI 营销工作流 · v0.1

这是一份已完成本地视频制作测试的可运行首版，**尚未完成四平台账号上线**。

2026-11-14 已用本机现有 FFmpeg 和 Windows 英文语音生成 1080×1920、约 16.7 秒的 MP4 演示片。它使用固定演示脚本，不证明本地大模型已经安装或能生成真实品牌视频。演示视频带有 DEMO 标记，程序禁止自动发布。

## 当前可以做什么

- 多公司配置隔离：独立品牌事实、素材、关键词、语言、账号和 CTA。
- 趋势输入：Google Trends RSS、其他 RSS、自建 SearXNG 搜索、带时间戳的 CSV。
- 本地脚本生成：Ollama 接口及 JSON/长度/禁用词/素材引用验证，需先安装模型。
- 视频制作：图片或视频素材、竖屏剪辑、系统配音或 Piper、分镜级字幕、封面、完整解码验证。
- 分发队列：YouTube 与 Instagram 官方 API 适配代码；TikTok、小红书生成待发布包。
- 可靠性：数据库去重、并发领取、防止不明状态重发、七天数据库备份。
- 转化反馈：UTM 和指标 CSV；最新累计快照参与下一轮选题权重。
- 每日任务：本地守护进程与 Windows 任务安装脚本，处理 Copenhagen 夏令时。

## 仍未完成的部分

真实公司资料和素材尚未提供；Ollama 模型未安装；实际账号未授权；联网趋势和官方 API 没有完成在线联调；中文语音未安装；TikTok/小红书的自动发布适配尚未实现；尚未部署生产 Windows 定时任务或连接 CRM。详细阶段见 [STAGES.md](docs/STAGES.md)。

## 最快查看

1. 将整个目录放在固定位置，例如 `A:\workspace\marketing-engine`，保留文件结构。
2. 双击 `start.cmd` 打开本地控制窗口。当前电脑若依赖可用，可直接查看诊断或制作演示。
3. 打开 `examples/demo/video.mp4` 查看已生成样片。
4. 打开 `docs/STAGES.md` 和 `docs/PLATFORM-NOTES.md` 查看真实完成状态与平台限制。

当前生成样片用的是本机已经安装的 Stremio 所带 FFmpeg，仅调用该可执行文件，没有修改 Stremio。路径记录在 `config/machine.json`。迁移电脑后删除这个配置文件，或换成本机 FFmpeg 路径，或使用下方安装流程附带的 FFmpeg。

## 安装运行依赖

在普通 PowerShell 打开项目目录，执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

这会在项目内建立 `.venv` 并安装免费 Python 依赖。没有调用付费 API。当前 ChatGPT 执行环境的 DNS/网络限制导致自动安装失败，需在能联网的普通终端完成。

从 [Ollama 官方下载页](https://ollama.com/download/windows) 安装 Ollama，然后：

```powershell
ollama pull qwen3:4b
.\run.cmd doctor
```

模型尚未下载，约需数 GB 磁盘和下载流量。6GB 显存先从 4B 脚本模型开始，不把整段生成式视频列为基础依赖。

本机只检测到 `Microsoft Zira Desktop / en-US` 语音。英文演示可用；中文品牌需要安装 Windows 中文语音或配置已确认可商用的 Piper 声音。找不到所需语言的声音时会中止，不会静默用错误语言配音。

## 加入一家公司

复制 `templates/brand.json` 到 `brands/your_brand.json`，填写：

| 字段 | 内容 |
|---|---|
| id | 公司唯一 ID，只用小写英文字母、数字、短横线或下划线 |
| name / offer | 公司名称、产品或服务 |
| target_customer / language | 目标人群、地区和视频语言 |
| approved_facts | 可以用于营销的真实事实，一项一句；价格/效果/认证要有依据 |
| facts_reviewed | 上述内容核对完成后设为 true |
| cta / landing_url | 下一步行动和已有 HTTPS 落地页；没有网站可先留空 |
| allowed_terms / banned_phrases | 相关话题与禁止出现的表达 |
| videos_per_day | 初始建议 1；当前允许 1–10 |
| platforms | 需要输出的四个平台名 |
| enabled | 素材和模型准备好后设为 true |
| auto_publish | 首批样片验收后可设 true，后续无需每条人工审批；仍需账号启用 |

将素材复制到 `assets/your_brand/`，参照 `templates/asset.example.json` 填写 `data/assets.json`。图片和 MP4 可用。素材登记必须含品牌、商用权限与依据；过期授权不参与生成。这里只引用灵感，不自动下载或搬运别人的视频。

将关键词加入 `data/keywords.csv`。灵感/自己的脚本记录加入 `data/inspirations.json`，示例在 templates。每家公司至少先给 5 份自有素材、10 个关键词，以及 3 条可以使用的品牌事实。

```powershell
.\run.cmd run --brand your_brand
.\run.cmd report
```

一条内容输出 `video.mp4`、`cover.png`、`captions.srt`、`script.json`、`quality.json`，以及各平台的文案和 post.json。实际视频为同一母版，文案按平台区分；当前不自动为四个平台重剪四种版本，也不自动翻译成四种语言。

## 连接账号

### YouTube

1. 在 Google Cloud 开启 YouTube Data API，创建桌面应用 OAuth 客户端。
2. 把客户端 JSON 保存在本机 `secrets/youtube-client.json`。不要发到聊天中。
3. 填写品牌 `youtube.channel_id`，用频道 ID 而不是 handle。
4. 执行以下命令并在浏览器里亲自授权：

```powershell
.\run.cmd auth-youtube your_brand .\secrets\youtube-client.json
```

会核对登录频道与配置一致，凭据留在本机。OAuth 测试模式的刷新令牌可能过期；要长期运行需按 Google 要求配置同意屏幕并处理所需验证。将 `youtube.enabled` 设 true。初次测试保留 privacy=private；准备好公开后才改为 public 并生成新的任务。

### Instagram

这个实现选择 Facebook Login for Business，以便本地直传 MP4，不依赖另购公网文件存储。需要 Professional 账号和关联的 Facebook Page，以及 `instagram_basic`、`instagram_content_publish`、`pages_read_engagement` 等适用权限；具体要求见官方文档。

填写品牌 `instagram.account_id`（IG 专业账号 ID），将 Page access token 保存在品牌 `token_env` 指定的本机环境变量，或 `secrets/your_brand-instagram.json`：

```json
{"access_token": "仅在本机填写"}
```

设置 `instagram.enabled=true`。代码没有提供完整 Meta 开发者后台设置向导，也没有保证 Page token 永不过期；账号授权变化时需要重新连接。

### TikTok / 小红书

当前导出完整发布包，状态是 manual，表示**未自动发布**。不能通过打开 auto_publish 把它们变成已支持的 API 发布渠道。后续需基于你真实账号验证可用权限或网页发布方案；TikTok 内部自用工具不符合 Direct Post 的适用范围。详见 PLATFORM-NOTES。

## 定时运行

`config/settings.json` 默认 Copenhagen 时区 09:00 生成、18:00 开始分发。可按公司主要受众修改。当前为全局时间；不同公司独立时区和错峰时段是后续扩展。

公司、模型和账号准备好后，二选一：

```powershell
# 保持终端运行，关闭或电脑休眠会停止执行
.\run.cmd daemon

# 或者注册 Windows 定时任务，每五分钟检查一次
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-scheduler.ps1
```

Windows 任务在已登录用户下执行，不保存系统密码。它不是服务器，关机/休眠时不会制作视频。任务安装器的目标时间精度约五分钟，上传耗时和平台处理也会影响最终出现时间；它不是平台原生定时发布功能。

暂停：结束 daemon，或在任务计划程序禁用 `LocalMarketingEngine`。卸载：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-scheduler.ps1 -Remove
```

只设置 enabled 的真实公司会参与运行；演示公司始终不会自动发布。若没有配置真实公司，任务只报告阻塞状态。

## 状态含义与恢复

| 状态 | 含义 |
|---|---|
| review | 等首批人工审核，可用 approve 放行 |
| ready | 已允许发布，等待时间和账号 |
| manual | 已导出，但该渠道需用户完成发布 |
| sending | 工作进程已领取，可能正在产生远端操作 |
| submitted | 远端正在处理；稍后查询 |
| published | 已得到符合公开发布判定的远端记录 |
| uploaded_private / uploaded_unlisted | 上传成功，但不是公开营销发布 |
| blocked | 账号、文件或配置等前提不满足 |
| unknown | 发布结果不确定；核查平台后再处理，禁止盲目重发 |
| failed | 生成或平台处理失败 |

审核单条待审任务：

```powershell
.\run.cmd approve JOB_ID
.\run.cmd publish
```

`publish` 只领取已到时间的任务。品牌 auto_publish=true 后，新任务无需逐条 approve。更改已生成任务的目标账号会阻塞，需重新生成并核对，防止串号。

生成进程异常退出且确认没有其他生成进程运行后：

```powershell
.\run.cmd recover-generation
.\run.cmd run
```

这个命令只恢复生成阶段，不会自动重发 unknown 的发布任务。state 数据库包含发布会话信息，应留在本机。备份只覆盖数据库，不覆盖素材、模型、账号凭据；要做完整备份需另行备份这些本地文件。

## 获客闭环

将平台数据和落地页/CRM 数据按 `data/metrics.csv` 字段导入；每行是该任务截至该日的累计值。`report` 会只取同一任务最新快照，避免累计值重复相加。拥有至少 100 次观看的样本，其合格咨询转化率会给下一轮相关关键词少量加权；不是成熟的归因模型或自动投放优化。

UTM 只能帮助归因，不能让平台不支持的正文链接变成可点击链接。Instagram、小红书和 TikTok 需要根据实际账号配置主页入口或平台允许的组件。当前没有自动私信、自动添加联系人、采集私人数据或投放广告。

## 测试与日常维护

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\run.cmd doctor
.\run.cmd status
.\run.cmd report
```

真实发布前还需要：至少一次账号级上传测试、一次当天趋势读取、一条真实公司样片、一次第二天定时运行。测试通过不能保证营销转化率；质量与获客效果需要用自己的素材和真实数据校准。
