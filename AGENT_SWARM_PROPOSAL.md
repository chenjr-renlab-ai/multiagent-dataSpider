# K 级多智能体数据采集工具 — 技术方案

> 通用版：面向通用 Web 数据采集的千级 Agent 协作系统设计
> 版本：v1.0 | 日期：2026-05-12

---

## 一、背景与目标

传统数据采集方案依赖人工维护数据源列表，扩展成本高，跨站点适配能力弱。

本方案设计一个**独立的通用 Web 数据采集层**，核心理念是：

> **给定一个目标（如"采集某电商平台商品数据"），系统能自主决定去哪里拿数据、需要什么格式、组建多大的团队、是批量采集还是实时监听**，而不依赖人工维护数据源列表。

可作为独立工具运行，也可作为上游数据管道接入任何下游数据消费系统。

---

## 二、参考项目与选型依据

| 方向 | 最值得参考的项目 | 核心借鉴点 |
|------|----------------|-----------|
| 多 agent 框架 | **CrewAI**（50.8k ⭐）、**LangGraph**（生产最广） | 角色驱动分工；图状态机 + 任务持久化 |
| 分布式爬取 | **Crawlee**（17.7k ⭐）、**Scrapy-Cluster**（1.8k ⭐） | 零配置反爬指纹；Redis 任务队列分发模型 |
| 千级 agent 理论 | **MacNet**（ICLR 2025，arXiv 2406.07155）| Chain 拓扑最适合流水线，性能随数量呈 logistic 增长 |
| 并发架构 | **Project Sid**（arXiv 2411.00114，PIANO 架构）| 并行信息聚合 + 神经编排，实时多流并发 |
| 可观测性 | **OpenLLMetry**（6.6k ⭐）、**Langfuse**（6k ⭐） | 零侵入 OTel trace；自托管友好 |

---

## 三、整体架构

系统分为**六层**，数据严格单向串行流动（不是 Coordinator 同时分发给所有层）。

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Tier 0 · 战略规划层（按任务激活，常态 0 实例）                           │
│                                                                          │
│  GoalInterpreter → ScoutAgent → SchemaDesigner → TeamAssembler          │
│                         │             │          └─[MissionTracker 子模块]│
│                  RealTimeController   │                                  │
│                              EntityRegistrar（启动/每周同步实体字典）      │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │  Mission Spec + TeamConfig
┌──────────────────────────────────▼───────────────────────────────────────┐
│  Tier 1 · 协调层（×2 副本，分布式锁 SET NX 保证单主调度）                 │
│  MissionCoordinator ←→ Redis Streams（任务总线）                         │
│  Scheduler（Redis Sorted Set 定时任务）  Dead Letter Queue               │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │ Job Envelope → crawl_jobs Stream
┌──────────────────────────────────▼───────────────────────────────────────┐
│  Tier 2 · 采集层（Strategy 0~6，按站点防护等级选工具）                    │
│  APIHarvester / StaticCrawler / DrissionPage / Scrapling Stealth         │
│  Camoufox / Zendriver / Crawl4AI                                        │
│  ─────────────────────────────────────────────────────────────────────  │
│  StreamCrawler（实时 WS/SSE，独立通道，不走 crawl_jobs）                  │
└────────────────┬─────────────────────────────────┬───────────────────────┘
                 │ raw_data Stream                  │ live_events Stream
                 ▼                                  ▼
┌────────────────────────────┐     ┌────────────────────────────────────┐
│  Tier 3 · 处理层           │     │  FastValidator（< 5ms 轻量验证）    │
│  Preprocessor              │     │  字段存在性 + 类型 + 值域范围检查   │
│  SchemaMapper              │     └──────────────────┬─────────────────┘
│  EntityResolver            │                        │ 通过 → EventPublisher
│  Deduplicator              │                        │ 拒绝 → dead_letters
│  Normalizer                │
└────────────────┬───────────┘
                 │ clean_data Stream
┌────────────────▼───────────────────────────────────────────────────────┐
│  Tier 4 · 验证层                                                       │
│  ConsistencyChecker  FreshnessGuard  CredibilityScorer                 │
│  AnomalyDetector  CrossSourceComparator                                │
│  SchemaWatcher（每小时 schema diff，漂移时暂停数据源）                   │
└────────────────┬───────────────────────────────────────────────────────┘
                 │ validated_data Stream
┌────────────────▼───────────────────────────────────────────────────────┐
│  Tier 5 · 存储与交付层                                                  │
│  StoreAgent → PostgreSQL（按天/月分区，pg_partman 管理）+ Redis Cache   │
│  EventPublisher → Redis Pub-Sub / WebSocket（实时下游）                 │
│  APIGateway → REST / GraphQL（下游数据消费系统消费）                     │
│  RetentionAgent（每日 03:00 UTC 执行分区清理）                          │
└────────────────┬───────────────────────────────────────────────────────┘
                 │
┌────────────────▼───────────────────────────────────────────────────────┐
│  前端控制台（React 18 + Zustand + Tailwind + Vite）                     │
│  Mission 触发界面 ←→ WebSocket ws://localhost:8080/ws/console           │
│  Agent 实时监控面板（分层卡片 + 迷你拓扑 SVG）                           │
└────────────────────────────────────────────────────────────────────────┘
                 │
          下游数据消费系统
```

### 双管道并行

```
批量管道（Batch）：  Tier-0 规划 → crawl_jobs → Tier-2 → raw_data
                    → Tier-3 → clean_data → Tier-4 → validated_data → Tier-5

实时管道（Stream）：StreamCrawler → live_events → FastValidator
                    → EventPublisher（WebSocket 直推，< 100ms）
```

**关键修正：** Tier-2/3/4 之间是严格串行的 Stream 连接，Coordinator 只向 Tier-2 投递 Job，不直接操作 Tier-3/4。实时管道完全独立，绕过批量处理链，FastValidator 是实时路径上唯一的质量关卡。

---

## 四、Tier-0 战略规划层（新增）

这是整个系统最核心的创新：**不需要人工维护数据源列表，由 agent 自主发现并决策**。

---

### 4.1 GoalInterpreter（1 个）

**输入：** 自然语言目标，如"采集某电商平台全量商品价格及库存数据"

**职责：**
- 解析目标，提取关键维度：采集目标/数据集/字段范围/截止时间/用途
- 确定需要哪些数据类型（价格 / 历史数据 / 库存状态 / 新闻资讯 / 实时动态）
- 评估时效性需求：是批量离线（T-24h 前）还是实时监听（变更时触发）
- 输出：**DataRequirementSpec**（结构化的数据需求说明书）

```json
{
  "mission_id": "ecommerce-products-2026",
  "data_types": ["price", "inventory", "description", "reviews", "live_updates"],
  "freshness": { "price": "realtime", "inventory": "T-2h", "description": "T-24h" },
  "deadline": "2026-05-10T14:00:00Z",
  "output_schema_version": "generic-v1"
}
```

**不做：** 不选择数据源，不设计 schema，不分配 agent——职责止于理解目标

---

### 4.2 ScoutAgent（2~3 个，可并行）

**输入：** DataRequirementSpec

**职责：**
- 根据数据类型，主动搜索（WebSearch）和评估可用数据源
- 对每个候选源判断：公开免费 / 需要登录 / 需要付费 / 有官方 API
- 评估反爬难度（静态/动态/有 Cloudflare 等）
- 对已知可靠源（开放 API、公开数据集、权威新闻站等）直接加入
- 输出：**SourceCatalog**（数据源清单，含访问方式和优先级）

```json
{
  "sources": [
    { "id": "target-api",     "url": "https://api.example.com/items", "type": "api",     "auth": false, "priority": 1, "data": ["price","inventory"] },
    { "id": "aggregator",     "url": "https://aggregator.example.com/", "type": "browser", "auth": false, "priority": 1, "data": ["price"] },
    { "id": "official-site",  "url": "https://www.example.com/catalog", "type": "static",  "auth": false, "priority": 1, "data": ["description","history"] },
    { "id": "member-portal",  "url": "https://members.example.com/",  "type": "browser", "auth": true,  "priority": 2, "data": ["exclusive_data"] }
  ]
}
```

**不做：** 不实际爬取，只做侦察和评估

---

### 4.3 SchemaDesigner（1 个）

**输入：** DataRequirementSpec + SourceCatalog

**职责：**
- 根据下游需求（下游数据消费系统的输入格式）设计统一 DataRecord Schema
- 建立字段映射表（各源的原始字段 → 标准字段）
- 确定实体规范化规则（采集目标名称 / 类目 ID / 数据集标识的标准化方案）
- 输出：**SchemaSpec**（JSON Schema + 字段映射 + 实体字典）

**为什么需要这个角色：** 不同数据源对同一采集目标的命名可能有多种变体（如产品名、SKU、编号等多种形式），必须在入库前统一，否则跨源比对会失效。

---

### 4.4 RealTimeController（1~2 个）

**输入：** DataRequirementSpec 中标记为 `freshness: realtime` 的字段

**职责：**
- 决定哪些数据需要 WebSocket/SSE 长连接（实时价格变动、即时推送通知）
- 决定哪些数据用高频轮询替代（无流接口但需要准实时）
- 为 StreamCrawler 生成订阅配置
- 监控实时流的健康状态，断线自动重连

**输出：** StreamConfig（StreamCrawler 的订阅清单）

---

### 4.5 TeamAssembler（1 个）

**输入：** SourceCatalog + SchemaSpec + 当前资源约束（CPU/内存预算）

**职责：**
- 计算每种 Crawler 子类型需要多少个（基于源数量 × 页面深度 × 爬取频率）
- 决定 Preprocessor / Validator 数量（基于预估数据量）
- 生成 **TeamConfig**，驱动 Coordinator 动态启动对应数量的 worker
- 当任务完成或负载下降时，发出缩容指令释放资源

```json
{
  "static_crawlers": 120,
  "browser_crawlers": 80,
  "auth_crawlers": 40,
  "stream_crawlers": 30,
  "preprocessors": 60,
  "validators": 40,
  "estimated_duration_min": 45
}
```

**这是"按需组建团队"的核心机制**——不是固定启动 1000 个 agent 常驻，而是根据任务规模动态决定规模，用完释放。

---

## 五、Tier-2 采集层：按站点防护等级选策略

**核心原则（来自 last30days-skill 的实践）：API-first，能不动浏览器就不动浏览器。** 大多数目标数据站（示例：电商平台/新闻站点/开放 API）在 Network 面板里都能看到 JSON 接口，浏览器自动化只是最后手段。

### 策略分层（从轻到重）

```
Strategy 0  隐藏 JSON API      ← 首选，速度最快，无反爬压力
Strategy 1  纯 HTTP + header   ← API 有签名但规律可破
Strategy 2  DrissionPage 双模  ← 有 Cloudflare 但内容是静态 HTML
Strategy 3  Scrapling Stealth  ← Cloudflare Turnstile 验证
Strategy 4  Camoufox / Zendriver ← Akamai Bot Manager，需 C++ 级指纹
Strategy 5  Scrapling adaptive  ← DOM 频繁重构，selector 维护成本高
Strategy 6  Crawl4AI + magic   ← 快速上线，LLM 提取省写 selector
Strategy 7  StreamCrawler      ← 实时数据推送，WebSocket/SSE 长连接
```

---

### Strategy 0：隐藏 JSON API（前端 SPA 类站点）

大量目标数据站本质是前端 SPA，真实数据通过 XHR/Fetch 请求 JSON API，用浏览器 DevTools Network 面板抓包即可获得接口地址。

```python
import httpx, asyncio

