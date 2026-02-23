import os
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from gtts import gTTS

# ===== ENV =====
VISUAL_KEY = os.environ["VISUAL_CROSSING_API_KEY"].strip()
LOCATION = os.environ["LOCATION"].strip()  # 建议：40.8448,-73.8648
TG_TOKEN = os.environ["TG_BOT_TOKEN"].strip()
TG_CHAT = os.environ["TG_CHAT_ID"].strip()

TZ_NAME = os.getenv("TZ_NAME", "America/New_York").strip()

OUT_DIR = "out"


def fmt_num(x, nd=0):
    """把数字格式化成更适合口播的样子"""
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


def fetch_weather() -> dict:
    # 强制 metric = 摄氏度
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{LOCATION}"
    params = {
        "key": VISUAL_KEY,
        "contentType": "json",
        "unitGroup": "metric",            # ✅ 摄氏度
        "include": "days,current,alerts",
        "lang": "zh",
    }
    resp = requests.get(url, params=params, timeout=30)
    print("VC_STATUS:", resp.status_code)
    print("VC_TEXT_HEAD:", resp.text[:200].replace("\n", " "))
    resp.raise_for_status()
    return resp.json()


def pick_today(vc: dict, tz_name: str) -> dict:
    """用时区严格匹配今天，避免 days[0] 偶尔不是今天"""
    tz = ZoneInfo(tz_name)
    today_str = datetime.now(tz).strftime("%Y-%m-%d")
    days = vc.get("days", []) or []
    for d in days:
        if d.get("datetime") == today_str:
            return d
    return days[0] if days else {}


def comfort_label(temp_c, humidity_pct) -> str:
    """
    电台级“舒适度”判定：只用温度+湿度，简单可靠。
    """
    if temp_c is None or humidity_pct is None:
        return "整体体感一般"

    t = float(temp_c)
    h = float(humidity_pct)

    # 先处理极端
    if t >= 30 and h >= 65:
        return "偏闷热"
    if t >= 28 and h >= 70:
        return "比较闷热"
    if h <= 30:
        return "空气偏干"
    if t <= 5:
        return "体感偏冷"

    # 常见舒适区
    if 18 <= t <= 26 and 35 <= h <= 60:
        return "比较舒适"

    # 兜底
    if t >= 27:
        return "略热"
    if t <= 17:
        return "略凉"
    return "整体体感正常"


def umbrella_hint(precipprob) -> str:
    """基于降水概率的简单带伞建议"""
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


def script_from_data(resolved: str, current: dict, today: dict) -> str:
    # ===== 取值（尽量容错）=====
    cond_now = current.get("conditions")
    temp_now = current.get("temp")
    feel_now = current.get("feelslike")
    hum_now = current.get("humidity")
    wind_now = current.get("windspeed")
    gust_now = current.get("windgust")

    cond_today = today.get("conditions")
    tmax = today.get("tempmax")
    tmin = today.get("tempmin")
    precipprob = today.get("precipprob")
    uv = today.get("uvindex")

    comfort = comfort_label(temp_now, hum_now)
    umbrella = umbrella_hint(precipprob)

    # ===== 固定模板（保证数据不乱）=====
    # 注意：这里不让任何 AI 改写数字，播报=API
    script = (
        f"这里是{resolved}天气播报。"
        f"当前天气{fmt_num(cond_now)}，气温{fmt_num(temp_now)}度，体感{fmt_num(feel_now)}度，空气湿度{fmt_num(hum_now)}%，{comfort}。"
        f"当前风速{fmt_num(wind_now)}公里每小时，阵风{fmt_num(gust_now)}公里每小时。"
        f"今天整体{fmt_num(cond_today)}，最高{fmt_num(tmax)}度，最低{fmt_num(tmin)}度，降水概率{fmt_num(precipprob)}%。"
        f"紫外线指数{fmt_num(uv)}。"
        f"{umbrella}。祝你今天顺利。"
    )
    return script


def tts_mp3(text: str, out_path: str):
    gTTS(text=text, lang="zh-cn").save(out_path)


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
    with open(os.path.join(OUT_DIR, "weather_raw.json"), "w", encoding="utf-8") as f:
        json.dump(vc, f, ensure_ascii=False, indent=2)

    today = pick_today(vc, TZ_NAME)
    current = vc.get("currentConditions", {}) or {}
    resolved = vc.get("resolvedAddress") or LOCATION

    script = script_from_data(resolved, current, today)
    with open(os.path.join(OUT_DIR, "script.txt"), "w", encoding="utf-8") as f:
        f.write(script + "\n")

    ymd = datetime.now(ZoneInfo(TZ_NAME)).strftime("%Y%m%d")
    mp3_path = os.path.join(OUT_DIR, f"weather_{ymd}.mp3")
    tts_mp3(script, mp3_path)

    # Telegram caption：快速校验（确保数据口径对）
    cap = (
        f"{resolved} | now {fmt_num(current.get('temp'))}°C | "
        f"hi/lo {fmt_num(today.get('tempmax'))}/{fmt_num(today.get('tempmin'))}°C | "
        f"hum {fmt_num(current.get('humidity'))}% | rain {fmt_num(today.get('precipprob'))}%"
    )
    telegram_send_audio(mp3_path, cap)

    print("DONE:", mp3_path)


if __name__ == "__main__":
    main()
