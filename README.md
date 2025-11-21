# 🦈 Wall Street AI Risk Monitor (Enterprise Ver.)
# 华尔街风控情报系统 - 企业专业版

> A real-time financial risk dashboard powered by DeepSeek AI, integrating market metrics, sentiment analysis, and multi-user management.
> 基于 DeepSeek 大模型构建的实时金融风控仪表盘，集成了核心资产监控、舆情情感分析与企业级权限管理系统。

## 🌟 Core Features / 核心功能

### 1. 🧠 AI-Powered Intelligence (AI 智能研报)
- **DeepSeek V3 Integration**: Automates the reading of Goldman Sachs, Morgan Stanley, and other top-tier research/news.
- **Historical Comparison**: The AI remembers previous analyses and highlights **changes in viewpoint** (Viewpoint Shift).
- **Persistence**: Analysis history is saved to disk/cloud, ensuring no data loss upon refresh.
- **DeepSeek V3 驱动**: 自动阅读高盛、大摩等顶级投行研报与新闻。
- **历史观点对比**: AI 拥有记忆，能对比上一次分析，自动识别市场情绪变化。
- **数据持久化**: 研报记录永久保存，刷新页面不丢失，支持团队历史回溯。

### 2. 📊 Real-Time Market Metrics (实时核心指标)
- **Multi-Asset Tracking**: SPY (S&P 500), QQQ (Nasdaq), IEF (Treasury), VIX (Volatility).
- **Technical Signals**: Auto-calculated **RSI** with overbought/oversold alerts.
- **Fear & Greed Index**: Real-time visualization of CNN's Fear & Greed Index (with anti-blocking mechanism).
- **多资产监控**: 覆盖标普500、纳指、美债、恐慌指数。
- **技术信号**: 自动计算 RSI，实时提示超买/超卖风险。
- **情绪仪表盘**: 实时抓取 CNN 恐慌贪婪指数（含防屏蔽与 RSI 替补机制）。

### 3. 📰 Smart News Feed (智能舆情流)
- **Sentiment Tagging**: 5-level color-coded sentiment analysis (Extreme Bullish to Extreme Bearish).
- **Time-Sorted**: Aggregated news feeds sorted by real-time timestamps.
- **5级情绪染色**: 基于 NLP 对新闻标题进行 5 级红绿灯打分。
- **时间流排序**: 聚合多源新闻，按最新发布时间倒序排列。

### 4. 🔒 Enterprise Security (企业级安全)
- **Authentication**: Username/Password login system.
- **Audit Logs**: Admin can monitor user activity and AI usage logs.
- **Cloud Config**: Credentials managed securely via Streamlit Secrets.
- **身份验证**: 完整的账号密码登录系统。
- **审计日志**: 管理员可监控用户活跃度与 API 调用情况。
- **云端配置**: 密钥与用户名单通过云端安全管理。

---

## 🛠️ Tech Stack / 技术栈
- **Frontend**: Streamlit
- **AI Engine**: OpenAI SDK (Compatible with DeepSeek API)
- **Data**: yfinance, feedparser, CNN (Reverse Engineered)
- **Visualization**: Plotly, Altair
- **NLP**: TextBlob

---

## 🚀 Quick Start / 如何运行

1. **Clone the repo**:
   ```bash
   git clone [https://github.com/YOUR_USERNAME/wallstreet-monitor.git](https://github.com/YOUR_USERNAME/wallstreet-monitor.git)
