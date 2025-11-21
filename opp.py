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

# --- 2. 侧边栏：控制中心 ---
st.sidebar.title("⚙️ 控制中心")

# A. 自动获取 Secrets 中的 API Key
# 优先读取云端后台配置，如果没有，再显示输入框
if "DEEPSEEK_API_KEY" in st.secrets:
    api_key = st.secrets["DEEPSEEK_API_KEY"]
    st.sidebar.success("✅ API Key 已从云端安全加载")
else:
    api_key = st.sidebar.text_input("DeepSeek API Key", type="password", placeholder="sk-...")

MODEL_NAME = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"

# B. 刷新控制
st.sidebar.subheader("⏱️ 刷新设置")
if st.sidebar.button("🔄 立即刷新数据", type="primary"):
    st.rerun()

refresh_rate = st.sidebar.slider("自动刷新 (分钟)", 5, 60, 30)

st.sidebar.markdown("---")
st.sidebar.subheader("🔗 快捷入口")
st.sidebar.markdown("[📅 财经日历](https://cn.investing.com/economic-calendar/)")
st.sidebar.caption(f"更新时间: {datetime.datetime.now().strftime('%H:%M:%S')}")

# --- 3. 初始化 AI 记忆 (Session State) ---
# 这是页面刷新不丢失内容的关键
if 'ai_history' not in st.session_state:
    st.session_state['ai_history'] = [] # 存储历史报告列表

# --- 4. 核心逻辑函数 ---

@st.cache_data(ttl=3600) 
def get_cnn_fear_greed_index():
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.cnn.com/"
        }
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return int(data['fear_and_greed_historical']['data'][-1]['y']), "CNN 官方数据"
        return None, None
    except: return None, None

def plot_gauge(score, source):
    if score is None: return go.Figure()
    color = "#GRAY"
    if score > 75: color = "#FF4B4B"
    elif score > 55: color = "#FF8C00"
    elif score < 25: color = "#006400"
    elif score < 45: color = "#00CC96"
    
    fig = go.Figure(go.Indicator(
        mode = "gauge+number", value = score,
        title = {'text': f"市场情绪 ({source})", 'font': {'size': 18}},
        number = {'font': {'size': 40, 'color': color}},
        gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': color},
                 'steps': [{'range': [0, 25], 'color': 'rgba(0,255,0,0.2)'}, {'range': [75, 100], 'color': 'rgba(255,0,0,0.2)'}]}
    ))
    fig.update_layout(height=250, margin=dict(l=10, r=10, t=40, b=10))
    return fig

def analyze_sentiment_tag(text):
    s = TextBlob(text).sentiment.polarity
    if s > 0.3: return "🟢 极度乐观", "green"
    elif 0.1 < s <= 0.3: return "🥬 偏多", "green"
    elif -0.1 <= s <= 0.1: return "⚪ 中性", "gray"
    elif -0.3 <= s < -0.1: return "🟠 偏空", "orange"
    else: return "🔴 极度悲观", "red"

@st.cache_data(ttl=300)
def get_market_data():
    return yf.Tickers("SPY QQQ IEF").history(period="3mo")

