# 小红书研究工作流

本目录整合原 xhs_n8n_mvp.json、supabase_schema.sql 与部署说明。工作流为未激活的手动模板，独立于已有回放。Apify 输入关键词和上限在 Config。只保留有来源链接的成功视频记录，按实际收藏数、笔记 ID 稳定排序，取 topN。未知指标为 null；暂存原始指标以便复核。被过滤的搜索结果可在 Apify 数据集复核。缺失 URL 不补造。

在测试 Supabase 项目执行 supabase_schema.sql；既有旧表兼容可空指标，历史零值来源需单独复核。通过 n8n Cloud 导入 JSON。将两个 Save 节点的 REPLACE_PROJECT_REF 替换为项目引用。为它们选择 Custom Auth 凭证，headers 同时包含 apikey 与 Authorization（Bearer 服务端密钥）。Apify、GPT 选择各自的 Header Auth（Authorization: Bearer …），Claude 使用 x-api-key。密钥只填凭证管理。先以手动回放测试，付费调用需批准。当前同步 Actor 超时或返回不明时先查 run，避免重复计费。

两个模型在此路径仅接收元数据；每个结果按笔记 ID 写入最新分析。SQL 中的 snapshots 表预留历史采样，当前工作流未写入。云端 Notion 适配器、媒体处理和模型费用累计限制仍待实现。离线匹配输入示例见 fixture.json；运行及审核顺序见 ../AGENTS.md。
