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
#  🚫 模块 A: 身份验证系统 (Gatekeeper)
# ============================================================

def check_login():
    """登录逻辑：拦截未授权用户"""
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['user_role'] = None
        st.session_state['username'] = None

    if st.session_state['logged_in']:
        return True

    # 登录界面设计
    st.markdown("## 🔒 华尔街风控系统 (专业版)")
    st.info("请登录以访问实时风控数据。")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        username = st.text_input("账号 / Username")
        password = st.text_input("密码 / Password", type="password")
        
        if st.button("登录 / Login"):
            # 1. 验证管理员
            if username == st.secrets["admin"]["username"] and password == st.secrets["admin"]["password"]:
                st.session_state['logged_in'] = True
                st.session_state['user_role'] = "admin"
                st.session_state['username'] = username
                st.success("管理员登录成功")
                time.sleep(0.5)
                st.rerun()
            
            # 2. 验证普通用户
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

# ⛔ 如果未登录，在此处停止加载
if not check_login():
    st.stop()

# ============================================================
#  ✅ 模块 B: 系统核心 (登录后可见)
# ============================================================

# 1. 基础参数
api_key = st.secrets["DEEPSEEK_API_KEY"]
MODEL_NAME = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"

# 2. 初始化 Session State (找回 AI 记忆功能)
if 'ai_history' not in st.session_state:
    st.session_state['ai_history'] = []

# --- 侧边栏：用户中心与工具 (融合 v3.5 和 v4.0) ---
st.sidebar.title("⚙️ 控制台")

# 用户信息
st.sidebar.write(f"👤 用户: **{st.session_state['username']}**")
if st.sidebar.button("退出登录"):
    st.session_state['logged_in'] = False
    st.rerun()

# 管理员面板
if st.session_state['user_role'] == "admin":
    with st.sidebar.expander("🛠️ 管理员监控", expanded=False):
        st.write("**已开通用户:**")
        for u in st.secrets["users"]:
            st.write(f"- {u}")
        st.caption("查看详细用量请前往 Streamlit Logs")

st.sidebar.markdown("---")

# 刷新设置 (v3.5 功能回归)
st.sidebar.subheader("⏱️ 刷新与工具")
if st.sidebar.button("🔄 立即刷新数据", type="primary"):
    st.rerun()
refresh_rate = st.sidebar.slider("自动刷新 (分钟)", 5, 60, 30)

# 快捷链接 (v3.5 功能回归)
st.sidebar.markdown("---")
st.sidebar.markdown("[📅 财经日历 (Investing)](https://cn.investing.com/economic-calendar/)")
st.sidebar.markdown("[😱 恐慌贪婪指数 (CNN)](https://edition.cnn.com/markets/fear-and-greed)")
st.sidebar.caption(f"上次更新: {datetime.datetime.now().strftime('%H:%M:%S')}")


# --- 核心逻辑函数 ---

# CNN 指数 (v3.4 增强版)
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

# 仪表盘绘制
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

# 情绪标签
def analyze_sentiment_tag(text):
    s = TextBlob(text).sentiment.polarity
    if s > 0.3: return "🟢 极度乐观", "green"
    elif 0.1 < s <= 0.3: return "🥬 偏多", "green"
    elif -0.1 <= s <= 0.1: return "⚪ 中性", "gray"
    elif -0.3 <= s < -0.1: return "🟠 偏空", "orange"
    else: return "🔴 极度悲观", "red"

# 市场数据
@st.cache_data(ttl=300)
def get_market_data():
    return yf.Tickers("SPY QQQ IEF").history(period="3mo")

