import streamlit as st
import yfinance as yf
import pandas as pd
import feedparser
from openai import OpenAI
from textblob import TextBlob  # 恢复情绪分析库
import datetime

# --- 1. 页面基础配置 ---
st.set_page_config(page_title="DeepSeek 智能风控仪表盘", layout="wide", page_icon="🦈")

# --- 2. 侧边栏：设置与工具 ---
st.sidebar.title("⚙️ 设置")
st.sidebar.info("ℹ️ 云端优化模式：已启用 SPY/QQQ/IEF 数据源。")

# API 设置
api_key = st.sidebar.text_input("DeepSeek API Key", type="password", placeholder="sk-...")
MODEL_NAME = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"

# 实用工具箱
st.sidebar.markdown("---")
st.sidebar.subheader("📅 交易员工具箱")
st.sidebar.markdown("[🇺🇸 本周财经日历 (Investing)](https://cn.investing.com/economic-calendar/)")
st.sidebar.markdown("[😱 恐慌贪婪指数 (CNN)](https://edition.cnn.com/markets/fear-and-greed)")
st.sidebar.caption("点击上方链接查看非农、CPI等关键发布时间")

# --- 3. 核心逻辑函数 ---

def calculate_rsi(data, window=14):
    try:
        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    except:
        return pd.Series([50]*len(data))

# 🆕 新增：5级情绪分析函数
def analyze_sentiment_tag(text):
    analysis = TextBlob(text)
    score = analysis.sentiment.polarity # -1 到 1
    
    # 5级划分逻辑
    if score > 0.3:
        return "🟢 极度乐观", "green", score
    elif 0.1 < score <= 0.3:
        return "🥬 偏多", "green", score
    elif -0.1 <= score <= 0.1:
        return "⚪ 中性", "gray", score
    elif -0.3 <= score < -0.1:
        return "🟠 偏空", "orange", score
    else:
        return "🔴 极度悲观", "red", score

@st.cache_data(ttl=300)
def get_market_data():
    # 新增 QQQ (纳斯达克100 ETF)
    tickers = yf.Tickers("SPY QQQ IEF VIXY") 
    hist = tickers.history(period="3mo")
    return hist

# --- 4. 主界面 ---
st.title("🦈 华尔街风向标 (Pro Ver.)")
st.caption(f"最后更新: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 情绪引擎: TextBlob + DeepSeek")

try:
    market_data = get_market_data()
    
    def safe_metric(ticker_symbol):
        try:
            s = market_data['Close'][ticker_symbol].dropna()
            if len(s) < 2: return 0, 0
            val = s.iloc[-1]
            chg = val - s.iloc[-2]
            return val, chg
        except: return 0, 0

    # 获取数据
    spy_val, spy_chg = safe_metric("SPY")
    qqq_val, qqq_chg = safe_metric("QQQ") # 新增
    ief_val, ief_chg = safe_metric("IEF")
    vix_val, vix_chg = safe_metric("VIXY")
    
    # 计算 RSI (使用 SPY)
    try:
        spy_data = market_data.xs('SPY', level=1, axis=1) if isinstance(market_data.columns, pd.MultiIndex) else market_data
        rsi_val = calculate_rsi(spy_data).iloc[-1]
        rsi_prev = calculate_rsi(spy_data).iloc[-2]
        rsi_delta = rsi_val - rsi_prev
    except:
        rsi_val, rsi_delta = 50.0, 0.0

    # --- 模块 A: 仪表盘 ---
    st.subheader("1. 全球核心资产监控")
    c1, c2, c3, c4, c5 = st.columns(5) # 改为5列

    c1.metric("📈 标普500 (SPY)", f"${spy_val:.1f}", f"{spy_chg:.2f}")
    c2.metric("💻 纳指科技 (QQQ)", f"${qqq_val:.1f}", f"{qqq_chg:.2f}", help="高盛重点关注的科技成长股风向")
    c3.metric("📉 恐慌 (VIXY)", f"${vix_val:.2f}", f"{vix_chg:.2f}", delta_color="inverse")
    c4.metric("⚖️ 国债价格 (IEF)", f"${ief_val:.2f}", f"{ief_chg:.2f}", delta_color="normal", help="红跌=利率涨=坏事")
    
    # RSI 逻辑
    rsi_state = "中性"
    if rsi_val > 70: rsi_state = "🔴 严重超买"
    elif rsi_val < 30: rsi_state = "🟢 严重超卖"
    
    c5.metric("🐂 RSI 指标", f"{rsi_val:.1f}", f"{rsi_delta:.1f}", delta_color="off")
    if rsi_val > 70: c5.error("高风险")
    elif rsi_val < 30: c5.success("反弹机会")

    st.markdown("---")
    
    # --- 模块 B: 趋势图 ---
    st.subheader("2. 趋势透视")
    t1, t2, t3 = st.tabs(["S&P 500 & Nasdaq", "恐慌趋势", "利率压力"])
    
    with t1:
        # 比较 SPY 和 QQQ
        chart_data = pd.DataFrame({
            'SPY (标普)': market_data['Close']['SPY'],
            'QQQ (纳指)': market_data['Close']['QQQ']
        })
        st.line_chart(chart_data)
    with t2:
        st.area_chart(market_data['Close']['VIXY'], color="#FF4B4B")
    with t3:
        st.line_chart(market_data['Close']['IEF'], color="#FFAA00")

