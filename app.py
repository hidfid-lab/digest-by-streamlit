import os
import streamlit as st
import requests
from yt_dlp import YoutubeDL
from google import genai
from google.genai.errors import ServerError, APIError

# ==========================================
# 🎨 頁面基本設定
# ==========================================
st.set_page_config(
    page_title="YouTube AI 智慧摘要生成器",
    page_icon="🎬",
    layout="centered"
)

st.title("🎬 YouTube 影片 AI 智慧摘要生成器")
st.markdown("貼上任意 YouTube 影片網址，系統將自動擷取真實標題與連結，透過 Gemini AI 快速萃取重點，並一鍵推送到 Telegram！")

# ==========================================
# 🔑 API Key 與 Telegram 設定 (支援 Streamlit Secrets 或 環境變數)
# ==========================================
def get_api_keys():
    try:
        if "GEMINI_API_KEYS" in st.secrets:
            keys = st.secrets["GEMINI_API_KEYS"]
            if isinstance(keys, str):
                return [k.strip() for k in keys.split(",") if k.strip()]
            elif isinstance(keys, list):
                return keys
    except Exception:
        pass
    
    env_keys = os.environ.get("GEMINI_API_KEYS", "")
    if env_keys:
        return [k.strip() for k in env_keys.split(",") if k.strip()]
    
    single_key = os.environ.get("GEMINI_API_KEY", "")
    if single_key:
        return [single_key]
        
    return []

API_KEYS = get_api_keys()

# ==========================================
# 🔍 透過 yt-dlp 快速取得影片標題與清理網址
# ==========================================
def get_video_info(video_url):
    ydl_opts = {
        "socket_timeout": 10,
        "retries": 1,
        "extractor_retries": 1,
        "fragment_retries": 1,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            title = info.get("title", "未知標題")
            video_id = info.get("id")
            if video_id:
                clean_url = f"https://www.youtube.com/watch?v={video_id}"
            else:
                clean_url = video_url
            return clean_url, title
    except Exception as e:
        return video_url, f"無法自動取得標題 ({str(e)})"

# ==========================================
# 🤖 Gemini 核心生成函數 (支援 Key 輪替與模型設定)
# ==========================================
def generate_with_key_rotation(prompt, video_url):
    if not API_KEYS:
        raise ValueError("未找到任何有效的 Gemini API Key！請在 Streamlit Secrets 中設定 GEMINI_API_KEYS。")
    
    last_error = None
    for index, key in enumerate(API_KEYS):
        try:
            print(f"正在嘗試使用第 {index + 1} 組 Gemini API Key...")
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[video_url, prompt]
            )
            print(f"第 {index + 1} 組 API Key 呼叫成功！")
            return response.text
        except (ServerError, APIError, Exception) as e:
            print(f"⚠️ 第 {index + 1} 組失敗 ({e})，切換下一組...")
            last_error = e
            continue
    raise Exception(f"所有 API Key 皆嘗試失敗，最後錯誤: {last_error}")

# ==========================================
# ✈️ Telegram 發送函數
# ==========================================
def send_telegram_message(message):
    try:
        bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
    except Exception:
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        return False, "未設定 Telegram Bot Token 或 Chat ID"
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        return True, "發送成功"
    else:
        return False, f"發送失敗: {response.text}"

# ==========================================
# 🖥️ 使用者介面設計 (UI)
# ==========================================
with st.form("summary_form"):
    input_url = st.text_input("🔗 請輸入 YouTube 影片網址", placeholder="https://www.youtube.com/watch?v=...")
    
    style_option = st.selectbox(
        "💡 選擇摘要風格與模板",
        [
            "政經/財經/知識型結構化摘要 (預設)",
            "搞笑/情境短劇趣味剖析",
            "簡明扼要重點摘要"
        ]
    )
    
    submitted = st.form_submit_button("✨ 開始生成摘要並發送")

if submitted:
    if not input_url:
        st.warning("⚠️ 請先輸入有效的 YouTube 影片網址！")
    elif not API_KEYS:
        st.error("❌ 系統未偵測到 Gemini API Key，請先至 Streamlit Secrets 設定。")
    else:
        # 1. 模擬原本腳本：先檢查與取得標題
        with st.spinner("🔄 正在快速檢查 YouTube 影片資訊..."):
            url, title = get_video_info(input_url)
            
        # 清楚印出影片標題與連結（符合你的要求）
        st.success("✅ 成功鎖定影片！")
        st.markdown(f"📌 **影片標題**：{title}")
        st.markdown(f"🔗 **影片連結**：[{url}]({url})")

        # 2. 根據風格套用對應的 Prompt 結構
        if "搞笑" in style_option:
            prompt = f"""
            請針對以下 YouTube 搞笑或情境短劇影片進行趣味與人性的深度剖析：
            影片標題：{title}
            影片連結：{url}
            
            請嚴格依照下列三個區塊進行回覆，口吻需幽默、犀利且生活化，適合手機閱讀：
            1. 一句話笑點與核心反轉：嚴格限制 30 個字以內，點出這部短片的戲劇張力或諷刺點。
            2. 人性與社會諷刺：劇中角色反映了什麼樣的現代理象、職場生態或人性盲點？
            3. 搞笑橋段與編劇邏輯：拆解其包袱、笑點鋪陳或出人意料的結局設計。
            """
            telegram_title = "YouTube 搞笑短片 AI 趣味剖析"
        elif "簡明" in style_option:
            prompt = f"""
            請針對以下 YouTube 影片進行簡明扼要的重點萃取：
            影片標題：{title}
            影片連結：{url}
            
            請提供：
            1. 核心一句話總結 (30字內)
            2. 3-5 點重要收穫與精華
            """
            telegram_title = "YouTube 影片快篩摘要"
        else:
            prompt = f"""
            請針對以下 YouTube 影片進行深度結構化重點萃取：
            影片標題：{title}
            影片連結：{url}
            
            請嚴格依照下列三個區塊進行回覆，排版需簡潔清晰，適合手機閱讀：
            1. 一句話結論：嚴格限制 30 個字以內，直接講出核心結論。
            2. 全局觀測：本集最重要的國際政經趨勢與核心命題。
            3. 關鍵拆解：針對科技創新、AI 應用、地緣政治或商業模式進行邏輯拆解。
            4. 實踐視角：結合 FIRE 族與投資視角，點出其中隱含的商業機會與底層邏輯。
            """
            telegram_title = "YouTube 深度知識 AI 自動摘要"

        # 3. 呼叫 Gemini 生成摘要
        with st.spinner("🤖 正在呼叫 Gemini 生成全新影片摘要..."):
            try:
                summary = generate_with_key_rotation(prompt, url)
                
                st.markdown("---")
                st.markdown("### 📋 摘要內容預覽")
                st.markdown(summary)
                
                # 4. 同步發送到 Telegram
                with st.spinner("✈️ 正在發送 Telegram 通知..."):
                    message_content = f"【{telegram_title}】\n標題：{title}\n連結：{url}\n\n{summary}"
                    success = send_telegram_message(message_content)
                    
                    if success:
                        st.success("✅ Telegram 訊息發送成功！")
                    else:
                        st.error("❌ Telegram 發送失敗，請檢查 Bot Token 與 Chat ID。")

            except Exception as e:
                st.error(f"❌ 發生錯誤：{str(e)}")
