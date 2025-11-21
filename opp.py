import streamlit as st
import yfinance as yf
import pandas as pd
import feedparser
from openai import OpenAI
import datetime

# --- 1. 页面基础配置 ---
st.set_page_config(page_title="DeepSeek 智能风控仪表盘", layout="wide", page_icon="🦈")

# --- 2. 侧边栏 ---
st.sidebar.title("⚙️ 设置")
st.sidebar.info("ℹ️ 云端优化模式：已启用 ETF 数据源 (SPY/IEF) 以绕过云端拦截。")
api_key = st.sidebar.text_input("DeepSeek API Key", type="password", placeholder="sk-...")
MODEL_NAME = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
refresh_rate = st.sidebar.slider("刷新频率", 15, 60, 30)

# --- 3. 核心逻辑函数 (云端优化版) ---

def calculate_rsi(data, window=14):
    try:
        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    except:
        return pd.Series([50]*len(data))

@st.cache_data(ttl=300)
def get_market_data():
    # 【关键修改】
    # ^GSPC (容易被封) -> SPY (标普500 ETF, 极稳)
    # ^TNX (容易被封)  -> IEF (7-10年国债 ETF, 价格与利率反向)
    # ^VIX (偶尔被封)  -> VIXY (短期恐慌指数 ETF)
    tickers = yf.Tickers("SPY IEF VIXY NVDA") 
    hist = tickers.history(period="3mo")
    return hist

# --- 4. 主界面 ---
st.title("🦈 华尔街风向标 (Cloud Stable Ver.)")
st.caption(f"更新时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

try:
    market_data = get_market_data()
    
    # 辅助函数：安全获取数据，防止NaN报错
    def safe_metric(ticker_symbol):
        try:
            s = market_data['Close'][ticker_symbol].dropna()
            if len(s) < 2: return 0, 0
            val = s.iloc[-1]
            chg = val - s.iloc[-2]
            return val, chg
        except:
            return 0, 0

    # 获取数据
    spy_val, spy_chg = safe_metric("SPY")     # 标普500 ETF
    ief_val, ief_chg = safe_metric("IEF")     # 美债 ETF (价格)
    vix_val, vix_chg = safe_metric("VIXY")    # 恐慌 ETF
    
    # 计算 RSI
    try:
        spy_data = market_data.xs('SPY', level=1, axis=1) if isinstance(market_data.columns, pd.MultiIndex) else market_data
        rsi_val = calculate_rsi(spy_data).iloc[-1]
        rsi_prev = calculate_rsi(spy_data).iloc[-2]
        rsi_delta = rsi_val - rsi_prev
    except:
        rsi_val, rsi_delta = 50.0, 0.0

    # --- 模块 A: 仪表盘 ---
    st.subheader("1. 市场核心指标 (ETF源)")
    c1, c2, c3, c4 = st.columns(4)

    # 卡片1: 标普500 (SPY)
    c1.metric("📈 标普500 (SPY)", f"${spy_val:.2f}", f"{spy_chg:.2f}")

    # 卡片2: 恐慌指数 (VIXY)
    # VIXY 是 ETF，价格大约在 10-20 之间，和 VIX 指数数值不同，但趋势一致
    c2.metric("📉 恐慌 ETF (VIXY)", f"${vix_val:.2f}", f"{vix_chg:.2f}", delta_color="inverse", help="VIXY 上涨代表恐慌增加")

    # 卡片3: 美债压力 (IEF)
    # ⚠️ 逻辑转换：IEF 是债券价格。
    # 价格跌 = 利率涨 (对股市不好) -> 显示为红色(inverse)
    # 价格涨 = 利率跌 (对股市好)   -> 显示为绿色
    c3.metric("⚖️ 国债价格 (IEF)", f"${ief_val:.2f}", f"{ief_chg:.2f}", delta_color="normal", help="注意：这是债券价格。价格下跌(红色)意味着市场利率在上升(风险增加)。")

    # 卡片4: RSI
    rsi_label = "中性"
    if rsi_val > 70: rsi_label = "🔴 过热风险"
    elif rsi_val < 30: rsi_label = "🟢 超卖机会"
    
    c4.metric("🐂 RSI 情绪", f"{rsi_val:.1f}", f"{rsi_delta:.1f}", delta_color="off")
    if rsi_val > 70: c4.error(rsi_label)
    elif rsi_val < 30: c4.success(rsi_label)
    else: c4.info(rsi_label)

    st.markdown("---")
    
    # --- 模块 B: 趋势图 (已修正为 ETF) ---
    st.subheader("2. 趋势透视")
    t1, t2, t3 = st.tabs(["S&P 500 (SPY)", "恐慌趋势 (VIXY)", "利率压力 (IEF)"])
    
    with t1:
        st.line_chart(market_data['Close']['SPY'], color="#00CC96")
    with t2:
        st.area_chart(market_data['Close']['VIXY'], color="#FF4B4B")
    with t3:
        st.caption("👇 注意：曲线向下代表利率上升（压力变大）")
        st.line_chart(market_data['Close']['IEF'], color="#FFAA00")

except Exception as e:
    st.error(f"云端数据连接暂时不稳定，请稍后刷新。错误信息: {e}")

# --- 模块 C: AI 分析 (保持不变) ---
st.subheader("3. DeepSeek 研报分析")
# ... (这里保持你原有的 AI 代码即可，不需要改动) ...
# 为了完整性，这里补上 AI 部分的简易版:
rss_feeds = {
    "Goldman": "https://news.google.com/rss/search?q=Goldman+Sachs+outlook+when:7d&hl=en-US&gl=US&ceid=US:en",
    "Morgan": "https://news.google.com/rss/search?q=Morgan+Stanley+market+outlook+when:7d&hl=en-US&gl=US&ceid=US:en"
}

col_news_1, col_news_2 = st.columns([1, 2])
with col_news_1:
    if st.button("🔄 生成分析报告"):
        if not api_key:
            st.warning("请输入 API Key")
        else:
            with st.spinner("AI 正在分析..."):
                news_text = ""
                for src, url in rss_feeds.items():
                    try:
                        f = feedparser.parse(url)
                        for e in f.entries[:2]: news_text += f"- {e.title}\n"
                    except: pass
                
                try:
                    client = OpenAI(api_key=api_key, base_url=BASE_URL)
                    resp = client.chat.completions.create(
                        model=MODEL_NAME,
                        messages=[{"role":"user", "content":f"分析以下美股新闻风险:\n{news_text}"}]
                    )
                    st.success("分析完成")
                    st.markdown(resp.choices[0].message.content)
                except Exception as e: st.error(str(e))

with col_news_2:
    st.caption("新闻源数据流 (Raw)")
    for src, url in rss_feeds.items():
        try:
            f = feedparser.parse(url)
            for e in f.entries[:2]: st.text(f"• {e.title}")
        except: pass