except Exception as e:
    st.error(f"数据加载中，请稍候... {e}")

# --- 模块 C: 智能化情报分析 ---
st.markdown("---")
st.subheader("3. 华尔街情报台 (Sentiment Analysis)")

rss_feeds = {
    "Goldman Sachs": "https://news.google.com/rss/search?q=Goldman+Sachs+outlook+when:7d&hl=en-US&gl=US&ceid=US:en",
    "Morgan Stanley": "https://news.google.com/rss/search?q=Morgan+Stanley+market+outlook+when:7d&hl=en-US&gl=US&ceid=US:en",
    "Market Risk": "https://news.google.com/rss/search?q=stock+market+crash+warning+when:3d&hl=en-US&gl=US&ceid=US:en"
}

col_ui_1, col_ui_2 = st.columns([1, 1.5])

# 左侧：AI 深度总结
with col_ui_1:
    st.markdown("#### 🤖 DeepSeek 首席策略师")
    if st.button("⚡ 开始深度研报分析", type="primary"):
        if not api_key:
            st.warning("请先在侧边栏输入 API Key")
        else:
            with st.spinner("正在阅读所有新闻并交叉比对..."):
                raw_text = ""
                for src, url in rss_feeds.items():
                    try:
                        f = feedparser.parse(url)
                        for e in f.entries[:3]: raw_text += f"- {e.title}\n"
                    except: pass
                
                try:
                    client = OpenAI(api_key=api_key, base_url=BASE_URL)
                    # 更高级的 Prompt
                    prompt = f"""
                    作为对冲基金风控官，请分析以下新闻：
                    {raw_text}
                    
                    请用中文输出简报（使用Markdown格式）：
                    1. **🚨 风险评级**：(0-10分，10分最高)
                    2. **🐂 多空博弈**：高盛 vs 大摩，谁在唱多谁在唱空？
                    3. **📉 关键预警**：如果是负面新闻，具体是在担心什么（AI泡沫？通胀反弹？）
                    4. **💡 操作建议**：针对SPY和QQQ的建议。
                    """
                    resp = client.chat.completions.create(
                        model=MODEL_NAME,
                        messages=[{"role":"user", "content":prompt}]
                    )
                    st.session_state['ai_report'] = resp.choices[0].message.content
                except Exception as e: st.error(str(e))
    
    if 'ai_report' in st.session_state:
        st.success("✅ 分析报告已生成")
        st.markdown(st.session_state['ai_report'])

# 右侧：新闻流 + 5级颜色标签
with col_ui_2:
    st.markdown("#### 📰 实时新闻情绪流 (5级分层)")
    st.caption("基于 NLP 算法对标题进行实时打分")
    
    news_container = st.container(height=500) # 固定高度，可滚动
    with news_container:
        for src, url in rss_feeds.items():
            try:
                f = feedparser.parse(url)
                if len(f.entries) > 0:
                    st.markdown(f"**{src}**")
                    for e in f.entries[:4]:
                        # 调用情绪分析
                        label, color, score = analyze_sentiment_tag(e.title)
                        
                        # 渲染彩色标签
                        # Streamlit 支持 :color[text] 语法
                        st.markdown(f":{color}[**{label}**] {e.title}")
                        with st.expander("查看详情 & 链接"):
                            st.write(f"发布时间: {e.published}")
                            st.write(f"情绪得分: {score:.2f} (-1.0 ~ 1.0)")
                            st.markdown(f"[👉 点击阅读原文]({e.link})")
                    st.divider()
            except: pass
