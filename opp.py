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
import random

# --- 1. 页面配置 ---
st.set_page_config(page_title="DeepSeek 智能风控仪表盘", layout="wide", page_icon="🦈")

# --- 2. 侧边栏：全局控制中心 ---
st.sidebar.title("⚙️ 控制中心")

# A. 刷新控制
st.sidebar.subheader("⏱️ 刷新设置")
if st.sidebar.button("🔄 立即刷新数据 (Refresh Now)", type="primary"):
    st.rerun()

refresh_rate = st.sidebar.slider("自动刷新间隔 (分钟)", 5, 60, 30)

# B. API 设置
st.sidebar.markdown("---")
st.sidebar.subheader("🤖 模型设置")
api_key = st.sidebar.text_input("DeepSeek API Key", type="password", placeholder="sk-...")
MODEL_NAME = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"

# C. 快捷工具
st.sidebar.markdown("---")
st.sidebar.subheader("🔗 快捷入口")
st.sidebar.markdown("[📅 财经日历 (Investing)](https://cn.investing.com/economic-calendar/)")
st.sidebar.caption(f"更新时间: {datetime.datetime.now().strftime('%H:%M:%S')}")

# --- 3. 核心逻辑函数 ---

# A. 获取 CNN 恐慌贪婪指数 (增强伪装版)
@st.cache_data(ttl=3600) 
def get_cnn_fear_greed_index():
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        # 伪装成真实的 Mac Chrome 浏览器
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.cnn.com/",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        }
        # 增加超时时间到 10秒
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            latest = data['fear_and_greed_historical']['data'][-1]
            return int(latest['y']), "CNN 官方数据"
        return None, None
    except:
        return None, None

# B. 画仪表盘 (通用版)
def plot_gauge(score, source_label):
    if score is None: return go.Figure()
    
    # 动态变色
    color = "#GRAY"
    if score > 75: color = "#FF4B4B" # 极度贪婪
    elif score > 55: color = "#FF8C00" # 贪婪
    elif score < 25: color = "#006400" # 极度恐慌
    elif score < 45: color = "#00CC96" # 恐慌
    
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = score,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': f"市场情绪 ({source_label})", 'font': {'size': 18}},
        number = {'font': {'size': 40, 'color': color}},
        gauge = {
            'axis': {'range': [0, 100]},
            'bar': {'color': color},
            'steps': [
                {'range': [0, 25], 'color': 'rgba(0, 255, 0, 0.2)'},
                {'range': [75, 100], 'color': 'rgba(255, 0, 0, 0.2)'}
            ],
        }
    ))
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

# D. 计算 RSI
def calculate_rsi(data, window=14):
    try:
        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    except:
        return pd.Series([50]*len(data))

# E. 获取市场数据
@st.cache_data(ttl=300)
def get_market_data():
    tickers = yf.Tickers("SPY QQQ IEF") 
    hist = tickers.history(period="3mo")
    return hist

# --- 4. 主界面布局 ---
st.title("🦈 华尔街风向标 (Pro)")
st.caption(f"数据时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

try:
    # 1. 数据层
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

    # 2. 智能仪表盘逻辑
    # 优先取 CNN，如果失败，取 RSI 模拟
    gauge_score, gauge_source = get_cnn_fear_greed_index()
    
    # 计算 RSI 作为备用
    try:
        spy_data = market_data.xs('SPY', level=1, axis=1) if isinstance(market_data.columns, pd.MultiIndex) else market_data
        rsi_val = calculate_rsi(spy_data).iloc[-1]
    except:
        rsi_val = 50

    # 替补逻辑
    if gauge_score is None:
        gauge_score = rsi_val
        gauge_source = "RSI 模拟值 (CNN超时)"

    # 3. 可视化布局
    col_metrics, col_gauge = st.columns([2, 1])

    with col_metrics:
        st.subheader("1. 核心资产")
        c1, c2, c3 = st.columns(3)
        c1.metric("📈 标普500", f"${spy_val:.1f}", f"{spy_chg:.2f}")
        c2.metric("💻 纳指", f"${qqq_val:.1f}", f"{qqq_chg:.2f}")
        c3.metric("⚖️ 国债", f"${ief_val:.2f}", f"{ief_chg:.2f}", help="红跌=利空")
        
        st.markdown("---")
        st.subheader("2. 趋势图")
        chart_df = pd.DataFrame({'SPY': market_data['Close']['SPY'], 'QQQ': market_data['Close']['QQQ']})
        st.line_chart(chart_df, height=200)

    with col_gauge:
        st.subheader("恐慌情绪表")
        # 无论 CNN 是否成功，这里都会显示一个图
        fig = plot_gauge(gauge_score, gauge_source)
        st.plotly_chart(fig, use_container_width=True)
        if "RSI" in gauge_source:
            st.caption("⚠️ 注：因云端网络限制，CNN 暂时无法连接，当前显示基于 RSI 的模拟情绪值。")

except Exception as e:
    st.error(f"核心数据加载失败: {e}")

# --- 5. 新闻情报流 ---
st.markdown("---")
st.subheader("3. 全球情报流")

rss_feeds = {
    "Goldman Sachs": "https://news.google.com/rss/search?q=Goldman+Sachs+outlook+when:7d&hl=en-US&gl=US&ceid=US:en",
    "Morgan Stanley": "https://news.google.com/rss/search?q=Morgan+Stanley+market+outlook+when:7d&hl=en-US&gl=US&ceid=US:en",
    "Market Risk": "https://news.google.com/rss/search?q=stock+market+crash+warning+when:2d&hl=en-US&gl=US&ceid=US:en"
}

all_news = []
for src, url in rss_feeds.items():
    try:
        f = feedparser.parse(url)
        for e in f.entries:
            ts = 0
            time_str = ""
            if hasattr(e, 'published_parsed') and e.published_parsed:
                ts = time.mktime(e.published_parsed)
                time_str = datetime.datetime.fromtimestamp(ts).strftime('%m-%d %H:%M')
            all_news.append({"source": src, "title": e.title, "link": e.link, "time_str": time_str, "timestamp": ts})
    except: pass

all_news.sort(key=lambda x: x['timestamp'], reverse=True)

c_ai, c_list = st.columns([1, 1.5])

with c_ai:
    st.markdown("#### 🧠 DeepSeek 研报")
    if st.button("⚡ 生成简报", type="primary"):
        if not api_key: st.warning("请先设置 API Key")
        else:
            context = "\n".join([f"- [{n['source']}] {n['title']}" for n in all_news[:10]])
            try:
                client = OpenAI(api_key=api_key, base_url=BASE_URL)
                prompt = f"根据最新新闻分析美股风险:\n{context}\n输出中文简报: 1.风险评分 2.多空观点 3.操作建议"
                with st.spinner("分析中..."):
                    resp = client.chat.completions.create(
                        model=MODEL_NAME, messages=[{"role":"user", "content":prompt}])
                    st.success("完成")
                    st.markdown(resp.choices[0].message.content)
            except Exception as e: st.error(str(e))

with c_list:
    st.markdown("#### 📰 资讯流")
    container = st.container(height=600)
    with container:
        for n in all_news[:25]:
            label, color, score = analyze_sentiment_tag(n['title'])
            st.markdown(f":{color}[**{label}**] {n['title']}")
            st.caption(f"🕒 {n['time_str']} | {n['source']} | [原文]({n['link']})")
            st.divider()

if refresh_rate: time.sleep(1)
