import os
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from gtts import gTTS

# ===== ENV =====
VISUAL_KEY = os.environ["VISUAL_CROSSING_API_KEY"].strip()
LOCATION = os.environ["LOCATION"].strip()
TG_TOKEN = os.environ["TG_BOT_TOKEN"].strip()
TG_CHAT = os.environ["TG_CHAT_ID"].strip()

TZ_NAME = os.getenv("TZ_NAME", "America/New_York").strip()
RUN_MODE = os.getenv("RUN_MODE", "AM").strip().upper()  # AM / PM

OUT_DIR = "out"


def fmt_num(x, nd=0):
    """用于 caption/日志显示（保留负号）"""
    if x is None:
        return "未知"
    try:
        if isinstance(x, (int, float)):
            v = round(float(x), nd)
            if abs(v - int(v)) < 1e-9:
                return str(int(v))
            return str(v)
        return str(x)
    except:
        return str(x)


def speak_temp_c(x):
    """
    ✅ 关键：所有温度用于口播时，统一把负号改写成“零下N”
    避免 TTS 吞掉 '-' 读错。
    """
    if x is None:
        return "未知"
    try:
        v = float(x)
        iv = int(round(v))
        if iv < 0:
            return f"零下{abs(iv)}"
        return str(iv)
    except:
        s = str(x).strip()
        if s.startswith("-"):
            return "零下" + s[1:]
        return s


def fetch_weather() -> dict:
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{LOCATION}"
    params = {
        "key": VISUAL_KEY,
        "contentType": "json",
        "unitGroup": "metric",            # 摄氏度
        "include": "days,current,alerts",
        "lang": "zh",
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def pick_today(vc: dict, tz_name: str) -> dict:
    tz = ZoneInfo(tz_name)
    today_str = datetime.now(tz).strftime("%Y-%m-%d")
    days = vc.get("days", []) or []
    for d in days:
        if d.get("datetime") == today_str:
            return d
    return days[0] if days else {}


def comfort_label(temp_c, humidity_pct) -> str:
    if temp_c is None or humidity_pct is None:
        return "整体体感一般"
    t = float(temp_c)
    h = float(humidity_pct)

    if t >= 30 and h >= 65:
        return "偏闷热"
    if t >= 28 and h >= 70:
        return "比较闷热"
    if h <= 30:
        return "空气偏干"
    if t <= 5:
        return "体感偏冷"
    if 18 <= t <= 26 and 35 <= h <= 60:
        return "比较舒适"
    if t >= 27:
        return "略热"
    if t <= 17:
        return "略凉"
    return "整体体感正常"


def umbrella_hint(precipprob) -> str:
    if precipprob is None:
        return "出门建议随身带伞以防万一"
    p = float(precipprob)
    if p >= 70:
        return "降雨概率很高，建议带伞或穿防水外套"
    if p >= 40:
        return "有一定下雨可能，建议带把伞更稳妥"
    if p >= 20:
        return "下雨概率不高，但带把折叠伞更安心"
    return "下雨概率较低，一般不需要带伞"


def build_script_am(resolved: str, current: dict, today: dict) -> str:
    comfort = comfort_label(current.get("temp"), current.get("humidity"))
    umbrella = umbrella_hint(today.get("precipprob"))

    return (
        f"早上好，这里是{resolved}天气播报。"
        f"当前天气{current.get('conditions')}，"
        f"气温{speak_temp_c(current.get('temp'))}度，体感{speak_temp_c(current.get('feelslike'))}度，"
        f"湿度{fmt_num(current.get('humidity'))}%，{comfort}。"
        f"风速{fmt_num(current.get('windspeed'))}公里每小时，阵风{fmt_num(current.get('windgust'))}公里每小时。"
        f"今天整体{today.get('conditions')}，"
        f"最高{speak_temp_c(today.get('tempmax'))}度，最低{speak_temp_c(today.get('tempmin'))}度，"
        f"降水概率{fmt_num(today.get('precipprob'))}%。"
        f"{umbrella}。祝你今天顺利。"
    )


def build_script_pm(resolved: str, current: dict, today: dict) -> str:
    comfort = comfort_label(current.get("temp"), current.get("humidity"))
    umbrella = umbrella_hint(today.get("precipprob"))

    return (
        f"下午好，这里是{resolved}下班前天气提醒。"
        f"现在{current.get('conditions')}，"
        f"气温{speak_temp_c(current.get('temp'))}度，体感{speak_temp_c(current.get('feelslike'))}度，"
        f"湿度{fmt_num(current.get('humidity'))}%，{comfort}。"
        f"当前风速{fmt_num(current.get('windspeed'))}公里每小时。"
        f"今天最高{speak_temp_c(today.get('tempmax'))}度，最低{speak_temp_c(today.get('tempmin'))}度，"
        f"降水概率{fmt_num(today.get('precipprob'))}%。"
        f"{umbrella}。回家路上注意安全。"
    )


def tts_mp3(text: str, out_path: str):
    gTTS(text=text, lang="zh-cn").save(out_path)


def tg_send_audio(audio_path: str, caption: str):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendAudio"
    with open(audio_path, "rb") as f:
        r = requests.post(
            url,
            data={"chat_id": TG_CHAT, "caption": caption},
            files={"audio": f},
            timeout=90,
        )
    r.raise_for_status()


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    tz = ZoneInfo(TZ_NAME)
    stamp = datetime.now(tz).strftime("%Y%m%d_%H%M")

    vc = fetch_weather()
    with open(os.path.join(OUT_DIR, f"weather_raw_{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump(vc, f, ensure_ascii=False, indent=2)

    today = pick_today(vc, TZ_NAME)
    current = vc.get("currentConditions", {}) or {}
    resolved = vc.get("resolvedAddress") or LOCATION

    if RUN_MODE == "PM":
        script = build_script_pm(resolved, current, today)
        tag = "PM"
    else:
        script = build_script_am(resolved, current, today)
        tag = "AM"

    with open(os.path.join(OUT_DIR, f"script_{tag}_{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write(script + "\n")

    mp3_path = os.path.join(OUT_DIR, f"weather_{tag}_{stamp}.mp3")
    tts_mp3(script, mp3_path)

    # caption 保留真实负号，供你核对数据源
    cap = (
        f"{tag} | {resolved} | now {fmt_num(current.get('temp'))}°C | "
        f"hi/lo {fmt_num(today.get('tempmax'))}/{fmt_num(today.get('tempmin'))}°C | "
        f"hum {fmt_num(current.get('humidity'))}% | rain {fmt_num(today.get('precipprob'))}%"
    )
    tg_send_audio(mp3_path, cap)

    print("DONE:", mp3_path)


if __name__ == "__main__":
    main()
