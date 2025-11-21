import streamlit as st
import yfinance as yf
import pandas as pd
import feedparser
from openai import OpenAI
import datetime
import time

# --- 1. 页面基础配置 ---
st.set_page_config(page_title="DeepSeek 智能风控仪表盘", layout="wide", page_icon="📊")

# --- 2. 侧边栏：全局控制 ---
st.sidebar.title("⚙️ 全局设置")

# A. 刷新频率设置
st.sidebar.subheader("⏱️ 刷新机制")
refresh_rate = st.sidebar.slider("自动刷新间隔 (分钟)", 5, 60, 30, help="为了节省 DeepSeek 费用，建议不要设置太频繁")
st.sidebar.caption(f"当前页面将每 {refresh_rate} 分钟尝试刷新一次数据。")

# B. DeepSeek 设置
st.sidebar.subheader("🤖 AI 模型配置")
api_key = st.sidebar.text_input("DeepSeek API Key", type="password", placeholder="sk-...", help="输入 Key 以启用 AI 研报分析")
MODEL_NAME = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"

st.sidebar.markdown("---")
st.sidebar.info("💡 **指标说明**：\n\n**RSI (相对强弱)**：\n- >70: 市场过热 (风险高)\n- <30: 市场超卖 (反弹机会)\n\n**VIX (恐慌)**：\n- >20: 恐慌情绪蔓延")

# --- 3. 核心逻辑函数 ---

# 计算 RSI 指标 (替代高盛指标，实现全自动)
def calculate_rsi(data, window=14):
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# 获取市场数据
@st.cache_data(ttl=300) # 缓存5分钟
def get_market_data():
    # 获取过去3个月的数据，用于画图
    tickers = yf.Tickers("^GSPC ^VIX ^TNX NVDA AAPL")
    hist = tickers.history(period="3mo")
    return hist

# --- 4. 主界面布局 ---