# --- 主界面显示 ---
st.title("🦈 华尔街风控系统 (Enterprise)")
st.caption(f"数据快照时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

try:
    market_data = get_market_data()
    spy = market_data['Close']['SPY'].dropna()
    qqq = market_data['Close']['QQQ'].dropna()
    ief = market_data['Close']['IEF'].dropna()
    
    # 智能替补逻辑
    cnn_score, cnn_src = get_cnn_fear_greed_index()
    if cnn_score is None:
        delta = spy.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        cnn_score = 100 - (100 / (1 + rs)).iloc[-1]
        cnn_src = "RSI 模拟值 (CNN超时)"

    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("1. 核心资产监控")
        m1, m2, m3 = st.columns(3)
        m1.metric("标普500 (SPY)", f"${spy.iloc[-1]:.1f}", f"{spy.iloc[-1]-spy.iloc[-2]:.2f}")
        m2.metric("纳指科技 (QQQ)", f"${qqq.iloc[-1]:.1f}", f"{qqq.iloc[-1]-qqq.iloc[-2]:.2f}")
        m3.metric("国债价格 (IEF)", f"${ief.iloc[-1]:.1f}", f"{ief.iloc[-1]-ief.iloc[-2]:.2f}", help="红跌=利率涨(利空)")
        st.line_chart(pd.DataFrame({'SPY': spy, 'QQQ': qqq}), height=200)
    with c2:
        st.subheader("市场情绪表")
        st.plotly_chart(plot_gauge(cnn_score, cnn_src), use_container_width=True)

except Exception as e: st.error(f"数据加载异常: {e}")

# --- AI 模块 (v3.5 完整功能回归 + v4.0 审计) ---
st.markdown("---")
st.subheader("2. DeepSeek 智能研报 (带历史记忆)")

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
            time_str = datetime.datetime.fromtimestamp(ts).strftime('%m-%d %H:%M') # 找回时间显示
            all_news.append({"s": src, "t": e.title, "l": e.link, "ts": ts, "time_str": time_str})
    except: pass
all_news.sort(key=lambda x: x['ts'], reverse=True)

col_ai, col_news = st.columns([1, 1.5])

with col_ai:
    # 历史记录回溯 (v3.5 功能)
    if len(st.session_state['ai_history']) > 0:
        with st.expander("📜 查看历史分析记录", expanded=False):
            for report in reversed(st.session_state['ai_history']):
                st.caption(f"🕒 分析时间: {report['time']}")
                st.markdown(report['content'])
                st.divider()

    # 生成按钮
    if st.button("⚡ 生成今日研报 (对比旧观点)", type="primary"):
        # 1. 审计日志 (v4.0 功能)
        user = st.session_state['username']
        print(f"[AUDIT LOG] User '{user}' requested AI analysis at {datetime.datetime.now()}")
        
        # 2. 准备 Prompt (v3.5 详细对比逻辑)
        latest_news = "\n".join([f"- [{n['s']}] {n['t']}" for n in all_news[:10]])
        
        prev_ctx = ""
        if len(st.session_state['ai_history']) > 0:
            prev_ctx = f"\n\n【你上一次的分析结论】：\n{st.session_state['ai_history'][-1]['content']}\n\n请将上面的旧观点与下面的新新闻进行比对："
        else:
            prev_ctx = "\n这是今日首次分析，请建立基准观点。"

        prompt = f"""
        你是一位华尔街顶级风控官。
        {prev_ctx}

        【今日最新新闻流】：
        {latest_news}

        请输出中文简报（Markdown格式）：
        1. **🔄 观点变化**：(对比上次分析，市场情绪是变好了还是变坏了？)
        2. **🚨 核心风险更新**：(当前最大的雷是什么？)
        3. **💡 机构分歧**：(高盛 vs 大摩)
        4. **🐂 操作建议**：(针对SPY/QQQ的建议)
        """
        
        try:
            with st.spinner("AI 正在对比历史观点并分析新数据..."):
                client = OpenAI(api_key=api_key, base_url=BASE_URL)
                resp = client.chat.completions.create(
                    model=MODEL_NAME, messages=[{"role":"user", "content":prompt}])
                res_txt = resp.choices[0].message.content
                
                st.session_state['ai_history'].append({
                    'time': datetime.datetime.now().strftime('%H:%M'),
                    'content': res_txt
                })
                st.rerun()
        except Exception as e: st.error(str(e))

    # 显示最新报告
    if len(st.session_state['ai_history']) > 0:
        st.success(f"📊 最新分析 ({st.session_state['ai_history'][-1]['time']})")
        st.markdown(st.session_state['ai_history'][-1]['content'])
    else:
        st.info("👈 点击上方按钮，生成今日第一份风控报告")

with col_news:
    st.markdown("#### 📰 实时资讯流")
    with st.container(height=600):
        for n in all_news[:20]:
            label, color = analyze_sentiment_tag(n['t'])
            # 找回 v3.5 的详细时间戳显示
            st.markdown(f":{color}[**{label}**] {n['t']}")
            st.caption(f"🕒 {n['time_str']} | {n['s']} | [原文]({n['l']})")
            st.divider()

if refresh_rate: time.sleep(1)
