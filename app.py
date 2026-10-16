import os
import re
import requests
import streamlit as st
from google import genai
from google.genai import types

# ==========================================
# ⚙️ 基本設定
# ==========================================
st.set_page_config(page_title="YouTube 影片 AI 摘要", page_icon="🎬", layout="centered")

KEYS_FILE = "keys.txt"
MODEL_OPTIONS = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]

# ==========================================
# 🧠 Prompt 模式（沿用排程腳本的內容，可自行增修）
# ==========================================
PROMPTS = {
    "📈 政經 / 科技 / 投資（預設）": """
請針對以下 YouTube 影片進行深度結構化重點萃取：
影片標題：{title}
影片連結：{url}

請嚴格依照下列四個區塊進行回覆，排版需簡潔清晰，適合手機閱讀：
1. 一句話結論：嚴格限制 30 個字以內，直接講出核心結論。
2. 全局觀測：本集最重要的國際政經趨勢與核心命題。
3. 關鍵拆解：針對科技創新、AI 應用、地緣政治或商業模式進行邏輯拆解。
4. 實踐視角：結合 FIRE 族與投資視角，點出其中隱含的商業機會與底層邏輯。
""",
    "😂 搞笑 / 情境短劇": """
請針對以下 YouTube 搞笑或情境短劇影片進行趣味與人性的深度剖析：
影片標題：{title}
影片連結：{url}

請嚴格依照下列三個區塊進行回覆，口吻需幽默、犀利且生活化，適合手機閱讀：
1. 一句話笑點與核心反轉：嚴格限制 30 個字以內，點出這部短片的戲劇張力或諷刺點。
2. 人性與社會諷刺：劇中角色反映了什麼樣的現代社會現象、職場生態或人性盲點？
3. 搞笑橋段與編劇邏輯：拆解其包袱、笑點鋪陳或出人意料的結局設計。
""",
    "✍️ 自訂 Prompt": "",
}

# 頻道預設標題（傳 Telegram 用）
TELEGRAM_TITLE_DEFAULT = "單支影片 AI 摘要"


# ==========================================
# 🔑 讀取 API Key（keys.txt → st.secrets → 環境變數）
# ==========================================
def load_api_keys():
    keys = []
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE, "r", encoding="utf-8") as f:
            keys = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    if not keys:
        raw = st.secrets.get("GEMINI_API_KEYS", "") if hasattr(st, "secrets") else ""
        raw = raw or os.environ.get("GEMINI_API_KEYS", "")
        keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        single = st.secrets.get("GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
        if single:
            keys = [single]
    return keys


def get_secret(name):
    try:
        val = st.secrets.get(name)
    except Exception:
        val = None
    return val or os.environ.get(name)


# ==========================================
# 🔗 URL 處理：從分享文字中抓出 YouTube 連結並標準化
# ==========================================
YT_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?"
    r"(?:youtube\.com/(?:watch\?[^\s]*?v=|shorts/|live/|embed/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)


def extract_video_url(text):
    """從任意貼上的文字（含手機『分享』的標題+連結）找出影片 ID，回傳標準網址。"""
    if not text:
        return None
    m = YT_PATTERN.search(text)
    if not m:
        return None
    return f"https://www.youtube.com/watch?v={m.group(1)}"


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_video_meta(url):
    """用 YouTube oEmbed 取得標題與頻道名（不需 API Key、速度快）。"""
    try:
        r = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": url, "format": "json"},
            timeout=10,
        )
        if r.status_code == 200:
            d = r.json()
            return d.get("title", ""), d.get("author_name", ""), d.get("thumbnail_url", "")
    except Exception:
        pass
    return "", "", ""


# ==========================================
# 🤖 Gemini 呼叫（Key 輪替）
# ==========================================
def generate_with_key_rotation(api_keys, model, prompt, video_url, log):
    last_error = None
    for i, key in enumerate(api_keys, 1):
        try:
            log(f"嘗試第 {i} / {len(api_keys)} 組 API Key…")
            client = genai.Client(api_key=key)
            try:
                # 以 file_data 方式讓 Gemini 真正讀取影片內容
                contents = types.Content(
                    parts=[
                        types.Part(file_data=types.FileData(file_uri=video_url)),
                        types.Part(text=prompt),
                    ]
                )
                resp = client.models.generate_content(model=model, contents=contents)
            except Exception as inner:
                # 退回與排程腳本相同的寫法
                log(f"影片直讀失敗（{str(inner)[:60]}），改用純連結模式…")
                resp = client.models.generate_content(model=model, contents=[video_url, prompt])
            log(f"第 {i} 組成功 ✅")
            return resp.text
        except Exception as e:
            log(f"第 {i} 組失敗：{str(e)[:120]}")
            last_error = e
    raise RuntimeError(f"所有 API Key 皆失敗，最後錯誤：{last_error}")


