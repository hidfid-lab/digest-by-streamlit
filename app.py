import os
import streamlit as st
from google import genai
from google.genai.errors import ServerError, APIError

# 導入你原本的 API Key 讀取邏輯
KEYS_FILE = "keys.txt"
API_KEYS = []

if os.path.exists(KEYS_FILE):
    with open(KEYS_FILE, "r", encoding="utf-8") as f:
        API_KEYS = [line.strip() for line in f if line.strip() and not line.startswith("#")]

if not API_KEYS:
    ENV_KEYS = os.environ.get("GEMINI_API_KEYS", "")
    if ENV_KEYS:
        API_KEYS = [k.strip() for k in ENV_KEYS.split(",") if k.strip()]
    else:
        single_key = os.environ.get("GEMINI_API_KEY", "")
        if single_key:
            API_KEYS = [single_key]

# 讀取 Telegram 設定（可從環境變數或 Streamlit Secrets 讀取）
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# 支援從 Streamlit Cloud 的 Secrets 讀取
try:
    if "TELEGRAM_BOT_TOKEN" in st.secrets:
        TELEGRAM_BOT_TOKEN = st.secrets["TELEGRAM_BOT_TOKEN"]
    if "TELEGRAM_CHAT_ID" in st.secrets:
        TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
    if "GEMINI_API_KEYS" in st.secrets:
        secret_keys = st.secrets["GEMINI_API_KEYS"]
        API_KEYS = [k.strip() for k in secret_keys.split(",") if k.strip()]
except Exception:
    pass

def generate_with_key_rotation(prompt, video_url):
    if not API_KEYS:
        raise ValueError("未找到任何有效的 Gemini API Key！請檢查 keys.txt 或密鑰設定。")
    
    last_error = None
    for index, key in enumerate(API_KEYS):
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[video_url, prompt]
            )
            return response.text
        except (ServerError, APIError, Exception) as e:
            last_error = e
            continue
    raise Exception(f"所有 API Key 皆嘗試失敗，最後錯誤: {last_error}")

def send_telegram_message(message):
    import requests
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    response = requests.post(url, json=payload)
    return response.status_code == 200

# ====================
# Streamlit 網頁前端介面
# ====================
st.set_page_config(page_title="YouTube AI 摘要生成器", page_icon="🎬", layout="centered")

st.title("🎬 YouTube 影片 AI 智慧摘要")
st.write("貼上任意 YouTube 影片網址，即可一鍵生成結構化摘要，並可同步發送至 Telegram！")

with st.form("summary_form"):
    video_url = st.text_input("🔗 YouTube 影片網址", placeholder="https://www.youtube.com/watch?v=...")
    
    prompt_style = st.selectbox(
        "📝 選擇摘要風格/模板",
        [
            "深度政經/商業/科技分析（預設）",
            "搞笑短劇/人性諷刺風格"
        ]
    )
    
    send_to_tg = st.checkbox("📤 同步發送到 Telegram 頻道", value=True)
    
    submitted = st.form_submit_button("🚀 開始生成摘要")

if submitted:
    if not video_url:
        st.warning("⚠️ 請先輸入 YouTube 影片網址！")
    else:
        with st.spinner("⏳ 正在透過 Gemini 分析影片並生成摘要，請稍候..."):
            try:
                # 根據選擇的風格套用對應 Prompt
                if "搞笑短劇" in prompt_style:
                    prompt = f"""
                    請針對以下 YouTube 搞笑或情境短劇影片進行趣味與人性的深度剖析：
                    影片連結：{video_url}
                    
                    請嚴格依照下列三個區塊進行回覆，口吻需幽默、犀利且生活化，適合手機閱讀：
                    1. 一句話笑點與核心反轉：嚴格限制 30 個字以內，點出這部短片的戲劇張力或諷刺點。
                    2. 人性與社會諷刺：劇中角色反映了什麼樣的現代社會現象、職場生態或人性盲點？
                    3. 搞笑橋段與編劇邏輯：拆解其包袱、笑點鋪陳或出人意料的結局設計。
                    """
                    title_prefix = "搞笑短劇 AI 摘要"
                else:
                    prompt = f"""
                    請針對以下 YouTube 影片進行深度結構化重點萃取：
                    影片連結：{video_url}
                    
                    請嚴格依照下列三個區塊進行回覆，排版需簡潔清晰，適合手機閱讀：
                    1. 一句話結論：嚴格限制 30 個字以內，直接講出核心結論。
                    2. 全局觀測：本集最重要的核心命題與背景。
                    3. 關鍵拆解：針對核心技術、觀點或商業模式進行邏輯拆解。
                    4. 實踐視角：點出其中隱含的洞察與底層邏輯。
                    """
                    title_prefix = "YouTube 頻道 AI 自動摘要"

                # 呼叫 Gemini
                summary = generate_with_key_rotation(prompt, video_url)
                
                st.success("✅ 摘要生成完畢！")
                st.markdown("---")
                st.markdown(summary)
                st.markdown("---")
                
                # 發送到 Telegram
                if send_to_tg:
                    message_content = f"【{title_prefix}】\n連結：{video_url}\n\n{summary}"
                    success = send_telegram_message(message_content)
                    if success:
                        st.info("📨 已成功同步發送至 Telegram！")
                    else:
                        st.warning("⚠️ Telegram 發送失敗，請檢查 Token 與 Chat ID 設定。")
                        
            except Exception as e:
                st.error(f"❌ 發生錯誤：{e}")
