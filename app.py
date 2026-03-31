import io
import json
import os
import re
import tempfile
from typing import List, Optional

import cv2
import google.generativeai as genai
import requests
import streamlit as st
from PIL import Image

# ─── CONFIG ───────────────────────────────────────────────────────────────────
GOOGLE_API_KEY = "AIzaSyDhiVndg_t2pp0hO2vEkjVEdPA7LxIsL1Q"
MODEL_NAME     = "models/gemini-2.5-flash"
FALLBACK_MODEL = "models/gemini-1.5-flash"

FORENSICS_PROMPT = """You are a digital forensics and psychological analysis AI.
Analyze this media and the accompanying social media caption.
Are there signs of AI generation in the pixels, or is this a "cheap fake"
(a real image used with a misleading, out-of-context caption)?
Return ONLY a JSON object with exactly four keys:
  authenticity_score (0-100),
  misinformation_risk (0-100),
  psychological_manipulation_score (0-100),
  explanation (2-sentence string).
No markdown, no extra text — raw JSON only."""

LINK_PROMPT = """You are a fact-checking and digital forensics AI.
A user has shared the following social media post URL and its scraped content.
Analyze the post text, title, and description for:
- Signs of misinformation or out-of-context framing
- Psychological manipulation techniques
- Credibility signals (sources cited, emotional language, sensationalism)
Return ONLY a JSON object with exactly four keys:
  authenticity_score (0-100, how credible/authentic this post seems),
  misinformation_risk (0-100, how likely it contains false info),
  psychological_manipulation_score (0-100, manipulation tactics used),
  explanation (2-sentence string summarising your verdict).
No markdown, no extra text — raw JSON only."""

# ─── PAGE ─────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Tattva", layout="wide", page_icon="🛡️")
genai.configure(api_key=GOOGLE_API_KEY)

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=Space+Mono:wght@400;700&display=swap');

*, *::before, *::after { box-sizing: border-box; }

#MainMenu, footer, header { visibility: hidden; }

html, body, [data-testid="stAppViewContainer"] {
    background: #04080f !important;
    color: #e2e8f0;
    font-family: 'Syne', sans-serif;
}

