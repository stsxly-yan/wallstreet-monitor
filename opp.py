import streamlit as st
import yfinance as yf
import pandas as pd
import feedparser
from openai import OpenAI
from textblob import TextBlob
import plotly.graph_objects as go
import requests
import datetime
import time

# --- 1. 页面配置 ---
st.set_page_config(page_title="DeepSeek 智能风控仪表盘", layout="wide", page_icon="🦈")

# --- 2. 侧边栏 ---
st.sidebar.title("⚙️ 设置")
api_key = st.sidebar.text_input("DeepSeek API Key", type="password", placeholder="sk-...")
MODEL_NAME = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
st.sidebar.info("已启用 CNN 恐慌指数实时图表")

# --- 3. 核心逻辑函数 ---

# A. 获取 CNN 恐慌贪婪指数 (黑科技版)
@st.cache_data(ttl=3600) # 缓存1小时，避免频繁请求被封
def get_cnn_fear_greed_index():
    try:
        # 这是一个非官方但目前稳定的 CNN 数据接口
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            # 获取最新的一条数据
            latest_data = data['fear_and_greed_historical']['data'][-1]
            score = int(latest_data['y'])
            timestamp = latest_data['x'] # 时间戳
            return score
        else:
            return None
    except:
        return None

# B. 画仪表盘 (Gauge Chart)
def plot_gauge(score):
    if score is None:
        return go.Figure() # 返回空图
    
    # 颜色逻辑
    color = "red"
    if score > 75: color = "#FF4B4B" # 极度贪婪 (红)
    elif score > 55: color = "#FF8C00" # 贪婪 (橙)
    elif score > 45: color = "#GRAY" # 中性
    elif score > 25: color = "#00CC96" # 恐慌 (绿-机会)
    else: color = "#006400" # 极度恐慌 (深绿-大机会)

    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = score,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "CNN 恐慌贪婪指数", 'font': {'size': 20}},
        number = {'font': {'size': 40, 'color': color}},
        gauge = {
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "white"},
            'bar': {'color': color},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 25], 'color': 'rgba(0, 255, 0, 0.3)'},  # 极度恐慌区域
                {'range': [75, 100], 'color': 'rgba(255, 0, 0, 0.3)'} # 极度贪婪区域
            ],
        }
    ))
    # 调整布局大小
    fig.update_layout(height=250, margin=dict(l=10, r=10, t=40, b=10))
    return fig

# C. 情绪分析
def analyze_sentiment_tag(text):
    analysis = TextBlob(text)
    score = analysis.sentiment.polarity
    if score > 0.3: return "🟢 极度乐观", "green", score
    elif 0.1 < score <= 0.3: return "🥬 偏多", "green", score
    elif -0.1 <= score <= 0.1: return "⚪ 中性", "gray", score
    elif -0.3 <= score < -0.1: return "🟠 偏空", "orange", score
    else: return "🔴 极度悲观", "red", score

@st.cache_data(ttl=300)
def get_market_data():
    tickers = yf.Tickers("SPY QQQ IEF") 
    hist = tickers.history(period="3mo")
    return hist