# 抓包后还原的真实接口（x-mas header 有规律可循）
SITE_HEADERS = {
    "x-mas": "...",   # 通过分析 JS bundle 可还原生成算法
    "referer": "https://api.example.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

async def get_items(page: int):
    async with httpx.AsyncClient(headers=SITE_HEADERS) as client:
        r = await client.get(f"https://api.example.com/items?page={page}")
        return r.json()  # 直接拿到结构化数据，无需解析 HTML
```

**适用站点：** 具有隐藏 JSON API 的 SPA 站点（电商平台、数据聚合站、开放 API 等）

---

### Strategy 1：纯 HTTP + TLS 指纹伪造（Scrapling Fetcher）

对有基础反爬但无 JS 挑战的站点，用 Scrapling 的 `Fetcher` 模拟真实浏览器 TLS 握手，比 requests 更难被识别。

```python
from scrapling.fetchers import Fetcher

page = Fetcher(auto_match=True).get(
    "https://www.example.com/catalog/list",
    stealthy_headers=True,   # 自动生成真实浏览器 header 组合
    follow_redirects=True
)
# CSS 选择器提取，auto_match=True 记录元素特征，改版后自动重定位
data_table = page.css("table#data_records", auto_match=True).first
```

---

### Strategy 2：DrissionPage 双模式（静态内容 + Cloudflare 类站点）

**最重要的实战方案。** 浏览器模式通过 Cloudflare 拿到 Cookie，立刻切到 HTTP 模式批量爬取，速度比全程浏览器快 10 倍以上。适用于有 Cloudflare 防护但内容为静态 HTML 的数据站。

```python
from DrissionPage import ChromiumPage, SessionPage, ChromiumOptions

# Step 1：浏览器模式，过 Cloudflare（一次性）
opts = ChromiumOptions()
opts.set_argument("--disable-blink-features=AutomationControlled")
browser = ChromiumPage(addr_or_opts=opts)
browser.get("https://www.example.com/data/catalog")
# Cloudflare 挑战自动完成，cookies 已写入

# Step 2：导出 cookies 给 Session，切到 HTTP 高速模式
session = SessionPage()
session.set.cookies(browser.cookies())
browser.quit()  # 浏览器只用一次，立即释放内存

# Step 3：HTTP 模式批量翻页（无浏览器开销）
results = []
for page_num in ["page=1", "page=2", "page=3"]:
    resp = session.get(f"https://www.example.com/data/catalog?{page_num}")
    table = resp.html.css_first("table#data_records")
    results.append(table)
```

**适用站点：** 具有 Cloudflare 防护的静态内容数据站（新闻站、数据目录、内容聚合站等）

---

### Strategy 3：Scrapling StealthySession（Cloudflare Turnstile 类站点）

对使用 Cloudflare Turnstile 的站点，`solve_cloudflare=True` 自动处理挑战，维持有状态 Session。

```python
from scrapling.fetchers import StealthySession

with StealthySession(
    headless=True,
    solve_cloudflare=True,   # 自动过 Turnstile
    block_images=True,       # 节省带宽，采集数据不需要图片
) as session:
    # 先访问首页建立信任记录
    session.fetch("https://www.example.com/")
    # 再爬目标页面，Session 状态自动保持
    page = session.fetch("https://www.example.com/data/list/category-a/")
    records = page.css(".data__item", auto_match=True).getall()
```

**适用站点：** 使用 Cloudflare Turnstile 防护的数据站（价格聚合站、内容平台等）

---

### Strategy 4：Camoufox + Zendriver（Akamai Bot Manager 类高防护站）

部分高防护数据站使用 Akamai Bot Manager，会在 WebGL、AudioContext、WebRTC 多维度做 bot 检测。Camoufox 在 **C++ 层**（不是 JS 层）修改这些属性，检测不出异常。

```python
# Camoufox：C++ 级 Firefox 指纹伪造
from camoufox.async_api import AsyncCamoufox
from browserforge.fingerprints import FingerprintGenerator

gen = FingerprintGenerator(browser=("firefox",), os=("windows", "macos"))

async def scrape_protected_site(item_id: str):
    async with AsyncCamoufox(
        fingerprint=gen.generate(),
        headless=True,
        geoip=True,    # 地理位置与代理 IP 自动一致
        proxy={"server": "http://residential:8080", "username": "u", "password": "p"}
    ) as browser:
        page = await browser.new_page()
        await page.goto(f"https://www.example.com/items/{item_id}")
        await page.wait_for_selector("[data-testid='item-detail']", timeout=10000)
        return await page.inner_text("[data-testid='item-detail']")
```

```python
# Zendriver：原生 CDP 协议，无 WebDriver 痕迹（适合 Shadow DOM 站点）
import asyncio, zendriver as zd

async def scrape_with_zendriver(url: str):
    browser = await zd.start(headless=True)
    page = await browser.get(url)
    await page.wait_for(".item-detail", timeout=10)
    detail = await (await page.find(".item-detail", best_match=True)).get_text()
    await browser.cookies.save("site_session.json")  # 持久化 session
    await browser.stop()
    return detail
```

**适用站点：** 使用 Akamai Bot Manager 或同等强度防护的高防护数据站

---

### Strategy 5：Scrapling Adaptive（DOM 频繁重构类站点）

部分数据站每隔几周重构一次前端，传统 CSS selector 维护成本极高。Scrapling 的 adaptive 模式把目标元素的多维特征存库，改版后自动重新定位同一元素。

```python
from scrapling.fetchers import DynamicSession

with DynamicSession(headless=True, network_idle=True, disable_resources=True) as session:
    page = session.fetch("https://www.example.com/data/records/123")
    # auto_match=True：元素特征入库，页面改版后自动重定位
    field_a = page.css(".record-field-a", auto_match=True).getall()
    field_b = page.css(".record-detail[data-field='b']", auto_match=True).getall()
```

---

### Strategy 6：Crawl4AI（快速上线，LLM 兜底提取）

新数据源快速接入时，用 LLM 描述要提取什么，不写 selector。适合 MVP 阶段或结构不规则的页面。

```python
from pydantic import BaseModel
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai import LLMExtractionStrategy, LLMConfig

class DataRecord(BaseModel):
    item_name: str; item_id: str
    field_a: float; field_b: str; field_c: str
    source: str; updated_at: str

async def scrape_data(url: str):
    strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(provider="openai/gpt-4o-mini"),
        schema=DataRecord.model_json_schema(),
        instruction="提取页面上所有数据记录，包含名称、ID、关键数据字段及来源信息"
    )
    async with AsyncWebCrawler(config=BrowserConfig(browser_type="undetected")) as crawler:
        result = await crawler.arun(url, config=CrawlerRunConfig(
            extraction_strategy=strategy,
            magic=True,           # 自动应用最优反检测参数组合
            cache_mode=CacheMode.BYPASS
        ))
        return result.extracted_content
