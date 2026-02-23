import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from google import genai
from gtts import gTTS

# =========================
# ENV
# =========================
VISUAL_KEY = os.environ["VISUAL_CROSSING_API_KEY"].strip()
GEMINI_KEY = os.environ["GEMINI_API_KEY"].strip()
LOCATION = os.environ["LOCATION"].strip()  # 推荐： "40.8448,-73.8648"
TG_TOKEN = os.environ["TG_BOT_TOKEN"].strip()
TG_CHAT = os.environ["TG_CHAT_ID"].strip()

TZ_NAME = os.getenv("TZ_NAME", "America/New_York").strip()
UNIT_GROUP = os.getenv("UNIT_GROUP", "us").strip()   # us / metric / uk
VC_LANG = os.getenv("VC_LANG", "zh").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview").strip()

OUT_DIR = "out"


def fetch_weather() -> dict:
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{LOCATION}"
    params = {
        "key": VISUAL_KEY,
        "contentType": "json",
        "unitGroup": UNIT_GROUP,
        "include": "days,current,alerts",
        "lang": VC_LANG,
    }
    resp = requests.get(url, params=params, timeout=30)

    print("VC_STATUS:", resp.status_code)
    print("VC_TEXT_HEAD:", resp.text[:200].replace("\n", " "))

    resp.raise_for_status()
    return resp.json()


def pick_today(vc: dict, tz_name: str) -> dict:
    """
    避免 days[0] 不等于今天：用 timezone 的今天日期严格匹配。
    """
    tz = ZoneInfo(tz_name)
    today_str = datetime.now(tz).strftime("%Y-%m-%d")

    days = vc.get("days", []) or []
    for d in days:
        if d.get("datetime") == today_str:
            return d

    # fallback
    return days[0] if days else {}


def build_prompt(vc: dict, today: dict) -> str:
    current = vc.get("currentConditions", {}) or {}
    resolved = vc.get("resolvedAddress") or LOCATION
    timezone = vc.get("timezone") or TZ_NAME
    alerts = vc.get("alerts", []) or []

    # 为了不让 Gemini 自己脑补单位，把单位写死在文案里
    unit_hint = "温度单位：华氏°F；风速单位：mph。" if UNIT_GROUP == "us" else "温度单位：摄氏°C；风速单位：km/h。"

    alert_text = ""
    if alerts:
        # 只取前 1-2 条，防止太长
        brief = []
        for a in alerts[:2]:
            headline = a.get("headline") or a.get("event") or "天气预警"
            brief.append(headline)
        alert_text = "预警：" + "；".join(brief) + "。"

    # 关键字段（不依赖 description，避免翻译误差）
    cur_cond = current.get("conditions")
    cur_temp = current.get("temp")
    cur_feel = current.get("feelslike")
    cur_wind = current.get("windspeed")
    cur_gust = current.get("windgust")

    cond = today.get("conditions")
    tmax = today.get("tempmax")
    tmin = today.get("tempmin")
    precip_prob = today.get("precipprob")
    precip = today.get("precip")
    snow = today.get("snow")
    uv = today.get("uvindex")
    wind = today.get("windspeed")
    gust = today.get("windgust")

    # 口播稿硬约束：不允许输出列表/标题/markdown
    prompt = f"""
你是天气语音播报编辑。只输出“播报正文”，不要标题、不要列表、不要markdown、不要解释。
长度：45~70秒中文口播。风格：电台主播，句子短，有节奏。

地点：{resolved}
时区：{timezone}
{unit_hint}
{alert_text}

当前：{cur_cond}，{cur_temp}°，体感{cur_feel}°，风速{cur_wind}，阵风{cur_gust}。
今天：{cond}，最高{tmax}°，最低{tmin}°。
降水概率{precip_prob}%；预计降水量{precip}；降雪{snow}；紫外线指数{uv}。
今天风速{wind}，阵风{gust}。

要求：必须包含（今天概况/最高最低/降水概率/风/出行建议）。如果有预警，必须在前半段提到。
"""
    return prompt.strip()


def gemini_generate(text: str) -> str:
    client = genai.Client(api_key=GEMINI_KEY)
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=text,
    )
    out = (resp.text or "").strip()
    if not out:
        raise RuntimeError("Gemini returned empty text.")
    return out


def tts_mp3(text: str, path: str):
    gTTS(text=text, lang="zh-cn").save(path)


def telegram_send_audio(audio_path: str, caption: str):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendAudio"
    with open(audio_path, "rb") as f:
        r = requests.post(
            url,
            data={"chat_id": TG_CHAT, "caption": caption},
            files={"audio": f},
            timeout=90,
        )
    print("TG_STATUS:", r.status_code)
    print("TG_TEXT_HEAD:", r.text[:200].replace("\n", " "))
    r.raise_for_status()


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    vc = fetch_weather()

    # 写出原始数据，方便你核对“到底取到哪个城市/时区”
    with open(os.path.join(OUT_DIR, "weather_raw.json"), "w", encoding="utf-8") as f:
        json.dump(vc, f, ensure_ascii=False, indent=2)

    today = pick_today(vc, TZ_NAME)
    current = vc.get("currentConditions", {}) or {}
    resolved = vc.get("resolvedAddress") or LOCATION

    # 生成 prompt → Gemini → script
    prompt = build_prompt(vc, today)
    with open(os.path.join(OUT_DIR, "prompt.txt"), "w", encoding="utf-8") as f:
        f.write(prompt + "\n")

    script = gemini_generate(prompt)
    with open(os.path.join(OUT_DIR, "script.txt"), "w", encoding="utf-8") as f:
        f.write(script + "\n")

    # TTS
    ymd = datetime.now(ZoneInfo(TZ_NAME)).strftime("%Y%m%d")
    mp3_path = os.path.join(OUT_DIR, f"weather_{ymd}.mp3")
    tts_mp3(script, mp3_path)

    # Telegram caption：用于“快速校验是否取对城市/单位/日期”
    cap = (
        f"{resolved} | now {current.get('temp')}° | "
        f"hi/lo {today.get('tempmax')}/{today.get('tempmin')} | "
        f"rain {today.get('precipprob')}%"
    )
    telegram_send_audio(mp3_path, cap)

    print("DONE:", mp3_path)


if __name__ == "__main__":
    main()
