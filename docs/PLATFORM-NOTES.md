# 平台和成本说明

核实日期：2026-11-14。以下链接来自平台官方文档或项目维护者，规则可能变化，账号控制台的实际权限仍需验证。

| 平台 | 当前接入方案 | 需要的账号条件 | 本项目实际状态 |
|---|---|---|---|
| YouTube Shorts | Data API resumable upload，设置元数据，轮询处理状态 | Google Cloud 项目启用 API、桌面 OAuth 客户端、目标频道授权 | 上传/查询代码已写，未实号联调 |
| Instagram Reels | Facebook Login for Business + 本地文件 resumable upload | Professional 账号、关联 Page、相应权限和 token；额外审核取决于使用场景 | 容器创建、上传、轮询、publish、读取 permalink 代码已写，未实号联调 |
| TikTok | 先生成待发布包；后续评估账号可用渠道 | Direct Post 的应用审核和用户授权不能被一个 token 代替 | 不声称已实现无人值守公开发布 |
| 小红书 | 先生成待发布包；后续验证正式权限或允许的网页流程 | 已登录账号以及真实可用发布路径 | 未实现自动发布 |

YouTube 官方修订历史在 2026-11-02 更新：未验证 API 项目的视频不再统一限制为私密。OAuth 配置、账号权限和配额仍然存在。本项目默认 private 是测试配置，不能把 uploaded_private 算成公开发布。横竖比例/时长满足条件不等于平台一定完成 Shorts 分类。

- [YouTube 修订历史](https://developers.google.com/youtube/data/revision_history)
- [YouTube 上传接口](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert)
- [YouTube resumable upload](https://developers.google.com/youtube/data/guides/using_resumable_upload_protocol)
- [Instagram Content Publishing](https://developers.facebook.com/documentation/instagram-platform/content-publishing)
- [TikTok 内容分享要求](https://developers.tiktok.com/doc/content-sharing-guidelines/)
- [TikTok Direct Post](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post/)
- [小红书授权范围](https://openaccount.xiaohongshu.com/docs/scope)

TikTok 官方列出的不可接受使用情形包括仅为自己或团队管理的账号上传的工具。未审核客户端另有可见性限制。即便存在第三方发布服务，也不能预设其免费方案支持所有公司和所有平台。

小红书公开 scope 页面将 write_notes 标为规划中，并说明特定场景需额外材料；小程序引导用户发笔记也不等于通用服务器自动发笔记 API。

## 热词与搜索

本项目内建 Google Trends RSS 解析，可以定时获取区域搜索趋势；它不代表小红书热榜，也不代表 Instagram hashtag 增长。CSV 中只有提供相同口径的 current_value 和 previous_value 才计算增幅，零基数或缺失值不制造增长百分比。用户须确保 period_hours、地域和指标口径一致。

SearXNG 接口用于可选联网检索，返回未标注发布时间的内容只当灵感，不当“今日上升热词”。需自行部署或连接允许 JSON 查询的实例，代码不会假定公共实例稳定可用。

- [Google Trends 的 RSS/CSV 导出](https://support.google.com/trends/answer/3076011)
- [SearXNG Search API](https://docs.searxng.org/dev/search_api.html)
- [TikTok Creative Center](https://ads.tiktok.com/creative/creativeCenter/trends/hashtag)
- [新榜的 API 服务入口](https://www.newrank.cn/account/api)

TikTok Creative Center 可以查看公开趋势。新红属于新榜的第三方分析产品；本项目未取得其免费长期 API 授权，不把它列为零成本必需组件。Instagram 没有为本项目验证可用的全站热词免费榜单接口。

## 浏览器发布扩展的判断

开源项目 [social-auto-upload](https://github.com/dreammis/social-auto-upload) 提供多个平台的网页上传实现，维护者文档也覆盖小红书和 TikTok。当前没有下载、安装或执行该项目，也没有把其“上传成功”返回值接入本系统。后续需要检查具体版本、账号会话、页面变化和平台条款，完成一次真实账号测试才能开启。遇到验证码或登录校验由用户处理，不做绕过。

## 零订阅费技术栈

| 组件 | 本地方案 | 必需软件订阅费 |
|---|---|---:|
| 调度/队列 | Python + SQLite + Windows Task Scheduler | 0 |
| 脚本模型 | Ollama + 本地 Qwen3 4B | 0 |
| 配音 | 已安装 Windows 语音；可选 Piper | 0 |
| 剪辑/字幕/封面 | FFmpeg + Pillow | 0 |
| 基础趋势 | 可用 RSS / 用户授权数据导入 | 0 |
| 官方发布 | 平台 API，在账号许可和配额内 | 无必需第三方订阅 |

[Qwen3 4B](https://ollama.com/library/qwen3:4b) 的模型文件约 2.5GB，可先用于这台 6GB 显存电脑的脚本任务；实际速度和内存余量仍需安装后验证。Piper 的引擎和具体声音模型许可需分别确认，不能把引擎开源等同于所有声音均可商用。

- [Ollama Generate API](https://docs.ollama.com/api/generate)
- [Piper 项目及声音许可链接](https://github.com/OHF-Voice/piper1-gpl)

零软件订阅费不等于零电费或零维护成本。没有购买云服务器、付费热榜、代理、付费生成 API 或发布 SaaS。电脑睡眠或关机时，本地工作流不能持续制作和上传。