```

---

### Strategy 7：StreamCrawler（实时数据推送）

实时数据不走批量 Job 队列，直接维持 WebSocket/SSE 长连接，事件写入 `live_events` Stream。

```python
import asyncio, websockets, json
from redis.asyncio import Redis

async def stream_live_updates(ws_url: str, redis: Redis):
    async with websockets.connect(ws_url, extra_headers={
        "Origin": "https://api.example.com",
        "User-Agent": "Mozilla/5.0..."
    }) as ws:
        async for raw in ws:
            event = json.loads(raw)
            if event.get("type") == "data_update":
                await redis.xadd("live_events", {
                    "item_id":  event["itemId"],
                    "field_a":  event["data"]["field_a"],
                    "field_b":  event["data"]["field_b"],
                    "field_c":  event["data"]["field_c"],
                    "ts": event["timestamp"]
                })
```

**断线重连由 StreamCrawler 自动处理，不进入 dead_letters（连接中断是正常现象，不是错误）。**

---

### 站点类型-策略速查表

| 站点类型（示例）| 防护类型 | 推荐策略 | 工具 |
|------|---------|---------|------|
| 有签名 JSON API 的 SPA 站 | 有签名 JSON API | Strategy 0 | httpx + header |
| 开放公共 API 的数据站 | 公开 JSON | Strategy 0 | httpx |
| Cloudflare 防护 + 静态 HTML | Cloudflare + 静态 HTML | Strategy 2 | DrissionPage |
| 内容聚合 + Cloudflare Turnstile | Cloudflare Turnstile | Strategy 3 | Scrapling Stealth |
| 轻度反爬的新闻/资讯站 | 轻度反爬 | Strategy 1 | Scrapling Fetcher |
| 高防护平台（Akamai） | Akamai Bot Manager | Strategy 4 | Camoufox + geoip |
| 前端频繁重构的数据站 | 频繁 DOM 重构 | Strategy 5 | Scrapling adaptive |
| 新数据源（MVP 阶段） | 未知 | Strategy 6 | Crawl4AI + magic |
| 实时推送数据流 | WebSocket/SSE | Strategy 7 | websockets + Redis |

**ScoutAgent 在 SourceCatalog 里标注每个源的防护类型，TeamAssembler 据此自动选择对应策略，无需人工干预。**

---

## 六、Tier-3 处理层（扩充）

| 角色 | 数量 | 职责 |
|------|------|------|
| **Preprocessor** | ~80 | HTML/JSON → 结构化字段，基础去重 |
| **SchemaMapper** | ~60 | 按 SchemaDesigner 生成的映射表，原始字段 → 标准字段 |
| **EntityResolver** | ~40 | 采集目标名称/类目/标识符 → 规范 ID（查字典或 fuzzy match） |
| **Deduplicator** | ~30 | 跨源内容 hash 去重，防止同一数据被多个源重复写入 |
| **Normalizer** | ~20 | 时区统一、数据格式统一（单位换算、编码归一、标准化处理）|

---

## 七、Tier-4 验证层（扩充）

| 角色 | 数量 | 职责 |
|------|------|------|
| **ConsistencyChecker** | ~50 | 跨源同一字段对比，标记异常偏差（如关键数据字段偏差 > 15%）|
| **FreshnessGuard** | ~30 | 监测数据时效，超时未更新触发重爬 Job |
| **CredibilityScorer** | ~30 | 给每条记录打来源可信度分（已知权威源 > 聚合站 > 社媒）|
| **AnomalyDetector** | ~20 | 统计异常检测（数据字段突变、无效值、数据集规模异常）|
| **CrossSourceComparator** | ~20 | 多源数据聚合为单一 consensus 记录，标注分歧字段 |

---

## 八、Tier-5 存储与交付层（扩充）

| 角色 | 数量 | 职责 |
|------|------|------|
| **StoreAgent** | ~15 | 写入 PostgreSQL，更新 Redis 热数据缓存 |
| **EventPublisher** | ~8 | 将验证通过的记录推送到 Redis Pub-Sub，供实时订阅方消费 |
| **APIGateway** | ~7 | 暴露 REST / GraphQL 接口，下游数据消费系统通过此接口拉取数据 |

---

## 九、协作模式

### 9.1 动态组队流程（Mission Lifecycle）

```
用户输入目标
    │
    ▼
GoalInterpreter（1 次 LLM 调用）
    │  DataRequirementSpec
    ▼
ScoutAgent × 2（并行搜索，2~3 次 LLM + WebSearch）
    │  SourceCatalog
    ├──────────────────────────┐
    ▼                          ▼
SchemaDesigner（1 次 LLM）  RealTimeController（1 次 LLM）
    │  SchemaSpec               │  StreamConfig
    └──────────┬────────────────┘
               ▼
         TeamAssembler（1 次 LLM）
               │  TeamConfig
               ▼
        MissionCoordinator
               │  启动 N 个 worker（Docker Compose scale）
               ▼
        [批量管道 + 实时管道 并行执行]
               │
               ▼
        任务完成 → TeamAssembler 发出缩容指令 → worker 优雅退出
```

**Tier-0 总计 LLM 调用：约 6~8 次**（均使用轻量模型 Haiku/DeepSeek，控制成本）

---

### 9.2 消息总线（Redis Streams）

```
Stream 名称          生产者            消费者
─────────────────────────────────────────────────────
crawl_jobs          Coordinator        Tier-2 所有 Crawler
raw_data            Tier-2 Crawlers    Preprocessor, SchemaMapper
clean_data          Tier-3 Processors  ConsistencyChecker, Validator
validated_data      Tier-4 Validators  StoreAgent, EventPublisher
live_events         StreamCrawler      FreshnessGuard, EventPublisher (直通)
dead_letters        任何失败 worker    Coordinator（重试/跳过决策）
```

### 9.3 任务路由规则

每个 Job Envelope 携带 `job_type` 字段，Coordinator 根据此字段路由到对应 Crawler 子类型：

```
job_type: "static"    → StaticCrawler 消费者组
job_type: "browser"   → BrowserCrawler 消费者组
job_type: "auth"      → AuthCrawler 消费者组
job_type: "stream"    → RealTimeController 直接配置 StreamCrawler（不走 Job 队列）
job_type: "api"       → APIHarvester 消费者组
```

---

## 十、容错机制

### 10.1 重试与死信

```
Job 失败 → 重试 3 次（指数退避：2s / 10s / 60s）
         → 仍失败 → dead_letters Stream
                  → Coordinator 决策：
                    - 同类 Job 失败率 < 10%：记录跳过
                    - 失败率 > 10%（该源故障）：触发熔断
```

### 10.2 熔断器

每个数据源（source_id）维护独立熔断状态：
- 连续失败 > 5 次 → 熔断，暂停该源的 Job 投递
- 冷却 300s 后 → 半开，投递 1 个探测 Job
- 探测成功 → 恢复

### 10.3 幂等性

每个 Job 带唯一 `job_id`（`{mission_id}:{source_id}:{url_hash}`），Redis SET 做处理记录，重投递不重复执行。

### 10.4 实时流容错

StreamCrawler 维护心跳检测（30s），超时自动重连，重连后回放最近 5 分钟事件（依赖数据源是否支持回放，否则标记 gap）。

### 10.5 降级策略

- Validator 超时未完成 → 数据打 `confidence=low` 写入，不阻塞主链路
- 某源完全熔断 → FreshnessGuard 标记该字段来源缺失，ConsensusRecord 降级为单源

---

## 十一、可观测性

### 11.1 全链路 Trace

每条数据从爬取到入库，全程挂 `trace_id = {mission_id}:{record_id}`：

```
trace_id: mission-001-abc123
  span: ScoutAgent.discover        (sources_found=12, duration=4.2s)
  span: StaticCrawler.fetch        (url, http_status, bytes)
  span: Preprocessor.parse         (fields=8, dedup_hit=false)
  span: SchemaMapper.map           (schema_version="generic-v1")
  span: ConsistencyChecker.check   (sources_compared=3, conflict=false)
  span: StoreAgent.write           (table="data_records", record_id)
