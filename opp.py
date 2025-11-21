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

# --- 2. 身份验证系统 (Gatekeeper) ---

def check_login():
    """简单的登录逻辑，读取 Secrets 中的用户列表"""
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['user_role'] = None
        st.session_state['username'] = None

    # 如果已登录，直接返回 True
    if st.session_state['logged_in']:
        return True

    # 登录界面
    st.markdown("## 🔒 华尔街风控系统 (专业版)")
    st.info("本系统仅限受邀用户使用。")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        username = st.text_input("账号 (Username)")
        password = st.text_input("密码 (Password)", type="password")
        
        if st.button("登录 / Login"):
            # 1. 检查管理员
            if username == st.secrets["admin"]["username"] and password == st.secrets["admin"]["password"]:
                st.session_state['logged_in'] = True
                st.session_state['user_role'] = "admin"
                st.session_state['username'] = username
                st.success("管理员登录成功！")
                time.sleep(1)
                st.rerun()
            
            # 2. 检查普通用户
            elif username in st.secrets["users"] and password == st.secrets["users"][username]:
                st.session_state['logged_in'] = True
                st.session_state['user_role'] = "user"
                st.session_state['username'] = username
                st.success(f"欢迎回来, {username}")
                time.sleep(1)
                st.rerun()
            else:
                st.error("账号或密码错误，请联系管理员开通。")
    
    return False

# 如果没登录，停止执行后面代码
if not check_login():
    st.stop()

# ============================================================
#  以下是登录后才能看到的内容 (Main App)
# ============================================================

# 获取 API Key
api_key = st.secrets["DEEPSEEK_API_KEY"]
MODEL_NAME = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"

# --- 侧边栏：用户信息 & 管理员面板 ---
st.sidebar.title("👤 用户中心")
st.sidebar.write(f"当前用户: **{st.session_state['username']}**")

if st.sidebar.button("退出登录 (Logout)"):
    st.session_state['logged_in'] = False
    st.rerun()

# 管理员专属：用量监控面板
if st.session_state['user_role'] == "admin":
    st.sidebar.markdown("---")
    st.sidebar.subheader("🛠️ 管理员监控")
    st.sidebar.info("💡 用量日志请在 Streamlit Cloud 后台点击 'Manage app' -> 'Logs' 查看详细记录。")
    st.sidebar.markdown("**已开通用户列表:**")
    for u in st.secrets["users"]:
        st.sidebar.text(f"- {u}")

st.sidebar.markdown("---")

# --- 原有功能区 ---
st.sidebar.subheader("⏱️ 刷新设置")
if st.sidebar.button("🔄 立即刷新数据", type="primary"):
    st.rerun()
refresh_rate = st.sidebar.slider("自动刷新 (分钟)", 5, 60, 30)

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

@st.cache_data(ttl=300)
def get_market_data():
    return yf.Tickers("SPY QQQ IEF").history(period="3mo")

# --- 主界面 ---
st.title("🦈 华尔街风控系统 (Enterprise)")
st.caption(f"更新时间: {datetime.datetime.now().strftime('%H:%M:%S')}")

try:
    market_data = get_market_data()
    spy = market_data['Close']['SPY'].dropna()
    qqq = market_data['Close']['QQQ'].dropna()
    ief = market_data['Close']['IEF'].dropna()
    
    cnn_score, cnn_src = get_cnn_fear_greed_index()
    if cnn_score is None:
        delta = spy.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        cnn_score = 100 - (100 / (1 + rs)).iloc[-1]
        cnn_src = "RSI 模拟"

    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("核心资产")
        m1, m2, m3 = st.columns(3)
        m1.metric("标普500", f"${spy.iloc[-1]:.1f}", f"{spy.iloc[-1]-spy.iloc[-2]:.2f}")
        m2.metric("纳指QQQ", f"${qqq.iloc[-1]:.1f}", f"{qqq.iloc[-1]-qqq.iloc[-2]:.2f}")
        m3.metric("国债IEF", f"${ief.iloc[-1]:.1f}", f"{ief.iloc[-1]-ief.iloc[-2]:.2f}")
        st.line_chart(pd.DataFrame({'SPY': spy, 'QQQ': qqq}), height=200)
    with c2:
        st.plotly_chart(plot_gauge(cnn_score, cnn_src), use_container_width=True)

except Exception as e: st.error(f"数据错误: {e}")

# --- AI 模块 (带审计日志) ---
st.markdown("---")
st.subheader("DeepSeek 智能研报")

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
            all_news.append({"s": src, "t": e.title, "l": e.link, "ts": ts})
    except: pass
all_news.sort(key=lambda x: x['ts'], reverse=True)

if 'ai_history' not in st.session_state: st.session_state['ai_history'] = []

col_ai, col_news = st.columns([1, 1.5])

with col_ai:
    # 历史记录
    if len(st.session_state['ai_history']) > 0:
        with st.expander("📜 历史记录"):
            for report in reversed(st.session_state['ai_history']):
                st.caption(f"{report['time']}")
                st.markdown(report['content'])
                st.divider()

    # 生成按钮
    if st.button("⚡ 生成最新研报", type="primary"):
        # 【关键】记录谁点击了按钮
        user = st.session_state['username']
        print(f"[AUDIT LOG] User '{user}' requested AI analysis at {datetime.datetime.now()}")
        
        # 准备上下文
        latest_news = "\n".join([f"- [{n['s']}] {n['t']}" for n in all_news[:10]])
        prev_ctx = ""
        if len(st.session_state['ai_history']) > 0:
            prev_ctx = f"\n旧观点参考：\n{st.session_state['ai_history'][-1]['content']}\n"
            
        prompt = f"我是风控官，参考旧观点(如有)：{prev_ctx}\n分析新数据：\n{latest_news}\n输出中文简报：1.观点变化 2.风险 3.建议"
        
        try:
            with st.spinner("AI 思考中..."):
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

    if len(st.session_state['ai_history']) > 0:
        st.success(f"📊 最新分析")
        st.markdown(st.session_state['ai_history'][-1]['content'])

with col_news:
    st.markdown("#### 📰 资讯流")
    with st.container(height=600):
        for n in all_news[:20]:
            label, color = analyze_sentiment_tag(n['t'])
            st.markdown(f":{color}[**{label}**] {n['t']}")
            st.caption(f"{n['s']} | [原文]({n['l']})")
            st.divider()