st.title("📊 华尔街风向标 (Trend & Risk)")
st.caption(f"最后更新时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

try:
    # 获取数据
    market_data = get_market_data()
    
    # 提取最新数据
    latest_spx = market_data['Close']['^GSPC'].iloc[-1]
    latest_vix = market_data['Close']['^VIX'].iloc[-1]
    latest_tnx = market_data['Close']['^TNX'].iloc[-1]
    
    # 计算 RSI (基于标普500)
    # 为了计算准确的RSI，我们需要单独提取SPX序列
    spx_only = yf.Ticker("^GSPC").history(period="6mo") # 取更长一点的时间确保RSI计算准确
    spx_rsi_series = calculate_rsi(spx_only)
    
    if len(spx_rsi_series) > 1:
        spx_rsi = spx_rsi_series.iloc[-1]
        prev_rsi = spx_rsi_series.iloc[-2]
        rsi_delta = spx_rsi - prev_rsi
    else:
        spx_rsi = 50.0
        rsi_delta = 0.0

    # --- 模块 A: 核心风控指标卡片 ---
    st.subheader("1. 核心风险仪表 (Risk Gauges)")
    
    c1, c2, c3, c4 = st.columns(4)
    
    # 卡片 1: 标普500
    if len(market_data['Close']['^GSPC']) > 1:
        spx_delta = latest_spx - market_data['Close']['^GSPC'].iloc[-2]
    else:
        spx_delta = 0
        
    c1.metric("📈 S&P 500", f"{latest_spx:.0f}", f"{spx_delta:.2f}")
    
    # 卡片 2: VIX 恐慌指数 (反向颜色)
    if len(market_data['Close']['^VIX']) > 1:
        vix_delta = latest_vix - market_data['Close']['^VIX'].iloc[-2]
    else:
        vix_delta = 0
    c2.metric("📉 VIX 恐慌指数", f"{latest_vix:.2f}", f"{vix_delta:.2f}", delta_color="inverse")
    
    # 卡片 3: 10年美债
    if len(market_data['Close']['^TNX']) > 1:
        tnx_delta = latest_tnx - market_data['Close']['^TNX'].iloc[-2]
    else:
        tnx_delta = 0
    c3.metric("⚖️ 10年美债", f"{latest_tnx:.2f}%", f"{tnx_delta:.2f}%", delta_color="inverse")
    
    # 卡片 4: 自动化的“牛熊指标” (RSI)
    # 动态判断风险颜色
    rsi_label = "中性 (Neutral)"
    if spx_rsi > 70:
        rsi_label = "🔴 极度贪婪 (风险高)"
    elif spx_rsi < 30:
        rsi_label = "🟢 极度恐慌 (机会)"
        
    c4.metric(f"🐂 RSI 情绪指标", f"{spx_rsi:.1f}", f"{rsi_delta:.1f}", delta_color="off", help="替代高盛指标：>70为超买风险，<30为超卖机会")
    if spx_rsi > 70:
        c4.error(rsi_label)
    elif spx_rsi < 30:
        c4.success(rsi_label)
    else:
        c4.info(rsi_label)

    st.markdown("---")

    # --- 模块 B: 趋势图表 (Trend Charts) ---
    st.subheader("2. 趋势透视 (Trend Analysis)")
    
    tab1, tab2, tab3 = st.tabs(["📉 VIX 恐慌趋势", "📈 大盘走势 (S&P 500)", "⚖️ 利率压制 (10年美债)"])
    
    with tab1:
        st.markdown("**VIX 恐慌指数走势 (越低越好)**")
        st.line_chart(market_data['Close']['^VIX'], color="#FF4B4B") # 红色示警
    
    with tab2:
        st.markdown("**标普500指数走势**")
        st.line_chart(market_data['Close']['^GSPC'], color="#00CC96") # 绿色代表上涨
        
    with tab3:
        st.markdown("**10年期美债收益率 (科技股杀手)**")
        st.area_chart(market_data['Close']['^TNX'], color="#FFAA00") # 黄色

except Exception as e:
    st.error(f"数据加载异常: {e}")

st.markdown("---")

# --- 模块 C: DeepSeek 智能总结 ---
st.subheader("3. 投行观点 AI 深度复盘")

# 定义新闻源
rss_feeds = {
    "Goldman Sachs": "https://news.google.com/rss/search?q=Goldman+Sachs+stock+market+outlook+when:7d&hl=en-US&gl=US&ceid=US:en",
    "Morgan Stanley": "https://news.google.com/rss/search?q=Morgan+Stanley+market+strategy+when:7d&hl=en-US&gl=US&ceid=US:en",
    "Market Risk": "https://news.google.com/rss/search?q=stock+market+risk+warning+when:3d&hl=en-US&gl=US&ceid=US:en"
}

col_news_1, col_news_2 = st.columns([1, 2])

with col_news_1:
    if st.button("🔄 立即分析 (Call AI)", type="primary"):
        if not api_key:
            st.warning("请先在左侧侧边栏输入 DeepSeek API Key")
        else:
            with st.spinner("正在读取新闻并生成研报..."):
                # 1. 抓取
                news_text = ""
                for src, url in rss_feeds.items():
                    try:
                        feed = feedparser.parse(url)
                        for entry in feed.entries[:3]:
                            news_text += f"- [{src}] {entry.title}\n"
                    except:
                        continue
                
                # 2. 分析
                try:
                    client = OpenAI(api_key=api_key, base_url=BASE_URL)
                    
                    # 这里就是之前报错的地方，请确保复制完整
                    prompt = f"""
                    作为顶级交易员，请根据以下新闻标题，分析当前美股的下行风险：
                    
                    新闻数据：
                    {news_text}
                    
                    请输出（中文）：
                    1. **多空力量对比**：(机构是更看多还是看空？)
                    2. **关键风险点**：(通胀？地缘？财报？)
                    3. **RSI与基本面结合建议**：(当前RSI为 {spx_rsi:.1f}，结合新闻，我该买入还是卖出？)
                    """
                    
                    response = client.chat.completions.create(
                        model=MODEL_NAME,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.3
                    )
                    st.session_state['ai_analysis'] = response.choices[0].message.content
                except Exception as e:
                    st.error(f"AI 思考失败: {e}")

    # 显示 AI 结果 (使用 Session State 保持结果不消失)
    if 'ai_analysis' in st.session_state:
        st.success("📊 AI 分析报告已生成")
        st.markdown(st.session_state['ai_analysis'])

with col_news_2:
    st.info("📰 **原始新闻流 (最近7天)**")
    for src, url in rss_feeds.items():
        try:
            f = feedparser.parse(url)
            for e in f.entries[:3]:
                st.text(f"• [{src}] {e.title}")
                st.caption(f"  {e.published} | [原文链接]({e.link})")
        except:
            st.text(f"• [{src}] 暂时无法获取")

# --- 自动刷新逻辑 ---
if st.sidebar.button("手动刷新页面数据"):
    st.rerun()