```

工具：**OpenLLMetry** 零侵入 instrument → **Jaeger** trace 存储 → **Grafana** 可视化

### 11.2 关键监控指标

| 指标 | 含义 | 告警阈值 |
|------|------|---------|
| `queue_depth[stream]` | 各 Stream 积压深度 | > 10,000 条 |
| `crawler_error_rate[source]` | 每个数据源的失败率 | > 15% |
| `dedup_hit_rate` | 去重命中率 | 突增 > 80%（数据源可能停更） |
| `live_stream_lag_ms` | 实时流延迟 | > 5,000ms |
| `validator_low_confidence_rate` | 低置信率 | > 30% |
| `mission_completion_rate` | 任务按时完成率 | < 95% |
| `dead_letter_velocity` | 死信产生速率 | > 100/min |
| `tier0_llm_cost_usd` | Tier-0 LLM 费用 | > $0.5/mission |

---

## 十二、技术选型汇总

| 层 | 技术 | 理由 |
|----|------|------|
| Tier-0 LLM | **DeepSeek-v3 / Haiku**（廉价）+ **Sonnet**（验证层） | 异构混用降成本（X-MAS 策略） |
| Agent 框架 | **LangGraph**（调度骨架）+ **CrewAI**（角色定义） | 生产最广；图状态 + 角色驱动 |
| 爬取 — 隐藏 API | **httpx**（异步 HTTP） | 大量 SPA 站点有 JSON 接口，无需浏览器 |
| 爬取 — 轻度反爬 | **Scrapling Fetcher** | TLS 指纹伪造，比 requests 更难被识别 |
| 爬取 — Cloudflare 静态 | **DrissionPage** | 浏览器过 CF 拿 Cookie，切 HTTP 模式批量爬，10x 提速 |
| 爬取 — Cloudflare Turnstile | **Scrapling StealthySession** | `solve_cloudflare=True` 自动过挑战 |
| 爬取 — Akamai Bot Manager | **Camoufox**（C++ 级指纹）+ **Zendriver**（原生 CDP）| 浏览器底层伪造，JS 层检测不出 |
| 爬取 — DOM 频繁重构 | **Scrapling adaptive** | 元素特征入库，改版后自动重定位 |
| 爬取 — 快速上线 | **Crawl4AI** + `magic=True` | LLM 提取省写 selector，新源快速接入 |
| 爬取 — 大规模代理管理 | **Crawlee TieredProxy + SessionPool** | 指纹绑定 Session，代理按成本自动分层 |
| 实时流 | **websockets** + **Redis Streams** | WebSocket 长连，事件直写 Redis |
| 消息总线 | **Redis Streams** | 轻量持久，消费者组支持 k 级并发 |
| 存储 | **PostgreSQL**（结构化）+ **Redis Cache**（热数据）| Event Sourcing 原始数据不可变 |
| Trace | **OpenLLMetry** + **Jaeger** + **Grafana** | 零侵入，自托管友好 |
| 部署 | **Docker Compose 单文件** | 一条命令启动，`--scale` 控并发规模，不引入 K8s |

---

## 十三、部署方案（Docker Compose）

**目标：** `docker-compose up` 一条命令启动全部服务，`--scale` 参数控制 worker 数量。

```yaml
# docker-compose.yml（概念示意）
services:

  # 基础设施 —— Redis 是全系统单点，必须开持久化
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    ports: ["6379:6379"]
    volumes: ["redis_data:/data"]
    command: >
      redis-server
      --appendonly yes
      --appendfsync everysec
      --auto-aof-rewrite-percentage 100
      --auto-aof-rewrite-min-size 64mb
      --save 60 1
      --maxmemory 512mb
      --maxmemory-policy allkeys-lru
    # 重启后恢复说明：
    # - crawl_jobs Stream（含 PEL pending）完整恢复，XAUTOCLAIM 自动处理遗留 pending
    # - heartbeat key 写入时带 EX 60，重启后自动过期，无需清理
    # - circuit OPEN 状态带 EX 300，重启后自动过期
    # - scheduled_jobs Sorted Set 完整恢复，Coordinator 正常扫描即可

  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: swarm_data
    volumes: ["pgdata:/var/lib/postgresql/data"]

  # Tier-0（轻量，按需启动，平时 0 副本）
  planner:
    build: ./services/planner
    scale: 1
    env_file: .env

  # Tier-1
  coordinator:
    build: ./services/coordinator
    scale: 2
    depends_on: [redis, postgres]

  # Tier-2（scale 参数控制并发规模）
  static-crawler:
    build: ./services/crawler
    environment: { CRAWLER_TYPE: static }
    scale: 50          # docker-compose up --scale static-crawler=300

  browser-crawler:
    build: ./services/crawler
    environment: { CRAWLER_TYPE: browser }
    scale: 20          # 浏览器内存消耗大，单机建议 ≤ 100

  auth-crawler:
    build: ./services/crawler
    environment: { CRAWLER_TYPE: auth }
    scale: 10

  stream-crawler:
    build: ./services/crawler
    environment: { CRAWLER_TYPE: stream }
    scale: 10

  # Tier-3
  preprocessor:
    build: ./services/processor
    scale: 30

  # Tier-4
  validator:
    build: ./services/validator
    scale: 20

  # Tier-5
  store:
    build: ./services/store
    scale: 5

  api-gateway:
    build: ./services/api-gateway
    ports: ["8080:8080"]

  # 可观测性
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports: ["16686:16686"]   # Trace UI

  grafana:
    image: grafana/grafana:latest
    ports: ["3001:3000"]     # 指标面板

volumes:
  pgdata:
```

**启动命令：**
```bash
# 开发环境（小规模）
docker-compose up

# 生产任务（按需扩规模）
docker-compose up \
  --scale static-crawler=300 \
  --scale browser-crawler=100 \
  --scale preprocessor=100 \
  --scale validator=60
```

**单机硬件参考（满配 ~1000 workers）：**
- 静态 crawler × 300：CPU 密集，8 core 足够
- 浏览器 crawler × 100：每个 Chromium 实例 ~100MB，需要 16GB+ 内存
- 其余 worker：轻量，内存各 50~100MB
- **推荐最低配：** 16 core / 32GB RAM / 100GB SSD

---

## 十四、规模测算（动态组队示例）

以"多站点全量数据采集任务"为例，TeamAssembler 的典型输出：

| 角色 | 数量 | 估算 QPS/吞吐 | LLM 调用 |
|------|------|-------------|---------|
| Tier-0 规划 agents | 6 | — | ~8 次（Haiku，< $0.01）|
| StaticCrawler | 120 | ~1,200 req/s | 无 |
| BrowserCrawler | 80 | ~80 page/s | 无 |
| AuthCrawler | 40 | ~40 req/s | 无 |
| StreamCrawler | 30 | 持续连接 | 无 |
| Preprocessor + SchemaMapper + EntityResolver | 80 | — | 可选 LLM（Haiku）|
| Validator 系列 | 70 | — | 部分用 Sonnet |
| Store + Publisher | 30 | — | 无 |
| **合计** | **~456** | | **< $0.05/任务** |

> 可根据紧迫程度（deadline 远近）动态上调/下调规模，1000 agent 是系统上限，实际按需使用 300~600 更经济。

---

## 十五、与下游系统集成

**通用 REST API 接入方案：**

1. 下游数据消费系统在数据初始化阶段，将原有单点 API 调用替换为调用本工具的 APIGateway（`GET /api/v1/records?dataset=target&page=1`）
2. APIGateway 返回多源聚合的 consensus 数据 + confidence_score
3. 下游系统可直接消费标准化数据记录，可信度分数可作为数据质量权重使用

```
下游系统 init()
    │
    ▼  GET /api/v1/records?dataset=...
APIGateway (本工具)
    │  consensus record + confidence
    ▼
下游系统业务逻辑（无需改动内部处理流程）
```

---

## 十六、架构决策记录

以下为已确认的设计决策，不再作为开放问题。

---

### 决策 1：ScoutAgent 允许发现灰色数据源

**决定：** Scout 可以发现并收录无明确版权授权的数据源，无需白名单限制。

**约束：** 数据真实性是唯一硬性要求，Validator 层的 CredibilityScorer 负责评估来源可信度；下游消费方可根据 `confidence_score` 决定是否采用低可信来源的数据。

**不做：** 不设域名白名单，不对 Scout 的搜索范围人工干预。

---

### 决策 2：AuthCrawler 不持有账号，改为主动绕过登录

**决定：** 不注册账号、不维护账号池，AuthCrawler 的核心能力改为**无账号登录绕过**。

具体技术方案见第十七节（待 subagent 调研完成后补充）。

---

### 决策 3：Schema 版本控制采用 Event Sourcing

**决定：** 所有原始抓取内容（原始 HTML / JSON）必须以**不可变事件**形式持久化存储，Schema 映射在读取时按版本应用，而非写入时转换。

**实施方式：**
- `raw_events` 表：存储所有原始采集内容，字段为 `(event_id, source_id, url, raw_content, captured_at, schema_version)`，只追加、不修改
- SchemaMapper 做"投影"而非"转换"——原始数据不变，不同 schema 版本生成不同的物化视图
- 数据源改版时，只需新增 schema 版本映射，历史数据可用旧版本重新投影，不存在不可逆丢失

**好处：** 可以对任意历史时间点的数据重新执行处理逻辑，支持回溯验证。

---

### 决策 4：实时流数据优先于批量快照

**决定：** 当同一字段同时存在实时流数据和批量快照数据时，**以实时流为最终值**。

**合并规则：**
```
最终记录 = 批量快照（基础字段） MERGE 实时流（覆盖冲突字段）
conflict_log：记录每次覆盖（字段名、批量值、实时值、时间差）
```

**理由：** 高频波动字段（如价格、状态）在批量爬取窗口内可能发生变化，实时流的时间戳更新，数据更准确。

---

### 决策 5：初期部署用单文件 Docker Compose，不引入 K8s

**决定：** 整个系统用一个 `docker-compose.yml` 覆盖全部服务，单机一条命令启动。

**原则：**
- 不引入 Kubernetes、Helm、服务网格
- 不引入 Kafka（用 Redis Streams 替代）
- 不引入独立的 tracing 基础设施（Jaeger 作为 compose 中一个容器即可）
- 扩容用 `--scale` 参数，不用自动弹性伸缩

**升级路径：** 当单机成为瓶颈时（通常是 BrowserCrawler 内存耗尽），再考虑迁移到 Docker Swarm 或 K8s，架构本身不需要改动，只是换调度层。

---

## 十七、采集层设计原则补充

第五节已覆盖全部 Strategy 0～7 的具体实现。本节补充三个跨策略的通用原则，来自 last30days-skill（25.4k ⭐）的实战总结。

---

### 原则 1：实体预解析（Entity Pre-Resolution）

ScoutAgent 不直接把模糊采集目标交给 Crawler，而是先把它映射为具体的抓取目标：

```
目标 → 实体预解析 → 精准抓取目标

