# Bug 跟踪 & 下一轮修改意见

## 当前版本：MVP v0.1（首次实现）
状态：设计完成，实现中

## 一、已知架构风险（设计层面）

1. **Redis 单点故障**
   - 描述：即使开了 AOF+RDB，Redis 进程崩溃到恢复期间（通常 < 5s）所有 Agent 失联
   - 影响：低频但全局
   - 建议：生产环境考虑 Redis Sentinel（两台机器后），当前单机部署接受此风险
   - 优先级：P2（生产前解决）

2. **Coordinator 分布式锁的 30s 空窗**
   - 描述：持锁 Coordinator 崩溃后，最多 30s 内无调度
   - 影响：任务延迟，不影响数据完整性
   - 建议：缩短 TTL 至 15s，或实现更快的心跳检测
   - 优先级：P3

3. **Docker Compose scale 的并发调用问题**
   - 描述：Coordinator 扩缩容时调用 `docker compose scale`，如果执行期间发生错误（Docker 未运行）会崩溃
   - 建议：加 try/except + 超时保护
   - 优先级：P2

4. **WebSocket 客户端数量无限制**
   - 描述：/ws/console 没有连接数限制，大量连接会占用 FD
   - 建议：限制最大 WebSocket 并发连接数（如 50）
   - 优先级：P3

5. **raw_events 表未分区**
   - 描述：初始实现可能没有按天分区，大量数据后查询变慢
   - 建议：首次实现后确认是否使用 pg_partman 分区
   - 优先级：P2

## 二、实现阶段预期 Bug

1. **WebSocket 消息竞争**
   - 位置：api_gateway/main.py WebSocket handler
   - 描述：多个 Agent 同时触发 agent_update 推送时可能有消息顺序错乱
   - 建议：用 asyncio.Queue 序列化推送

2. **Entity 别名解析未实现**
   - 位置：processor/worker.py
   - 描述：EntityResolver 和 EntityRegistrar 是设计中的角色，MVP 可能简化或跳过
   - 建议：MVP 阶段跳过实体归一化，直接存储原始提取值

3. **CSS Selector 提取依赖 BeautifulSoup**
   - 位置：crawler/strategies/http_crawler.py
   - 描述：需要确认 beautifulsoup4 在 requirements 中
   - 建议：检查 pyproject.toml 是否包含 beautifulsoup4 和 lxml

4. **Circuit Breaker 的域名提取**
   - 位置：crawler/worker.py
   - 描述：从 URL 提取 domain 需要处理 subdomain、path 等边缘情况
   - 建议：用 urllib.parse.urlparse(url).netloc 提取

5. **前端 Tailwind 动态类名**
   - 位置：frontend/src/components/monitor/AgentCard.tsx
   - 描述：根据 status 动态拼接 className（如 `border-${color}`）会被 Tailwind purge 删除
   - 建议：用完整类名对象映射，例如：
     ```typescript
     const statusColors = {
       PROCESSING: 'border-blue-500',
       FAILED: 'border-red-500',
       IDLE: 'border-zinc-600',
       DEAD: 'border-zinc-700 opacity-50'
     }
     ```

6. **PostgreSQL 连接池在 Worker 进程中共享**
   - 位置：services/shared/db.py
   - 描述：如果多个 Worker 进程 fork 后共享连接池，会出现连接断开
   - 建议：每个 Worker 进程独立初始化连接池（在 main() 中，不在模块级别）

## 三、功能缺失（MVP 范围外，下一轮实现）

### P1（下一轮必做）
- [ ] SchemaWatcher：schema 漂移检测，目前没有实现
- [ ] FastValidator：实时流轻量验证，目前实时路径没有验证
- [ ] MissionTracker 完成检测：当前 MVP 可能没有精确的 job 完成计数
- [ ] RetentionAgent：数据清理，raw_events 会无限增长
- [ ] 认证/鉴权：/api/* 端点完全开放，生产前需要加 API Key

### P2（下下轮）
- [ ] Browser Crawler（Camoufox/Zendriver）：MVP 只实现了 httpx，浏览器渲染未实现
- [ ] DrissionPage 双模式：Cloudflare 绕过未实现
- [ ] EntityRegistrar：实体字典初始化
- [ ] Prometheus 指标暴露：/metrics 端点
- [ ] 前端历史任务对比功能
- [ ] 数据导出（CSV/JSON）

### P3（未来）
- [ ] LLM 提取策略（Crawl4AI magic 模式）
- [ ] 多用户隔离（Mission 权限管理）
- [ ] 数据可视化（时间线图、字段分布）
- [ ] Webhook 通知（任务完成时回调）

## 四、测试覆盖缺口

- [ ] Coordinator 自动扩缩容逻辑没有集成测试
- [ ] WebSocket 并发推送测试缺失
- [ ] PostgreSQL 分区清理 RetentionAgent 没有测试
- [ ] Docker Compose 健康检查端点（/health）没有测试
- [ ] 端到端流程测试（创建 Mission → 数据入库全流程）

## 五、下一轮开发优先级

### Sprint 2 目标（下一轮）
1. 补全 SchemaWatcher + FastValidator
2. 实现 DrissionPage 爬虫策略（Cloudflare 绕过）
3. 加 /health 端点和 Docker healthcheck
4. 前端数据导出功能
5. 修复所有 P1/P2 bug

### 技术债务
- [ ] 统一日志格式（structlog JSON）
- [ ] 配置文件统一（目前散落在各服务 main.py 里）
- [ ] 服务发现：目前 Worker 通过环境变量找 Redis，考虑服务注册

---
*最后更新：2026-05-12 | 版本：MVP v0.1*
