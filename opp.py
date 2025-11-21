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
st.set_page_config(page_title="DeepSeek 智能风控系统", layout="wide", page_icon="🔒")

# ============================================================
#  🚫 模块 A: 身份验证系统 (Gatekeeper) - 保持不变
# ============================================================

def check_login():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['user_role'] = None
        st.session_state['username'] = None

    if st.session_state['logged_in']: return True

    st.markdown("## 🔒 华尔街风控系统 (专业版)")
    st.info("请登录以访问实时风控数据。")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        username = st.text_input("账号 / Username")
        password = st.text_input("密码 / Password", type="password")
        
        if st.button("登录 / Login"):
            if username == st.secrets["admin"]["username"] and password == st.secrets["admin"]["password"]:
                st.session_state['logged_in'] = True
                st.session_state['user_role'] = "admin"
                st.session_state['username'] = username
                st.success("管理员登录成功")
                time.sleep(0.5)
                st.rerun()
            elif username in st.secrets["users"] and password == st.secrets["users"][username]:
                st.session_state['logged_in'] = True
                st.session_state['user_role'] = "user"
                st.session_state['username'] = username
                st.success(f"欢迎回来, {username}")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("❌ 账号或密码错误")
    return False

if not check_login(): st.stop()

# ============================================================
#  ✅ 模块 B: 系统核心
# ============================================================

api_key = st.secrets["DEEPSEEK_API_KEY"]
MODEL_NAME = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"

if 'ai_history' not in st.session_state: st.session_state['ai_history'] = []

# --- 侧边栏 ---
st.sidebar.title("⚙️ 控制台")
st.sidebar.write(f"👤 用户: **{st.session_state['username']}**")
if st.sidebar.button("退出登录"):
    st.session_state['logged_in'] = False
    st.rerun()

if st.session_state['user_role'] == "admin":
    with st.sidebar.expander("🛠️ 管理员监控", expanded=False):
        st.write("**已开通用户:**")
        for u in st.secrets["users"]: st.write(f"- {u}")

st.sidebar.markdown("---")
if st.sidebar.button("🔄 立即刷新数据", type="primary"): st.rerun()
refresh_rate = st.sidebar.slider("自动刷新 (分钟)", 5, 60, 30)

st.sidebar.markdown("---")
st.sidebar.markdown("[📅 财经日历](https://cn.investing.com/economic-calendar/)")
st.sidebar.markdown("[😱 CNN恐慌指数](https://edition.cnn.com/markets/fear-and-greed)")
st.sidebar.caption(f"更新: {datetime.datetime.now().strftime('%H:%M:%S')}")

# --- 核心逻辑函数 ---

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

def calculate_rsi(data, window=14):
    try:
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    except: return pd.Series([50]*len(data))

@st.cache_data(ttl=300)
def get_market_data():
    # 恢复 VIXY 数据获取
    return yf.Tickers("SPY QQQ IEF VIXY").history(period="3mo")