"采集某类目全量商品数据" →
  - 目标 API:    /api/items?category=electronics&page=1
  - 聚合站:      /catalog/category/electronics/list/
  - 官方站:      /products/search?q=electronics&sort=newest
  - 新闻/评论:   site:news.example.com + 关键词 "electronics 2026"
```

意义：Crawler 收到的是精准 URL 列表，不是模糊关键词，precision 大幅提升，避免爬到无关页面。

---

### 原则 2：TTL 缓存避免重复 API 调用

以 `{mission_id}:{source_id}:{url_hash}` 为 key，写入 Redis，TTL 按数据类型设置：

| 数据类型 | TTL | 理由 |
|---------|-----|------|
| 历史数据记录 | 7 天 | 不变数据，重复爬无意义 |
| 状态/详情字段 | 2 小时 | 当天可能发生变化 |
| 高频波动字段 | 15 分钟 | 采集窗口内频繁变动 |
| 实时推送数据 | 不缓存 | StreamCrawler 直推，无需缓存 |

---

### 原则 3：Crawlee 分层代理（TieredProxy）控成本

代理按成本分层，贵的只在失败时才用，不是每次请求都走住宅代理：

```typescript
// 自动分层：先走便宜的数据中心代理，失败了再升住宅代理
const proxyConfiguration = new ProxyConfiguration({
    tieredProxyUrls: [
        ["http://datacenter-1:8080", "http://datacenter-2:8080"],   // Tier 1，便宜
        ["http://residential-1:8080", "http://residential-2:8080"], // Tier 2，贵
    ],
});
// Crawlee 自动追踪每个域名的错误率，错误多了升层，稳定后降回
```

意义：高防护站走 Tier 2 住宅代理，轻防护站走 Tier 1 数据中心代理，代理成本降低 60%+。

---

---

## 十八、并发模型与实时采集

### 18.1 Push vs Pull 的边界

实时采集的第一个判断：这个数据源是**数据推过来**（Push）还是**我去轮询**（Pull）？

```
Push（数据源主动推）      Pull（我们主动轮询）
────────────────────      ─────────────────────
WebSocket 推送            HTTP 轮询（每 N 秒请求一次）
SSE（Server-Sent Events）  无 WebSocket 接口的"实时"页面
官方 API 的 webhook        需要定时刷新的数据页面

延迟：毫秒级               延迟：取决于轮询间隔（秒级）
适用：实时数据变动推送      适用：无 WS 接口但需要准实时
```

**判断规则（由 RealTimeController 负责）：**
- 数据源有 WebSocket/SSE → 直接订阅，不轮询
- 没有推送接口但需要 < 30s 延迟 → 高频轮询（每 10~15s 一次）
- 延迟容忍 > 5min → 进批量管道，不走实时路径

---

### 18.2 一个 StreamCrawler 能维持多少连接

**Python asyncio 模型**：单线程事件循环，I/O 等待时切换协程，一个进程可同时维持大量 WebSocket 连接（瓶颈是系统文件描述符和网络带宽，不是 CPU）。

```python
import asyncio, websockets, json
from redis.asyncio import Redis

class StreamCrawler:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def subscribe(self, ws_url: str, source_id: str):
        """单个 WebSocket 订阅协程"""
        async for ws in websockets.connect(ws_url, ping_interval=20, ping_timeout=10):
            try:
                async for raw in ws:
                    event = json.loads(raw)
                    await self.redis.xadd("live_events", {
                        "source": source_id,
                        "data": raw,
                        "ts": str(event.get("timestamp", ""))
                    }, maxlen=100_000)    # 防止 Stream 无限增长
            except websockets.ConnectionClosed:
                continue   # 自动重连：for 循环重新进入 connect()

    async def run(self, subscriptions: list[dict]):
        """并发维持 N 个 WebSocket 连接"""
        await asyncio.gather(*[
            self.subscribe(s["ws_url"], s["source_id"])
            for s in subscriptions
        ])
```

**实际容量估算：**

| 场景 | WebSocket 连接数 | 推荐 StreamCrawler 数量 |
|------|----------------|----------------------|
| 小规模采集（10 目标 × 3 源） | 30 | 1 |
| 中规模采集（50 目标 × 5 源）| 250 | 2~3 |
| 大规模采集（200 目标 × 5 源）| 1000 | 5~8 |

每个 StreamCrawler 进程轻松维持 200~500 并发连接（asyncio），内存消耗约 50~100MB/进程。

---

### 18.3 批量爬取的并发控制

批量 Crawler（Strategy 1~6）的并发不是越多越好，Crawlee 的 **AutoscaledPool** 根据系统负载动态决定并发数：

```typescript
import { PlaywrightCrawler, AutoscaledPool } from 'crawlee';

const crawler = new PlaywrightCrawler({
    // 并发控制：CPU/内存低时自动增加，高时自动减少
    minConcurrency: 5,
    maxConcurrency: 50,        // 单个 Crawler 实例最大并发
    maxRequestRetries: 3,
    requestHandlerTimeoutSecs: 30,

    // SessionPool：指纹绑定 Session，同一 Session 内请求指纹一致
    useSessionPool: true,
    persistCookiesPerSession: true,
    browserPoolOptions: { useFingerprints: true },

    async requestHandler({ request, page, session }) {
        const data = await page.$eval('.match-data', el => el.textContent);
        if (!data) {
            session.markBad();    // 触发 Session 轮换
            throw new Error('empty response, retry');
        }
        // 成功处理，写入 Redis
    }
});
```

**多进程水平扩展（Docker Compose scale）：**

```
docker-compose up --scale browser-crawler=20

→ 20 个 Crawler 进程，每个最大并发 50
→ 总并发上限：20 × 50 = 1000 并发请求
→ 所有进程共享同一个 Redis Streams 任务队列（Consumer Group 保证不重复）
```

---

### 18.4 背压：防止下游处理跟不上

实时事件涌入速度可能超过 Preprocessor 处理速度（尤其赛事密集时段）。Redis Streams 天然提供背压：

```
StreamCrawler 写入速度：1000 events/s
Preprocessor 处理速度：200 events/s
→ 积压 800 events/s → queue_depth 上升 → 触发 Preprocessor 自动扩容
```

**关键参数：**
- `XADD ... MAXLEN 100000`：Stream 上限 10 万条，超出自动丢弃最老的（防止内存爆炸）
- `queue_depth > 10000` → 告警 + 触发 Preprocessor 扩容（`docker-compose scale`）
- 实时管道（live_events）比批量管道优先级更高，消费者优先消费 live_events

---

### 18.5 实时+批量数据的合并时序

```
批量快照（T-2h 前采集）：field_a=2.10, field_b="status_A", field_c=3.20
实时数据流（触发更新）  ：field_a=1.85（数据字段发生变化）

合并规则（已在决策4确认）：实时流覆盖批量字段，保留 conflict_log

最终记录：field_a=1.85  ← 实时值
conflict_log: {field:"field_a", batch:2.10, stream:1.85, delta_min:15}
```

**StoreAgent 的合并逻辑**：按 `(item_id, field_name)` 做 UPSERT，`updated_at` 更新的记录覆盖旧值；conflict 写入独立审计表，不影响主数据。

---

## 十九、Agent 生命周期管理、健康监控与容错

### 19.1 每个 Agent 的状态机

```
     ┌──────────────────────────────────────────┐
     ▼                                          │
  STARTING                                      │
     │  注册到 Redis，写入初始心跳               │
     ▼                                          │
   IDLE ──────── 拉取 Job ──────► PROCESSING    │
     ▲                               │          │
     │         Job 完成，ACK          │ 超时/异常 │
     └───────────────────────────────┘          │
                                     │          │
                               FAILED           │
                                     │  重试 < 3次
                                     └──────────┘
                                     │  重试 >= 3次
                                     ▼
                               DEAD（写 dead_letters，进程退出）
```

**状态存储：**
```
Redis Hash: agent:{agent_id}
  status:     IDLE / PROCESSING / FAILED
  job_id:     当前处理的 job（PROCESSING 状态时）
  started_at: 进程启动时间
  heartbeat:  最后心跳时间戳（每 5s 更新一次）
  error_count: 累计错误次数