[data-testid="stAppViewContainer"]::before {
    content: '';
    position: fixed; inset: 0;
    background:
        radial-gradient(ellipse 70% 45% at 15% -5%, #002a2288 0%, transparent 55%),
        radial-gradient(ellipse 55% 35% at 85% 105%, #1a003355 0%, transparent 55%);
    pointer-events: none; z-index: 0;
}

.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 3rem !important;
    max-width: 960px !important;
    position: relative; z-index: 1;
}

/* ── HEADER ── */
.tattva-header { text-align: center; padding: 2rem 0 0.5rem; }
.tattva-eyebrow {
    font-family: 'Space Mono', monospace;
    font-size: .65rem; letter-spacing: .4em;
    color: #00ffe0; text-transform: uppercase; margin-bottom: .8rem;
}
.tattva-logo {
    font-family: 'Syne', sans-serif;
    font-size: clamp(3.5rem, 9vw, 6rem);
    font-weight: 800; letter-spacing: -.04em; line-height: 1;
    color: #f1f5f9; display: inline-block;
}
.tattva-logo .accent {
    background: linear-gradient(90deg, #00ffe0 0%, #7c6fff 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
}
.tattva-sub {
    color: #334155; font-size: .9rem;
    letter-spacing: .06em; margin-top: .6rem;
}
.tattva-rule {
    width: 48px; height: 2px; margin: 1.4rem auto 1.8rem;
    background: linear-gradient(90deg, #00ffe0, #7c6fff);
    border-radius: 2px;
}

/* ── TABS ── */
.stTabs [data-baseweb="tab-list"] {
    background: #0a1120 !important;
    border: 1px solid #0f2030 !important;
    border-radius: 12px !important;
    padding: 4px !important; gap: 4px !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    border-radius: 8px !important;
    color: #334155 !important;
    font-family: 'Space Mono', monospace !important;
    font-size: .7rem !important; letter-spacing: .12em !important;
    padding: 10px 18px !important; border: none !important;
    transition: color .2s !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #001f1a 0%, #0e0820 100%) !important;
    color: #00ffe0 !important;
    box-shadow: inset 0 0 0 1px #00ffe022 !important;
}
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] { display: none !important; }

/* ── FILE UPLOADER ── */
[data-testid="stFileUploader"] section {
    border: 1px dashed #0f2a22 !important;
    border-radius: 14px !important;
    background: #060d1a !important;
    transition: border-color .3s !important;
}
[data-testid="stFileUploader"] section:hover {
    border-color: #00ffe044 !important;
}

/* ── INPUTS ── */
.stTextInput input, .stTextArea textarea {
    background: #060d1a !important;
    border: 1px solid #0f2030 !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
    font-family: 'Space Mono', monospace !important;
    font-size: .8rem !important;
    transition: border-color .2s !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: #00ffe044 !important;
    box-shadow: 0 0 0 3px #00ffe00a !important;
}
.stTextArea textarea { padding: 14px 16px !important; }

/* ── BUTTON ── */
.stButton > button[kind="primary"] {
    background: linear-gradient(90deg, #003d35, #200a40) !important;
    border: 1px solid #00ffe033 !important;
    color: #00ffe0 !important;
    font-family: 'Space Mono', monospace !important;
    font-size: .75rem !important;
    letter-spacing: .15em !important;
    font-weight: 700 !important;
    padding: .75rem 1.5rem !important;
    border-radius: 10px !important;
    text-transform: uppercase !important;
    transition: box-shadow .2s, border-color .2s !important;
}
.stButton > button[kind="primary"]:hover {
    border-color: #00ffe077 !important;
    box-shadow: 0 0 20px #00ffe022 !important;
}

/* ── METRICS ── */
div[data-testid="stMetric"] {
    background: #060d1a !important;
    border: 1px solid #0f2030 !important;
    border-radius: 14px !important;
    padding: 1.2rem 1.2rem !important;
}
div[data-testid="stMetric"] label { color: #334155 !important; font-family: 'Space Mono', monospace !important; font-size: .65rem !important; letter-spacing: .1em !important; }
div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #e2e8f0 !important; font-family: 'Syne', sans-serif !important; font-size: 1.8rem !important; font-weight: 800 !important; }

/* ── PROGRESS ── */
.stProgress > div > div > div {
    background: linear-gradient(90deg, #00ffe0, #7c6fff) !important;
    border-radius: 4px !important;
}
.stProgress > div > div {
    background: #0a1120 !important;
    border-radius: 4px !important;
}

/* ── ALERTS ── */
.stSuccess, .stWarning, .stError {
    border-radius: 12px !important;
    font-family: 'Syne', sans-serif !important;
}

/* ── SPINNER ── */
.stSpinner > div { border-top-color: #00ffe0 !important; }

/* ── LABELS ── */
label[data-testid="stWidgetLabel"] p {
    color: #334155 !important;
    font-family: 'Space Mono', monospace !important;
    font-size: .7rem !important;
    letter-spacing: .1em !important;
}

/* ── SECTION HEADER ── */
.section-label {
    font-family: 'Space Mono', monospace;
    font-size: .65rem; letter-spacing: .3em;
    color: #00ffe0; text-transform: uppercase;
    margin: 1.4rem 0 .6rem;
}
.result-card {
    background: #060d1a;
    border: 1px solid #0f2030;
    border-radius: 14px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1rem;
}
</style>
""", unsafe_allow_html=True)


# ─── HELPERS ──────────────────────────────────────────────────────────────────
def parse_forensics_json(raw_text: str) -> Optional[dict]:
    if not raw_text:
        return None
    text = raw_text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e > s:
            try: data = json.loads(text[s:e+1])
            except: return None
        else:
            return None
    required = ("authenticity_score","misinformation_risk","psychological_manipulation_score","explanation")
    if not all(k in data for k in required):
        return None
    for k in required[:3]:
        try: data[k] = max(0, min(100, int(float(data[k]))))
        except: return None
    data["explanation"] = str(data["explanation"]).strip()
    return data


def risk_label_color(score: int, invert: bool = False):
    v = score if not invert else 100 - score
    if v >= 70: return "CRITICAL", "#f87171"
    if v >= 40: return "ELEVATED", "#fbbf24"
    return "LOW", "#4ade80"


def overall_level(auth, mis, psych):
    c = (mis + psych + (100 - auth)) / 3
    if c >= 65: return "error"
    if c >= 40: return "warning"
    return "success"


def extract_video_frames(uploaded) -> List[Image.Image]:
    file_bytes = uploaded.read()
    suffix = os.path.splitext(uploaded.name or "video")[1] or ".mp4"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(file_bytes); tmp.flush(); tmp.close()
        cap = cv2.VideoCapture(tmp.name)
        if not cap.isOpened(): return []
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if n <= 0: cap.release(); return []
        indices = sorted(set([0, max(0, n//2), max(0, n-1)]))
        frames = []
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if ok and frame is not None:
                frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
        cap.release()
        while 0 < len(frames) < 3: frames.append(frames[-1].copy())
        return frames[:3]
    finally:
        try: os.unlink(tmp.name)
        except: pass


def run_gemini(images: List[Image.Image], caption: str, prompt: str = FORENSICS_PROMPT) -> str:
    parts = [prompt, f"\n\nContext:\n{caption.strip() or '(none)'}\n"]
    for i, img in enumerate(images, 1):
        parts += [f"\n[Frame {i}]\n", img]
    for model_name in [MODEL_NAME, FALLBACK_MODEL]:
        try:
            client = genai.GenerativeModel(model_name)
            resp = client.generate_content(parts)
            if resp.candidates:
                return (resp.text or "").strip()
        except Exception:
            continue
    raise RuntimeError("All Gemini models failed. Check your API key and quota.")


def fetch_link_content(url: str) -> dict:
    """Fetch title, description, og:image from any URL."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TattvaBot/1.0)"}
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        html = resp.text
        def meta(prop):
            m = re.search(rf'<meta[^>]+(?:property|name)=["\'](?:og:)?{prop}["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
            if not m:
                m = re.search(rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:)?{prop}["\']', html, re.I)
            return m.group(1).strip() if m else ""
        title    = meta("title")   or re.search(r"<title[^>]*>([^<]+)</title>", html, re.I) and re.search(r"<title[^>]*>([^<]+)</title>", html, re.I).group(1) or "Unknown"
        desc     = meta("description")[:400] if meta("description") else ""
        og_image = meta("image")
        img_obj  = None
        if og_image:
            try:
                ir = requests.get(og_image, headers=headers, timeout=10)
                img_obj = Image.open(io.BytesIO(ir.content)).convert("RGB")
            except: pass
        return {"title": title, "description": desc, "image": img_obj, "image_url": og_image}
    except Exception as e:
        return {"title": "", "description": "", "image": None, "image_url": None, "error": str(e)}


def show_results(images: List[Image.Image], caption: str, prompt: str = FORENSICS_PROMPT):
    with st.spinner("Running forensics engine…"):
        try:
            raw = run_gemini(images, caption, prompt)
        except Exception as e:
            st.error(f"Gemini error: {e}"); return

    parsed = parse_forensics_json(raw)
    if not parsed:
        st.error("Could not parse model response.")
        st.code(raw[:2000]); return

    auth  = parsed["authenticity_score"]
    mis   = parsed["misinformation_risk"]
    psych = parsed["psychological_manipulation_score"]
    expl  = parsed["explanation"]

    st.markdown('<p class="section-label">Risk Analysis</p>', unsafe_allow_html=True)
    m1, m2, m3 = st.columns(3)
    with m1:
        al, ac = risk_label_color(auth, invert=True)
        st.metric("Authenticity", f"{auth}/100")
        st.markdown(f"<p style='color:{ac};font-family:Space Mono,monospace;font-size:.7rem;letter-spacing:.1em;margin-top:.3rem;'>{al}</p>", unsafe_allow_html=True)
        st.progress(auth/100)
    with m2:
        ml, mc = risk_label_color(mis)
        st.metric("Misinformation Risk", f"{mis}/100")
        st.markdown(f"<p style='color:{mc};font-family:Space Mono,monospace;font-size:.7rem;letter-spacing:.1em;margin-top:.3rem;'>{ml}</p>", unsafe_allow_html=True)
        st.progress(mis/100)
    with m3:
        pl, pc = risk_label_color(psych)
        st.metric("Manipulation Score", f"{psych}/100")
        st.markdown(f"<p style='color:{pc};font-family:Space Mono,monospace;font-size:.7rem;letter-spacing:.1em;margin-top:.3rem;'>{pl}</p>", unsafe_allow_html=True)
        st.progress(psych/100)

    st.markdown("")
    lvl = overall_level(auth, mis, psych)
    if lvl == "success":   st.success(f"**Verdict:** {expl}")
    elif lvl == "warning": st.warning(f"**Verdict:** {expl}")
    else:                  st.error(f"**Verdict:** {expl}")


# ─── HEADER ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="tattva-header">
  <div class="tattva-eyebrow">Digital Forensics · AI Detection · Fact Check</div>
  <div class="tattva-logo">T<span class="accent">attva</span></div>
  <div class="tattva-sub">Verify reality in the age of generative media</div>
</div>
<div class="tattva-rule"></div>
""", unsafe_allow_html=True)

# ─── TABS ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["🖼   IMAGE", "🎥   VIDEO", "🔗   LINK"])

# ── Tab 1: Image ──────────────────────────────────────────────────────────────
with tab1:
    _, c, _ = st.columns([0.05, 0.9, 0.05])
    with c:
        st.markdown("")
        uploaded_img = st.file_uploader(
            "Drop an image or click to browse",
            type=["png","jpg","jpeg","webp","gif"],
            label_visibility="visible", key="img_up"
        )
        caption_img = st.text_area(
            "Caption or context  (optional — improves accuracy)",
            height=90, placeholder="Paste the post caption, tweet, or any context…",
            key="img_cap"
        )
        if st.button("ANALYZE IMAGE", type="primary", use_container_width=True, key="img_btn"):
            if not uploaded_img:
                st.warning("Upload an image first.")
            else:
                try:
                    pil = Image.open(io.BytesIO(uploaded_img.read()))
                    pil = pil.convert("RGB") if pil.mode != "RGB" else pil
                    st.image(pil, use_container_width=True)
                    show_results([pil], caption_img)
                except Exception as e:
                    st.error(f"Could not open image: {e}")

# ── Tab 2: Video ──────────────────────────────────────────────────────────────
with tab2:
    _, c, _ = st.columns([0.05, 0.9, 0.05])
    with c:
        st.markdown("")
        uploaded_vid = st.file_uploader(
            "Drop a video or click to browse — 3 key frames will be extracted",
            type=["mp4","mov","avi"],
            label_visibility="visible", key="vid_up"
        )
        caption_vid = st.text_area(
            "Caption or context  (optional)",
            height=90, placeholder="Paste the post caption, tweet, or any context…",
            key="vid_cap"
        )
        if st.button("ANALYZE VIDEO", type="primary", use_container_width=True, key="vid_btn"):
            if not uploaded_vid:
                st.warning("Upload a video first.")
            else:
                frames = extract_video_frames(uploaded_vid)
                if not frames:
                    st.error("Could not read frames. Try an MP4 file.")
                else:
                    st.markdown('<p class="section-label">Extracted Frames — First · Middle · Last</p>', unsafe_allow_html=True)
                    cols = st.columns(3)
                    for i, img in enumerate(frames):
                        with cols[i]:
                            st.image(img, use_container_width=True, caption=f"Frame {i+1}")
                    show_results(frames, caption_vid)

# ── Tab 3: Link ───────────────────────────────────────────────────────────────
with tab3:
    _, c, _ = st.columns([0.05, 0.9, 0.05])
    with c:
        st.markdown("")
        link_url = st.text_input(
            "Paste any social media or news URL",
            placeholder="https://twitter.com/...  ·  https://linkedin.com/...  ·  any public URL",
            key="link_in"
        )
        st.markdown(
            "<p style='color:#1e3a4a;font-family:Space Mono,monospace;font-size:.65rem;margin-top:-.4rem;margin-bottom:.8rem;'>"
            "Tattva fetches the post content and uses Gemini to check authenticity — no image required</p>",
            unsafe_allow_html=True
        )
        extra_ctx = st.text_area(
            "Extra context  (optional)",
            height=80, placeholder="Any extra info about this post…",
            key="link_cap"
        )
        if st.button("ANALYZE LINK", type="primary", use_container_width=True, key="link_btn"):
            if not link_url.strip():
                st.warning("Paste a URL first.")
            else:
                with st.spinner("Fetching post content…"):
                    content = fetch_link_content(link_url.strip())

                if "error" in content and not content["title"]:
                    st.error(f"Could not fetch the URL: {content['error']}")
                else:
                    # Show what we fetched
                    if content["title"]:
                        st.markdown(f"<div class='result-card'><p style='color:#00ffe0;font-family:Space Mono,monospace;font-size:.65rem;letter-spacing:.2em;margin-bottom:.4rem;'>FETCHED POST</p><p style='font-weight:700;margin-bottom:.3rem;'>{content['title']}</p><p style='color:#475569;font-size:.85rem;'>{content['description']}</p></div>", unsafe_allow_html=True)
                    if content["image"]:
                        st.image(content["image"], use_container_width=True)

                    # Build context string for Gemini
                    gemini_ctx = f"""URL: {link_url}
Title: {content['title']}
Description: {content['description']}
User context: {extra_ctx.strip() or '(none)'}"""

                    if content["image"]:
                        # Have image — use visual + text forensics
                        show_results([content["image"]], gemini_ctx)
                    else:
                        # No image — text-only analysis via LINK_PROMPT
                        with st.spinner("Running text forensics via Gemini…"):
                            try:
                                # For text-only we pass a dummy tiny image + rich text
                                dummy = Image.new("RGB", (4, 4), (10, 14, 20))
                                raw = run_gemini([dummy], gemini_ctx, LINK_PROMPT)
                            except Exception as e:
                                st.error(f"Gemini error: {e}")
                                st.stop()

                        parsed = parse_forensics_json(raw)
                        if not parsed:
                            st.error("Could not parse model response.")
                            st.code(raw[:2000])
                        else:
                            auth  = parsed["authenticity_score"]
                            mis   = parsed["misinformation_risk"]
                            psych = parsed["psychological_manipulation_score"]
                            expl  = parsed["explanation"]

                            st.markdown('<p class="section-label">Risk Analysis (Text-based)</p>', unsafe_allow_html=True)
                            m1, m2, m3 = st.columns(3)
                            with m1:
                                al, ac = risk_label_color(auth, invert=True)
                                st.metric("Authenticity", f"{auth}/100")
                                st.markdown(f"<p style='color:{ac};font-family:Space Mono,monospace;font-size:.7rem;'>{al}</p>", unsafe_allow_html=True)
                                st.progress(auth/100)
                            with m2:
                                ml, mc = risk_label_color(mis)
                                st.metric("Misinformation Risk", f"{mis}/100")
                                st.markdown(f"<p style='color:{mc};font-family:Space Mono,monospace;font-size:.7rem;'>{ml}</p>", unsafe_allow_html=True)
                                st.progress(mis/100)
                            with m3:
                                pl, pc = risk_label_color(psych)
                                st.metric("Manipulation Score", f"{psych}/100")
                                st.markdown(f"<p style='color:{pc};font-family:Space Mono,monospace;font-size:.7rem;'>{pl}</p>", unsafe_allow_html=True)
                                st.progress(psych/100)
                            st.markdown("")
                            lvl = overall_level(auth, mis, psych)
                            if lvl == "success":   st.success(f"**Verdict:** {expl}")
                            elif lvl == "warning": st.warning(f"**Verdict:** {expl}")
                            else:                  st.error(f"**Verdict:** {expl}")