# ==========================================
# ✈️ Telegram
# ==========================================
def send_telegram(message):
    token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False, "未設定 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID"
    api = f"https://api.telegram.org/bot{token}/sendMessage"
    # Telegram 單則上限 4096 字，超過就切段
    chunks = [message[i : i + 4000] for i in range(0, len(message), 4000)]
    for c in chunks:
        r = requests.post(api, json={"chat_id": chat_id, "text": c}, timeout=15)
        if r.status_code != 200:
            return False, r.text
    return True, "OK"


# ==========================================
# 🖥️ UI
# ==========================================
st.title("🎬 YouTube 影片 AI 摘要")
st.caption("貼上（或分享）任一支影片連結，直接生成結構化摘要。")

api_keys = load_api_keys()

with st.sidebar:
    st.header("設定")
    model = st.selectbox("Gemini 模型", MODEL_OPTIONS, index=0)
    mode = st.radio("摘要模式", list(PROMPTS.keys()))
    tg_title = st.text_input("Telegram 標題", value=TELEGRAM_TITLE_DEFAULT)
    st.divider()
    if api_keys:
        st.success(f"已載入 {len(api_keys)} 組 Gemini API Key")
    else:
        st.error("找不到 Gemini API Key（keys.txt / secrets / 環境變數）")
        manual = st.text_input("或在此臨時輸入 Key", type="password")
        if manual.strip():
            api_keys = [manual.strip()]

# 支援網址參數：https://你的app.streamlit.app/?url=<影片連結>
prefill = st.query_params.get("url", "")
raw_input = st.text_area(
    "影片連結（可直接貼上手機『分享』的整段文字）",
    value=prefill,
    height=90,
    placeholder="https://youtu.be/xxxxxxxxxxx",
)

video_url = extract_video_url(raw_input)
title = author = thumb = ""

if raw_input.strip() and not video_url:
    st.warning("看不到有效的 YouTube 連結，請再確認。")

if video_url:
    title, author, thumb = fetch_video_meta(video_url)
    c1, c2 = st.columns([1, 2])
    with c1:
        if thumb:
            st.image(thumb, use_container_width=True)
    with c2:
        title = st.text_input("影片標題（可修改）", value=title)
        if author:
            st.caption(f"頻道：{author}")
        st.caption(video_url)

custom_prompt = ""
if mode == "✍️ 自訂 Prompt":
    custom_prompt = st.text_area(
        "自訂 Prompt（可用 {title}、{url} 變數）",
        value="請用繁體中文，條列出這支影片的重點與可執行的行動建議。\n影片標題：{title}\n影片連結：{url}",
        height=160,
    )

auto_tg = st.checkbox("生成後自動傳送到 Telegram", value=False)

if st.button("🚀 生成摘要", type="primary", disabled=not (video_url and api_keys), use_container_width=True):
    template = custom_prompt if mode == "✍️ 自訂 Prompt" else PROMPTS[mode]
    prompt = template.format(title=title or "未知標題", url=video_url)

    logs = []
    with st.status("Gemini 分析中…", expanded=True) as status:
        def log(msg):
            logs.append(msg)
            st.write(msg)

        try:
            summary = generate_with_key_rotation(api_keys, model, prompt, video_url, log)
            status.update(label="摘要完成！", state="complete", expanded=False)
            st.session_state["result"] = {
                "title": title,
                "url": video_url,
                "author": author,
                "summary": summary,
            }
            st.session_state.setdefault("history", []).insert(0, st.session_state["result"])

            if auto_tg:
                msg = f"【{tg_title}】\n標題：{title}\n連結：{video_url}\n\n{summary}"
                ok, info = send_telegram(msg)
                st.toast("已傳送到 Telegram ✅" if ok else f"Telegram 失敗：{info}")
        except Exception as e:
            status.update(label="生成失敗", state="error")
            st.error(str(e))

# ---------- 結果顯示 ----------
res = st.session_state.get("result")
if res:
    st.divider()
    st.subheader(res["title"] or "摘要結果")
    st.caption(res["url"])
    st.markdown(res["summary"])

    full_text = f"標題：{res['title']}\n連結：{res['url']}\n\n{res['summary']}"
    b1, b2 = st.columns(2)
    with b1:
        if st.button("✈️ 傳送到 Telegram", use_container_width=True):
            ok, info = send_telegram(f"【{tg_title}】\n{full_text}")
            st.success("已傳送！") if ok else st.error(f"失敗：{info}")
    with b2:
        st.download_button(
            "💾 下載 .txt", full_text, file_name="summary.txt", use_container_width=True
        )
    with st.expander("📋 複製用純文字"):
        st.code(full_text, language=None)

# ---------- 本次歷史 ----------
hist = st.session_state.get("history", [])
if len(hist) > 1:
    with st.expander(f"本次操作歷史（{len(hist)}）"):
        for h in hist[1:]:
            st.markdown(f"**{h['title'] or h['url']}**")
            st.caption(h["url"])
            st.markdown(h["summary"])
            st.divider()