```

---

### 19.2 心跳机制（判断 Agent 是否存活）

每个 Agent 进程每 **5 秒**写一次心跳到 Redis，TTL 30 秒（心跳停止 30s 后 key 自动消失）：

```python
import asyncio, time
from redis.asyncio import Redis

class AgentHeartbeat:
    def __init__(self, redis: Redis, agent_id: str):
        self.redis = redis
        self.agent_id = agent_id

    async def start(self):
        while True:
            await self.redis.hset(f"agent:{self.agent_id}", mapping={
                "heartbeat": int(time.time()),
                "status": self.status
            })
            await self.redis.expire(f"agent:{self.agent_id}", 30)  # TTL 30s
            await asyncio.sleep(5)
```

**Coordinator 的存活检查（每 15s 扫一次）：**

```python
async def check_agents(redis: Redis):
    # 找所有注册的 agent
    agent_keys = await redis.keys("agent:*")
    for key in agent_keys:
        data = await redis.hgetall(key)
        last_beat = int(data.get("heartbeat", 0))
        if time.time() - last_beat > 30:
            # 心跳超时：agent 已死
            dead_agent_id = key.split(":")[1]
            await handle_dead_agent(redis, dead_agent_id, data)
```

---

### 19.3 核心容错机制：Redis Streams Consumer Groups + XAUTOCLAIM

**这是整个系统容错的地基。** Redis Streams 的消费者组有一个"Pending Entry List"（PEL）：消息被消费者读取后进入 pending 状态，**只有显式 ACK 之后才算完成**。如果 Agent 读取消息后崩溃，消息一直在 pending 里，不会丢失。

```python
from redis.asyncio import Redis
import time

PENDING_TIMEOUT_MS = 60_000  # 60 秒无 ACK 视为超时

async def process_jobs(redis: Redis, stream: str, group: str, agent_id: str):
    while True:
        # 1. 读取新消息（">" 表示只取未分配给任何消费者的消息）
        messages = await redis.xreadgroup(
            group, agent_id, {stream: ">"}, count=1, block=5000
        )

        if messages:
            _, entries = messages[0]
            msg_id, job = entries[0]
            try:
                await process(job)
                await redis.xack(stream, group, msg_id)  # 成功 → ACK
            except Exception as e:
                # 失败不 ACK → 消息留在 pending，等待 XAUTOCLAIM 重新分配
                await redis.hset(f"agent:{agent_id}", "status", "FAILED")
                raise

async def reclaim_stuck_jobs(redis: Redis, stream: str, group: str):
    """Coordinator 定期执行：把超时 pending 消息转给新 consumer"""
    while True:
        await asyncio.sleep(30)
        # XAUTOCLAIM：把 pending 超过 60s 的消息重新分配给 "requeue" consumer
        result = await redis.xautoclaim(
            stream, group, "requeue",
            min_idle_time=PENDING_TIMEOUT_MS,
            start_id="0-0", count=100
        )
        reclaimed = result[1]
        if reclaimed:
            # 重新放回队列供健康的 agent 处理
            for msg_id, job in reclaimed:
                await redis.xadd(stream, job)
                await redis.xack(stream, group, msg_id)
```

**效果：**
- Agent 崩溃 → 其 pending 消息 60s 后被 `XAUTOCLAIM` 自动摘走，交给其他健康 Agent
- 无需人工干预，无数据丢失
- 同一消息最多被处理 `max_retries` 次后写入 dead_letters

---

### 19.4 调度器：两类任务的触发方式

系统存在两种不同性质的任务，调度方式不同：

**类型 A：事件驱动（Reactive）**
上层下达目标 → GoalInterpreter → Coordinator 生成 Job → Crawler 消费

```
用户发起 "采集目标数据集" → Tier-0 规划 → 一次性 Job Batch → 执行完毕
```

**类型 B：定时轮询（Proactive）**
某些数据需要周期性刷新（高频字段每 15min、状态字段每 2h），用 Redis Sorted Set 实现轻量调度：

```python
import time, json
from redis.asyncio import Redis

# 注册定时任务（调度器写入）
async def schedule_job(redis: Redis, job: dict, run_at: float):
    await redis.zadd("scheduled_jobs", {json.dumps(job): run_at})

# 调度循环（Coordinator 每 10s 扫一次）
async def scheduler_loop(redis: Redis):
    while True:
        now = time.time()
        # 取出所有到期任务（score <= now）
        due_jobs = await redis.zrangebyscore("scheduled_jobs", 0, now, withscores=True)
        for job_json, score in due_jobs:
            job = json.loads(job_json)
            await redis.xadd("crawl_jobs", job)        # 放入执行队列
            await redis.zrem("scheduled_jobs", job_json)  # 从调度表移除
            # 如果是周期任务，重新注册下一次执行时间
            if job.get("interval_s"):
                await schedule_job(redis, job, now + job["interval_s"])
        await asyncio.sleep(10)
```

**典型调度配置：**

| 数据类型 | 来源 | 轮询间隔 | 触发时机 |
|---------|------|---------|---------|
| 实时推送数据 | 支持 WS 的目标站 | Push（不轮询）| StreamCrawler 常驻订阅 |
| 高频波动字段 | 目标聚合站 | 15 分钟 | 任务开始 T-6h 启动 |
| 状态/详情字段 | 官方数据站 | 2 小时 | 任务开始 T-12h 启动 |
| 历史数据记录 | 数据归档站 | 1 次/天 | 每日 03:00 UTC |
| 周期性报告 | 内容聚合站 | 6 小时 | 常驻 |

---

### 19.5 熔断器实现（每数据源独立）

```python
import time
from redis.asyncio import Redis
from enum import Enum

class CircuitState(str, Enum):
    CLOSED = "closed"        # 正常
    OPEN = "open"            # 熔断，拒绝请求
    HALF_OPEN = "half_open"  # 探测中

FAILURE_THRESHOLD = 5     # 连续失败 5 次触发熔断
RECOVERY_TIMEOUT  = 300   # 熔断后 300s 进入半开

async def check_circuit(redis: Redis, source_id: str) -> bool:
    """返回 True 表示允许请求，False 表示熔断拒绝"""
    key = f"circuit:{source_id}"
    data = await redis.hgetall(key)
    state = data.get("state", CircuitState.CLOSED)

    if state == CircuitState.CLOSED:
        return True

    if state == CircuitState.OPEN:
        last_failure = float(data.get("last_failure", 0))
        if time.time() - last_failure > RECOVERY_TIMEOUT:
            await redis.hset(key, "state", CircuitState.HALF_OPEN)
            return True   # 半开：放行一个探测请求
        return False      # 仍在冷却期，拒绝

    return True           # HALF_OPEN 状态放行

async def record_failure(redis: Redis, source_id: str):
    key = f"circuit:{source_id}"
    failures = await redis.hincrby(key, "failures", 1)
    await redis.hset(key, "last_failure", time.time())
    if failures >= FAILURE_THRESHOLD:
        await redis.hset(key, "state", CircuitState.OPEN)

async def record_success(redis: Redis, source_id: str):
    await redis.hset(f"circuit:{source_id}", mapping={
        "state": CircuitState.CLOSED, "failures": 0
    })
```

---

### 19.6 监控指标与告警规则

所有 Agent 通过 OpenLLMetry 自动导出 OTel 指标，额外补充以下业务指标写入 Prometheus：

```python
from prometheus_client import Gauge, Counter, Histogram

# Agent 存活数
agents_alive = Gauge("swarm_agents_alive", "存活 agent 数量", ["tier", "type"])
# 队列积压
queue_depth  = Gauge("swarm_queue_depth",  "Stream 积压消息数", ["stream"])
# 任务处理延迟
job_duration = Histogram("swarm_job_duration_seconds", "任务处理耗时", ["agent_type"])
# 错误率
job_errors   = Counter("swarm_job_errors_total", "任务失败次数", ["source_id", "error_type"])
# 熔断状态
circuit_open = Gauge("swarm_circuit_open", "熔断数据源数量")
```

**Grafana 告警规则：**

| 告警名 | 触发条件 | 严重度 | 处理建议 |
|-------|---------|-------|---------|
| AgentHeartbeatMissing | `heartbeat_age > 60s` | Critical | Coordinator 自动重启（或人工干预）|
| QueueDepthHigh | `queue_depth > 10000` 持续 2min | Warning | 扩容对应 tier 的 worker |
| CircuitBreakerOpen | `circuit_open > 3`（多数据源同时熔断）| Critical | 检查网络/IP 是否被封 |
| DeadLetterBurst | `dead_letter_velocity > 100/min` | Warning | 查 dead_letters，识别系统性失败原因 |
| LiveStreamLag | `live_stream_lag_ms > 5000` | Critical | StreamCrawler 可能断连，检查 WebSocket |
| MissionTimeout | 任务超过预计时长 150% | Warning | 检查瓶颈 tier，可能需要临时扩容 |

---

### 19.7 自动扩缩容决策逻辑

Coordinator 内置简单的扩缩容决策，**不依赖 K8s HPA**，直接用 Docker Compose API 调整 replica 数：

```python
import subprocess