# --- 5. 主界面 ---
st.title("🦈 华尔街风向标 (AI Memory Ver.)")
st.caption(f"当前时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

try:
    # 数据与图表
    market_data = get_market_data()
    spy = market_data['Close']['SPY'].dropna()
    qqq = market_data['Close']['QQQ'].dropna()
    ief = market_data['Close']['IEF'].dropna()
    
    cnn_score, cnn_src = get_cnn_fear_greed_index()
    if cnn_score is None:
        # RSI Backup
        delta = spy.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        cnn_score = 100 - (100 / (1 + rs)).iloc[-1]
        cnn_src = "RSI 模拟值"

    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("1. 核心资产")
        m1, m2, m3 = st.columns(3)
        m1.metric("标普500", f"${spy.iloc[-1]:.1f}", f"{spy.iloc[-1]-spy.iloc[-2]:.2f}")
        m2.metric("纳指QQQ", f"${qqq.iloc[-1]:.1f}", f"{qqq.iloc[-1]-qqq.iloc[-2]:.2f}")
        m3.metric("国债IEF", f"${ief.iloc[-1]:.1f}", f"{ief.iloc[-1]-ief.iloc[-2]:.2f}")
        st.line_chart(pd.DataFrame({'SPY': spy, 'QQQ': qqq}), height=200)
    
    with c2:
        st.subheader("情绪表")
        st.plotly_chart(plot_gauge(cnn_score, cnn_src), use_container_width=True)

except Exception as e: st.error(f"数据错误: {e}")

# --- 6. AI 智能情报台 (含记忆功能) ---
st.markdown("---")
st.subheader("3. DeepSeek 智能研报 (带历史记忆)")

rss_feeds = {
    "Goldman": "https://news.google.com/rss/search?q=Goldman+Sachs+outlook+when:7d&hl=en-US&gl=US&ceid=US:en",
    "Morgan": "https://news.google.com/rss/search?q=Morgan+Stanley+market+outlook+when:7d&hl=en-US&gl=US&ceid=US:en",
    "Risk": "https://news.google.com/rss/search?q=stock+market+crash+warning+when:2d&hl=en-US&gl=US&ceid=US:en"
}

# 抓取新闻
all_news = []
for src, url in rss_feeds.items():
    try:
        f = feedparser.parse(url)
        for e in f.entries:
            ts = time.mktime(e.published_parsed) if hasattr(e, 'published_parsed') else 0
            all_news.append({"s": src, "t": e.title, "l": e.link, "ts": ts})
    except: pass
all_news.sort(key=lambda x: x['ts'], reverse=True)

# 布局
col_ai, col_news = st.columns([1, 1.5])

with col_ai:
    # 显示历史分析记录
    if len(st.session_state['ai_history']) > 0:
        with st.expander("📜 查看之前的分析记录", expanded=False):
            for i, report in enumerate(reversed(st.session_state['ai_history'])):
                st.caption(f"分析时间: {report['time']}")
                st.markdown(report['content'])
                st.divider()

    # 生成新分析按钮
    if st.button("⚡ 生成今日最新研报 (对比旧观点)", type="primary"):
        if not api_key: st.warning("请配置 API Key")
        else:
            # 1. 准备上下文
            latest_news = "\n".join([f"- [{n['s']}] {n['t']}" for n in all_news[:10]])
            
            # 2. 获取上一条历史记录（如果有）
            previous_context = ""
            if len(st.session_state['ai_history']) > 0:
                last_report = st.session_state['ai_history'][-1]['content']
                previous_context = f"\n\n【你上一次的分析结论是】：\n{last_report}\n\n请将上面的旧观点与下面的新新闻进行比对："
            else:
                previous_context = "\n这是第一次分析，请建立基准观点。"

            # 3. 构建超级 Prompt
            prompt = f"""
            你是一位专业的华尔街风控官。
            {previous_context}

            【今日最新新闻流】：
            {latest_news}

            请输出中文简报（Markdown格式），必须包含以下部分：
            1. **🔄 观点变化**：(对比你上次的分析，市场情绪是变好了还是变坏了？)
            2. **🚨 核心风险更新**：(当前最大的雷是什么？)
            3. **💡 最新操作建议**：(针对SPY/QQQ的建议)
            """

            try:
                with st.spinner("正在对比历史观点并分析新数据..."):
                    client = OpenAI(api_key=api_key, base_url=BASE_URL)
                    resp = client.chat.completions.create(
                        model=MODEL_NAME, messages=[{"role":"user", "content":prompt}])
                    
                    new_content = resp.choices[0].message.content
                    
                    # 4. 存入记忆
                    st.session_state['ai_history'].append({
                        'time': datetime.datetime.now().strftime('%H:%M'),
                        'content': new_content
                    })
                    st.rerun() # 重新运行以显示最新结果
            except Exception as e: st.error(str(e))

    # 始终显示最新的一条分析
    if len(st.session_state['ai_history']) > 0:
        latest = st.session_state['ai_history'][-1]
        st.success(f"📊 最新分析 ({latest['time']})")
        st.markdown(latest['content'])
    else:
        st.info("👈 点击按钮生成今日第一份研报")

with col_news:
    st.markdown("#### 📰 实时资讯")
    with st.container(height=600):
        for n in all_news[:20]:
            label, color = analyze_sentiment_tag(n['t'])
            st.markdown(f":{color}[**{label}**] {n['t']}")
            st.caption(f"{n['s']} | [原文]({n['l']})")
            st.divider()

if refresh_rate: time.sleep(1)