# --- 主界面显示 ---
st.title("🦈 华尔街风控系统 (Enterprise)")
st.caption(f"数据快照时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

try:
    market_data = get_market_data()
    
    # 1. 数据提取 (增加容错)
    def get_latest(ticker):
        try:
            s = market_data['Close'][ticker].dropna()
            return s.iloc[-1], s.iloc[-1] - s.iloc[-2], s
        except: return 0, 0, None

    spy_val, spy_chg, spy_series = get_latest('SPY')
    qqq_val, qqq_chg, qqq_series = get_latest('QQQ')
    ief_val, ief_chg, ief_series = get_latest('IEF')
    vix_val, vix_chg, vix_series = get_latest('VIXY') # 恢复 VIX
    
    # 2. RSI 计算
    try:
        rsi_series = calculate_rsi(market_data['Close']['SPY'])
        rsi_val = rsi_series.iloc[-1]
        rsi_delta = rsi_val - rsi_series.iloc[-2]
    except: rsi_val, rsi_delta = 50, 0

    # 3. CNN 指数
    cnn_score, cnn_src = get_cnn_fear_greed_index()
    if cnn_score is None:
        cnn_score = rsi_val
        cnn_src = "RSI 模拟"

    # === 恢复：5大核心指标卡片 ===
    st.subheader("1. 全球核心资产监控")
    # 使用 5 列布局，恢复 VIX 和 RSI
    c1, c2, c3, c4, c5 = st.columns(5)
    
    c1.metric("📈 标普500 (SPY)", f"${spy_val:.1f}", f"{spy_chg:.2f}")
    c2.metric("💻 纳指科技 (QQQ)", f"${qqq_val:.1f}", f"{qqq_chg:.2f}")
    c3.metric("⚖️ 国债价格 (IEF)", f"${ief_val:.2f}", f"{ief_chg:.2f}", help="红跌=利率涨(利空)")
    
    # 恢复 VIX 卡片
    c4.metric("📉 恐慌 ETF (VIX)", f"${vix_val:.2f}", f"{vix_chg:.2f}", delta_color="inverse", help="上涨代表恐慌增加")
    
    # 恢复 RSI 卡片与机会提示
    rsi_label = "中性"
    if rsi_val > 70: rsi_label = "🔴 过热风险"
    elif rsi_val < 30: rsi_label = "🟢 超卖机会"
    
    c5.metric("🐂 RSI 情绪", f"{rsi_val:.1f}", f"{rsi_delta:.1f}", delta_color="off")
    if rsi_val > 70: c5.error(rsi_label)
    elif rsi_val < 30: c5.success(rsi_label)
    else: c5.info(rsi_label)

    st.markdown("---")

    # === 恢复：交互式图表 (Tabs) 与 CNN 仪表盘 ===
    col_chart, col_gauge = st.columns([2, 1])

    with col_chart:
        st.subheader("2. 趋势透视 (Interactive)")
        # 恢复 Tabs 切换功能
        tab1, tab2, tab3 = st.tabs(["📊 核心资产", "😱 恐慌趋势", "🏦 利率压力"])
        
        with tab1:
            st.line_chart(pd.DataFrame({'SPY': spy_series, 'QQQ': qqq_series}), height=250)
        with tab2:
            st.area_chart(vix_series, color="#FF4B4B", height=250) # 红色恐慌
        with tab3:
            st.line_chart(ief_series, color="#FFAA00", height=250) # 黄色国债

    with col_gauge:
        st.subheader("市场情绪表")
        st.plotly_chart(plot_gauge(cnn_score, cnn_src), use_container_width=True)

except Exception as e: st.error(f"数据加载异常: {e}")

# --- AI 模块 (保留全部功能) ---
st.markdown("---")
st.subheader("3. DeepSeek 智能研报")

rss_feeds = {
    "Goldman": "https://news.google.com/rss/search?q=Goldman+Sachs+outlook+when:7d&hl=en-US&gl=US&ceid=US:en",
    "Morgan": "https://news.google.com/rss/search?q=Morgan+Stanley+market+outlook+when:7d&hl=en-US&gl=US&ceid=US:en",
    "Risk": "https://news.google.com/rss/search?q=stock+market+crash+warning+when:2d&hl=en-US&gl=US&ceid=US:en"
}

all_news = []
for src, url in rss_feeds.items():
    try:
        f = feedparser.parse(url)
        for e in f.entries:
            ts = time.mktime(e.published_parsed) if hasattr(e, 'published_parsed') else 0
            time_str = datetime.datetime.fromtimestamp(ts).strftime('%m-%d %H:%M')
            all_news.append({"s": src, "t": e.title, "l": e.link, "ts": ts, "time_str": time_str})
    except: pass
all_news.sort(key=lambda x: x['ts'], reverse=True)

col_ai, col_news = st.columns([1, 1.5])

with col_ai:
    if len(st.session_state['ai_history']) > 0:
        with st.expander("📜 查看历史记录"):
            for report in reversed(st.session_state['ai_history']):
                st.caption(f"🕒 {report['time']}")
                st.markdown(report['content'])
                st.divider()

    if st.button("⚡ 生成今日研报 (对比旧观点)", type="primary"):
        user = st.session_state['username']
        print(f"[AUDIT LOG] User '{user}' requested AI analysis at {datetime.datetime.now()}")
        
        latest_news = "\n".join([f"- [{n['s']}] {n['t']}" for n in all_news[:10]])
        prev_ctx = f"\n旧观点参考：\n{st.session_state['ai_history'][-1]['content']}\n" if len(st.session_state['ai_history']) > 0 else "\n这是首次分析。"
            
        prompt = f"我是风控官。{prev_ctx}\n新数据：\n{latest_news}\n输出中文简报：1.观点变化 2.风险 3.建议"
        
        try:
            with st.spinner("AI 思考中..."):
                client = OpenAI(api_key=api_key, base_url=BASE_URL)
                resp = client.chat.completions.create(model=MODEL_NAME, messages=[{"role":"user", "content":prompt}])
                st.session_state['ai_history'].append({'time': datetime.datetime.now().strftime('%H:%M'), 'content': resp.choices[0].message.content})
                st.rerun()
        except Exception as e: st.error(str(e))

    if len(st.session_state['ai_history']) > 0:
        st.success(f"📊 最新分析 ({st.session_state['ai_history'][-1]['time']})")
        st.markdown(st.session_state['ai_history'][-1]['content'])

with col_news:
    st.markdown("#### 📰 实时资讯流")
    with st.container(height=600):
        for n in all_news[:20]:
            label, color = analyze_sentiment_tag(n['t'])
            st.markdown(f":{color}[**{label}**] {n['t']}")
            st.caption(f"🕒 {n['time_str']} | {n['s']} | [原文]({n['l']})")
            st.divider()

if refresh_rate: time.sleep(1)