# --- 4. 主界面 ---
st.title("🦈 华尔街风向标 (Live Update)")
st.caption(f"更新: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# 1. 市场数据
try:
    market_data = get_market_data()
    
    def safe_metric(sym):
        try:
            s = market_data['Close'][sym].dropna()
            if len(s) < 2: return 0, 0
            val = s.iloc[-1]
            chg = val - s.iloc[-2]
            return val, chg
        except: return 0, 0

    spy_val, spy_chg = safe_metric("SPY")
    qqq_val, qqq_chg = safe_metric("QQQ")
    ief_val, ief_chg = safe_metric("IEF")
    
    # 获取 CNN 分数
    cnn_score = get_cnn_fear_greed_index()

    # 布局：左边是指数据，右边是仪表盘
    col_metrics, col_gauge = st.columns([2, 1])

    with col_metrics:
        st.subheader("1. 核心资产")
        c1, c2, c3 = st.columns(3)
        c1.metric("📈 标普500 (SPY)", f"${spy_val:.1f}", f"{spy_chg:.2f}")
        c2.metric("💻 纳指 (QQQ)", f"${qqq_val:.1f}", f"{qqq_chg:.2f}")
        c3.metric("⚖️ 国债 (IEF)", f"${ief_val:.2f}", f"{ief_chg:.2f}", help="红跌=利率涨风险")
        
        st.markdown("---")
        st.subheader("2. 趋势图")
        chart_data = pd.DataFrame({
            'SPY': market_data['Close']['SPY'],
            'QQQ': market_data['Close']['QQQ']
        })
        st.line_chart(chart_data, height=200)

    with col_gauge:
        st.subheader("情绪仪表盘")
        # 显示 CNN 图表
        if cnn_score is not None:
            fig = plot_gauge(cnn_score)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("CNN 数据源暂时连接超时，请稍后再试或参考 VIX。")
            st.metric("替代指标 VIX", "20.4", "+1.2") # 示例

except Exception as e:
    st.error(f"数据加载错误: {e}")

# --- 3. 新闻聚合 (按时间排序) ---
st.markdown("---")
st.subheader("3. 全球情报流 (Real-time News)")

rss_feeds = {
    "Goldman Sachs": "https://news.google.com/rss/search?q=Goldman+Sachs+outlook+when:7d&hl=en-US&gl=US&ceid=US:en",
    "Morgan Stanley": "https://news.google.com/rss/search?q=Morgan+Stanley+market+outlook+when:7d&hl=en-US&gl=US&ceid=US:en",
    "Market Risk": "https://news.google.com/rss/search?q=stock+market+crash+warning+when:2d&hl=en-US&gl=US&ceid=US:en"
}

# 1. 抓取并合并所有新闻
all_news_items = []
for src, url in rss_feeds.items():
    try:
        f = feedparser.parse(url)
        for e in f.entries:
            # 解析时间
            published_time = "未知时间"
            timestamp = 0
            if hasattr(e, 'published_parsed') and e.published_parsed:
                # 转换为时间戳以便排序
                timestamp = time.mktime(e.published_parsed)
                # 转换为易读格式 (年-月-日 时:分)
                dt_object = datetime.datetime.fromtimestamp(timestamp)
                published_time = dt_object.strftime('%Y-%m-%d %H:%M')
            
            all_news_items.append({
                "source": src,
                "title": e.title,
                "link": e.link,
                "time_str": published_time,
                "timestamp": timestamp
            })
    except: pass

# 2. 按时间戳倒序排序 (最新的在最前)
all_news_items.sort(key=lambda x: x['timestamp'], reverse=True)

# 3. 显示新闻
col_ui_1, col_ui_2 = st.columns([1, 1.5])

with col_ui_1:
    st.markdown("#### 🤖 AI 简报")
    if st.button("⚡ 分析最新新闻", type="primary"):
        if not api_key: st.warning("需输入 Key")
        else:
            # 只发给 AI 前 10 条最新的，避免 Token 太多
            top_news = "\n".join([f"- {n['title']}" for n in all_news_items[:10]])
            try:
                client = OpenAI(api_key=api_key, base_url=BASE_URL)
                prompt = f"分析以下最新美股新闻风险:\n{top_news}\n给出中文简报。"
                with st.spinner("AI 分析中..."):
                    resp = client.chat.completions.create(
                        model=MODEL_NAME, messages=[{"role":"user", "content":prompt}])
                    st.markdown(resp.choices[0].message.content)
            except Exception as e: st.error(str(e))

with col_ui_2:
    st.markdown("#### 📰 最新资讯 (按时间排序)")
    news_container = st.container(height=600)
    with news_container:
        for item in all_news_items[:20]: # 只显示最新的20条
            label, color, score = analyze_sentiment_tag(item['title'])
            
            # 布局：标题行
            st.markdown(f":{color}[**{label}**] [{item['source']}] **{item['title']}**")
            
            # 详情行 (灰色小字显示时间)
            st.caption(f"🕒 {item['time_str']} | [阅读原文]({item['link']})")
            st.divider()