SCALE_RULES = [
    # (stream, agent_type, scale_up_threshold, scale_down_threshold, max, min)
    ("crawl_jobs",     "static-crawler",   5000,  500,  300, 10),
    ("raw_data",       "preprocessor",    10000, 1000,  100,  5),
    ("clean_data",     "validator",        5000,  500,   60,  5),
    ("live_events",    "stream-crawler",      0,    0,   30,  3),  # 不扩缩，常驻
]

async def auto_scale(redis: Redis):
    while True:
        for stream, service, up_thresh, down_thresh, max_r, min_r in SCALE_RULES:
            depth = await get_queue_depth(redis, stream)
            current = get_current_replicas(service)

            if depth > up_thresh and current < max_r:
                new_count = min(current + max(1, current // 2), max_r)
                subprocess.run(["docker", "compose", "scale", f"{service}={new_count}"])

            elif depth < down_thresh and current > min_r:
                new_count = max(current - 1, min_r)
                subprocess.run(["docker", "compose", "scale", f"{service}={new_count}"])

        await asyncio.sleep(60)   # 每分钟评估一次
```

**扩缩容节奏设计：** 扩容激进（快速响应负载），缩容保守（每次只减 1 个，避免震荡）。

---

### 19.8 容错全景图

```
Job 进入 crawl_jobs Stream
         │
         ▼
Crawler 读取（进入 Pending）
         │
    ┌────┴────┐
  成功       失败/崩溃
    │           │
   ACK      消息留在 Pending
    │           │
  完成       60s 后 XAUTOCLAIM
              │
         重新入队（最多 3 次）
              │
         第 4 次失败 → dead_letters
                         │
                    Coordinator 分析
                    ┌────┴────┐
                 系统性        偶发性
                 失败          失败
                  │             │
              触发熔断        跳过记录
              通知告警        日志保留
```

**关键保证：**
- 消息不丢失：依赖 Redis Streams PEL + XAUTOCLAIM
- 不重复处理：依赖 job_id 幂等性检查（Redis SET 去重）
- 数据源故障不蔓延：熔断器隔离单源故障
- Agent 崩溃自动恢复：心跳检测 + 容器重启策略（`restart: unless-stopped`）

---

---

## 二十、Coordinator 高可用与 Redis 持久化

### 20.1 Coordinator 分布式锁（解决双副本竞争）

两个 Coordinator 副本用 Redis `SET NX + EXPIRE` 抢锁，同一时刻只有一个副本执行调度操作，另一个空转等待接管。

```python
import time, redis

LOCK_KEY = "coordinator:leader"
LOCK_TTL = 30   # 必须 > 一次调度循环最长执行时间

def try_acquire_lock(r: redis.Redis, instance_id: str) -> bool:
    return r.set(LOCK_KEY, instance_id, nx=True, ex=LOCK_TTL) is not None

def release_lock(r: redis.Redis, instance_id: str):
    # Lua 脚本保证"只删自己的锁"的原子性，防止误删其他实例的锁
    lua = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        return redis.call("DEL", KEYS[1])
    end
    return 0
    """
    r.eval(lua, 1, LOCK_KEY, instance_id)

def coordinator_loop(r: redis.Redis, instance_id: str):
    while True:
        if try_acquire_lock(r, instance_id):
            try:
                dispatch_scheduled_jobs(r)   # 扫 scheduled_jobs → crawl_jobs
                reclaim_pending_messages(r)  # XAUTOCLAIM 处理超时 pending
                autoscale_workers(r)         # docker compose scale 决策
            finally:
                release_lock(r, instance_id)
        # 抢锁失败则跳过本轮，10s 后再试
        time.sleep(10)
```

**局限性：** 持锁方崩溃时，锁等 TTL（最长 30s）到期后备用 Coordinator 才能接管——这是刻意接受的 30s 调度空窗，对数据采集场景可接受，不需要引入 Redlock 多节点方案。

---

### 20.2 Redis 持久化（已合并进 Section 13 Docker Compose）

**重启后各类数据的恢复行为：**

| 数据类型 | 恢复状态 | 处理方式 |
|---------|---------|---------|
| `crawl_jobs` Stream（含 PEL） | 完整恢复 | `XAUTOCLAIM` 自动处理遗留 pending，无需额外操作 |
| `scheduled_jobs` Sorted Set | 完整恢复 | Coordinator 重启后正常扫描，过期任务立即补发 |
| `circuit:{source}` 熔断状态 | 恢复，但可能停在 OPEN | **写入时加 `EX 300`**，Redis 重启后自动过期，无需应用层清理 |
| `agent:{id}` 心跳 | 恢复，但时间戳是旧的 | **写入时加 `EX 60`**，重启后自动过期，Coordinator 无需扫描清理 |
| `coordinator:leader` 锁 | 恢复旧值，但 TTL 保证 30s 内自动释放 | 无需处理 |

**核心设计原则：给所有"状态性"key 加 TTL，Redis 重启自愈，应用层零额外处理。**

---

## 二十一、补充 Agent 角色

以下四个角色填补前述架构审查发现的缺口，已在 Section 三 架构图中体现。

---

### 21.1 EntityRegistrar（新增，填补实体字典维护缺口）

**职责：** 初始化并持续维护实体字典（采集目标/类目/数据集标识的所有别名 → 规范 ID 映射）。EntityResolver 负责查询，EntityRegistrar 负责维护。

**触发机制：**
- **启动时一次性：** 从目标站点开放 API 或配置文件全量拉取采集目标列表，写入 `entity_aliases` 表
- **周期性（每周一次）：** 增量同步，检测新增实体、下线实体、改名
- **事件驱动：** EntityResolver 遇到未知别名时，发 `unknown_entity` 事件 → EntityRegistrar 模糊匹配并写回（置信度低时发告警等待人工确认）

**接口：** 输入：目标站开放 API / 本地配置 + `unknown_entity` 事件；输出：`entity_aliases` DB 表 + `entity_updated` 事件（通知 EntityResolver 热刷新内存缓存）

**不做：** 实时路径上的别名解析（由 EntityResolver 做）

---

### 21.2 SchemaWatcher（新增，填补 Schema 漂移检测缺口）

**职责：** 对比 SchemaDesigner 定义的"期望 schema"与"实际采集数据样本"，发现字段缺失、类型变更、新增未知字段。不做数据内容质量判断。

**触发机制：**
- **周期性（每小时）：** 对每个活跃数据源抽取最近 20 条记录，执行 schema diff
- **事件驱动：** Preprocessor 解析错误率突增时（> 20%），立即触发一次全源检测

**漂移响应分级：**
```
轻微漂移（新增非必填字段）  → 记录日志 + 通知 SchemaDesigner
严重漂移（必填字段缺失）    → 发 schema_drift_critical 事件
                              → RealTimeController 暂停该数据源写入
                              → 发告警等待人工介入
```

**归属：** 运行在 Tier-4 验证层（已在架构图中标注）

---

### 21.3 FastValidator（新增，填补实时管道验证缺口）

**职责：** 在 StreamCrawler 写入 `live_events` 后、EventPublisher 消费前做毫秒级拦截。只做结构合法性检查，不做跨源语义验证。

**检查规则（纯内存，启动时加载）：**
- 必填字段存在性（`item_id`、`timestamp`、`event_type`）
- 基础类型匹配（timestamp 为 ISO8601、数值字段为 int/float、文本字段为 string）
- 值域范围（按 SchemaSpec 中定义的各字段合法区间校验）

**延迟目标：** < 5ms（零 DB 查询，规则纯内存执行）

**通过 → 转发 EventPublisher；拒绝 → 写 dead_letters + 发 `validation_failed` 告警**

---

### 21.4 RetentionAgent（新增，填补数据保留策略缺口）

**职责：** 定期清理过期历史数据，防止磁盘无限增长。

**数据保留策略：**

| 数据类型 | 保留周期 | 分区粒度 | 清理方式 |
|---------|---------|---------|---------|
| `raw_events`（原始采集）| 7 天 | 按天 | DROP 旧分区（无 WAL 膨胀）|
| `processed_events`（处理后）| 90 天 | 按月 | DROP 旧分区 |
| `aggregated_stats`（聚合）| 永久 | — | 不清理 |
| `dead_letter_queue` | 30 天 | 按周 | DROP 旧分区 |

**技术方案：** PostgreSQL 原生分区表 + `pg_partman` 自动创建/删除分区。DROP 分区比 DELETE 快 100x 且不产生表膨胀。

**触发机制：** 每日 03:00 UTC 执行 `partman.run_maintenance()`，由 RetentionAgent 内嵌定时器触发，非关键路径，不影响数据流。

**归属：** 运行在 Tier-5 存储层（已在架构图中标注）

---

### 21.5 MissionTracker（TeamAssembler 子模块，填补 Mission 完成检测缺口）

**机制：** DB 表 `mission_jobs(mission_id, job_id, status, completed_at)` + 原子计数。

**完成判定（三种状态）：**

| 判定 | 条件 | 操作 |
|------|------|------|
| **完全完成** | `COUNT(status='done') = total_jobs` | TeamAssembler 触发缩容，释放全部 Crawler |
| **部分完成** | 核心 Job 全完成，附属 Job 失败率 < 20% | 标记 `PARTIAL_SUCCESS`，缩容 + 保留 1 个 RetryAgent |
| **超时熔断** | Mission 级 deadline 到期 | 强制标记 `TIMEOUT`，记录未完成列表，触发缩容 + 告警 |

**计数原子性：** StoreAgent 写入成功后发 `job_completed` 事件 → MissionTracker 监听，通过 DB 事务 + `SELECT FOR UPDATE` 原子递增，避免并发计数错误。

---

## 二十二、前端控制台设计

### 22.1 整体布局

单页应用，左右分栏。左侧固定 340px 为 Mission 控制区，右侧 flex 弹性区为 Agent 实时监控。

```
┌────────────────────────────────────────────────────────────────────────────┐
│  DataSpider 通用采集控制台              [系统状态: RUNNING ●]  Agents: 28    │
├───────────────────┬────────────────────────────────────────────────────────┤
│  MISSION CONTROL  │  AGENT MONITOR                                         │
│  (340px)          │                                                        │
│                   │  [ 📋 分层列表 ✓ ]  [ 🗺 拓扑图 ]       筛选  搜索    │
│  ┌─────────────┐  │  ┌──────────────────────────────────────────────────┐ │
│  │ 输入框      │  │  │  Tier-0 规划层  6/6 IDLE              ▸ 折叠    │ │
│  │ + 快捷按钮  │  │  │  Tier-1 协调层  2/2 PROCESSING        ▸ 展开   │ │
│  │ [启动]      │  │  │  Tier-2 采集层  16 PROC / 2 FAILED    ▸ 展开   │ │
│  └─────────────┘  │  │  [card] [card] [card] [card] ...                 │ │
│                   │  │  Tier-3/4 处理·验证层  全绿           ▸ 折叠    │ │
│  ┌─────────────┐  │  │  Tier-5 存储·交付层    全绿           ▸ 折叠    │ │
│  │ 启动进度    │  │  └──────────────────────────────────────────────────┘ │
│  │ 阶段进度条  │  │                                                        │
│  │ + agent列表 │  │  ┌──────────────────────────────────────────────────┐ │
│  └─────────────┘  │  │  队列深度    tier1→2: ████░ 847   ⚠             │ │
│                   │  │              tier2→3: ██░░░ 234                  │ │
│  ┌─────────────┐  │  │  熔断器: [siteB ⚡OPEN] [siteC ✓]               │ │
│  │ 历史任务    │  │  └──────────────────────────────────────────────────┘ │
│  └─────────────┘  │                                                        │
└───────────────────┴────────────────────────────────────────────────────────┘
```

---

### 22.2 Mission 触发界面

```
┌──────────────────────────────────────────┐
│  NEW MISSION                             │
│  ┌──────────────────────────────────┐   │
│  │                                  │   │
│  │  采集目标站点全量商品数据         │   │
│  │                        [Ctrl+↵]  │   │
│  └──────────────────────────────────┘   │
│  预设: [全量采集] [增量更新] [自定义▾]   │
│  [▶ 启动 Mission]                        │
└──────────────────────────────────────────┘
```

提交后进度区展开，分三阶段顺序呈现：

```
MISSION #M-0042  [PLANNING...]

阶段 1/3：Tier-0 规划
████████████░░░░░░  60%
● GoalInterpreter   ✓ 解析: 目标数据集，采集目标已确认
● ScoutAgent        ✓ 发现: 7个数据源
● SchemaDesigner    ⟳ 设计 schema 中...
● RealTimeController ○ 等待中
● TeamAssembler     ○ 等待中

阶段 2/3：TeamAssembler
○ 待启动

阶段 3/3：执行
○ 待启动
```

TeamAssembler 完成后，各 Tier 数量从 0 开始动画计数递增：

```
已组建团队：
  Tier-1  协调者    × 2
  Tier-2  采集      × 18  ←新增
  Tier-3  处理      × 4
  Tier-4  验证      × 2
  Tier-5  存储/交付 × 2
  合计：28 个 Agent
数据源：[目标站点 A] [目标站点 B] [目标 API C] [聚合站 D +3]
```

---

### 22.3 Agent 监控面板：分层卡片列表（主）+ 迷你拓扑 SVG（辅）

**选择分层卡片列表的理由：**
- Agent 数量动态增减时，卡片列表追加行，视觉稳定；D3 拓扑图节点增删需重新布局，闪烁严重
- 单 Agent 详情直接显示在卡片上，无需 hover；数量 > 30 时仍可读
- 拓扑图缺失的数据流方向感，用右上角静态迷你 SVG 补偿（5 层节点 + 带宽色标注，不动态）

**Agent 卡片信息规范（Tier-2 采集层最完整，其他层简化）：**

```
┌─────────────────────────────────┐
│ crawl-siteA-007         ⟳ PROC  │  ← ID + 状态
│ 数据源: example.com             │
│ 当前 Job: dataset_page_03_fetch │
│ 进度: ███████░░░  72%           │
│ 耗时: 01:24  速率: 3.2 req/s    │
│ 心跳: 2s 前  失败: 0次          │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ crawl-siteB-003          ✗ FAIL │  ← FAILED 状态
│ ⚡ 熔断器: OPEN (自动跳过)       │
│ 原因: 429 Too Many Requests     │
│ 失败 3:12 前  恢复 4:48 后      │
└─────────────────────────────────┘
```

状态图标：IDLE `●`灰 / PROCESSING `⟳`蓝旋转 / FAILED `✗`红 / DEAD `☠`深灰

---

### 22.4 WebSocket 实时数据推送

**端点：** `ws://localhost:8080/ws/console`（FastAPI WebSocket）

连接建立后，服务端立即推送一次全量快照（`type: snapshot`），之后全部增量推送。

**消息格式：**

```json
// 1. 全量快照（连接时一次性）
{ "type": "snapshot", "ts": 1746700800000,
  "data": { "agents": [...], "streams": [...], "circuits": [...] } }

// 2. Agent 状态变更（事件驱动，去抖 200ms）
{ "type": "agent_update", "ts": 1746700800123,
  "data": {
    "agent_id": "crawl-fbref-007", "tier": 2, "status": "PROCESSING",
    "source_name": "siteA", "current_job_id": "dataset_page_03_fetch",
    "job_progress": 72, "elapsed_sec": 84, "request_rate": 3.2,
    "last_heartbeat_ts": 1746700798000, "error_count": 0
  }}

// 3. 队列深度批量（每秒一次）
{ "type": "stream_update", "ts": 1746700800000,
  "data": { "streams": [
    { "name": "tier1_to_tier2", "depth": 847, "capacity": 1000 },
    { "name": "tier2_to_tier3", "depth": 234, "capacity": 1000 }
  ]}}

// 4. 熔断器状态变更（事件驱动）
{ "type": "circuit_update", "ts": 1746700800000,
  "data": { "source_name": "siteB", "state": "OPEN",
            "retry_after_sec": 288, "last_error": "429 Too Many Requests" }}

// 5. Mission 生命周期事件
{ "type": "mission_event", "ts": 1746700800000,
  "data": { "mission_id": "M-0042", "event": "team_assembled",
            "team_snapshot": { "tier2": 18, "total": 28 } }}
```

**客户端 → 服务端控制指令：**
```json
{ "cmd": "restart_agent", "payload": { "agent_id": "crawl-siteA-007" } }
{ "cmd": "pause_mission",  "payload": { "mission_id": "M-0042" } }
```

---

### 22.5 技术栈

| 层 | 选择 | 理由 |
|----|------|------|
| 框架 | **React 18** | `startTransition` 把低优先级图表更新降级，Agent 卡片状态更新不卡顿 |
| 状态管理 | **Zustand** | WS 消息直接 `set` 更新 store slice，无样板代码；`subscribe` 模式天然适配消息流 |
| 样式 | **Tailwind CSS** | 暗色主题 + 状态色一行搞定，无 CSS 文件维护负担 |
| 图表 | **Recharts**（队列折线）+ 手写 SVG（拓扑示意）| 拓扑只有 5 层节点且静态，手写 SVG < 50 行，无需引入 D3/ECharts |
| WebSocket | **自定义 `useWebSocket` hook** | 内置重连、消息去抖、快照合并逻辑，场景简单不需要 SockJS fallback |
| 构建 | **Vite** | 启动快；`vite build` 产物直接由 FastAPI `StaticFiles` 托管，不需要独立 nginx |

### 22.6 实现优先级

| Phase | 内容 | 产出 |
|-------|------|------|
| Phase 1 | WS 连接 + AgentCard 列表 + 队列深度条 | 能看到 agent 状态 |
| Phase 2 | Mission 输入 + 进度展示 + 熔断器显示 | 能触发和跟踪任务 |
| Phase 3 | 拓扑 SVG + 历史任务 + 控制指令（重启 agent）| 完整控制台 |

---

*v1.0（通用版）— 基于 CrewAI、LangGraph、Crawlee、Camoufox、Zendriver、Scrapling、DrissionPage、Crawl4AI、MacNet、Project Sid、OpenLLMetry 等项目的研究整理*
