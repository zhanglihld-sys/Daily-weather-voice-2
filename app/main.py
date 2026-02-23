import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from gtts import gTTS

# ===== ENV =====
VISUAL_KEY = os.environ["VISUAL_CROSSING_API_KEY"].strip()
LOCATION = os.environ["LOCATION"].strip()  # 建议：40.8448,-73.8648
TG_TOKEN = os.environ["TG_BOT_TOKEN"].strip()
TG_CHAT = os.environ["TG_CHAT_ID"].strip()

TZ_NAME = os.getenv("TZ_NAME", "America/New_York").strip()
UNIT_GROUP = os.getenv("UNIT_GROUP", "us").strip()   # us / metric / uk
VC_LANG = os.getenv("VC_LANG", "zh").strip()

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
    tz = ZoneInfo(tz_name)
    today_str = datetime.now(tz).strftime("%Y-%m-%d")
    days = vc.get("days", []) or []
    for d in days:
        if d.get("datetime") == today_str:
            return d
    return days[0] if days else {}


def fmt_num(x):
    if x is None:
        return "未知"
    try:
        # 温度/风速等一般一位小数足够
        if isinstance(x, (int, float)):
            # 去掉 .0
            v = round(float(x), 1)
            return str(int(v)) if abs(v - int(v)) < 1e-9 else str(v)
        return str(x)
    except:
        return str(x)


def make_script(resolved: str, timezone: str, current: dict, today: dict, alerts: list) -> str:
    # 单位口播
    if UNIT_GROUP == "us":
        t_unit = "华氏度"
        w_unit = "英里每小时"
    else:
        t_unit = "摄氏度"
        w_unit = "公里每小时"

    alert_line = ""
    if alerts:
        a = alerts[0] or {}
        headline = a.get("headline") or a.get("event") or "天气预警"
        alert_line = f"先插播一条预警：{headline}。"

    # 当前
    cur_cond = current.get("conditions")
    cur_temp = current.get("temp")
    cur_feel = current.get("feelslike")
    cur_wind = current.get("windspeed")
    cur_gust = current.get("windgust")

    # 今日
    cond = today.get("conditions")
    tmax = today.get("tempmax")
    tmin = today.get("tempmin")
    precip_prob = today.get("precipprob")
    wind = today.get("windspeed")
    gust = today.get("windgust")
    uv = today.get("uvindex")

    # 全程只读 API 数字，不做任何“智能改写”
    script = (
        f"{alert_line}"
        f"这里是{resolved}的天气播报。"
        f"当前天气：{fmt_num(cur_cond)}，气温{fmt_num(cur_temp)}{t_unit}，体感{fmt_num(cur_feel)}{t_unit}。"
        f"当前风速{fmt_num(cur_wind)}{w_unit}，阵风{fmt_num(cur_gust)}{w_unit}。"
        f"今天整体：{fmt_num(cond)}。"
        f"最高{fmt_num(tmax)}{t_unit}，最低{fmt_num(tmin)}{t_unit}。"
        f"降水概率{fmt_num(precip_prob)}%。"
        f"今天风速{fmt_num(wind)}{w_unit}，阵风{fmt_num(gust)}{w_unit}。"
        f"紫外线指数{fmt_num(uv)}。"
        f"出门建议：根据降水概率和风力，带好雨具并注意保暖。祝你一天顺利。"
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
    timezone = vc.get("timezone") or TZ_NAME
    alerts = vc.get("alerts", []) or []

    script = make_script(resolved, timezone, current, today, alerts)
    with open(os.path.join(OUT_DIR, "script.txt"), "w", encoding="utf-8") as f:
        f.write(script + "\n")

    ymd = datetime.now(ZoneInfo(TZ_NAME)).strftime("%Y%m%d")
    mp3_path = os.path.join(OUT_DIR, f"weather_{ymd}.mp3")
    tts_mp3(script, mp3_path)

    # caption 用来对照：你一眼看出“数字是否一致”
    cap = (
        f"{resolved} | now {fmt_num(current.get('temp'))} | "
        f"hi/lo {fmt_num(today.get('tempmax'))}/{fmt_num(today.get('tempmin'))} | "
        f"rain {fmt_num(today.get('precipprob'))}%"
    )
    telegram_send_audio(mp3_path, cap)

    print("DONE:", mp3_path)


if __name__ == "__main__":
    main()
