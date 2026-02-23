import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from gtts import gTTS

# ===== ENV =====
VISUAL_KEY = os.environ["VISUAL_CROSSING_API_KEY"]
LOCATION = os.environ["LOCATION"]

TG_TOKEN = os.environ["TG_BOT_TOKEN"]
TG_CHAT = os.environ["TG_CHAT_ID"]

TZ_NAME = "America/New_York"

# ===== 获取天气 =====
url=f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{LOCATION}"

resp=requests.get(url,params={
    "key":VISUAL_KEY,
    "contentType":"json",
    "unitGroup":"metric",
    "include":"days,current",
    "lang":"zh"
})

resp.raise_for_status()

weather=resp.json()

today=weather["days"][0]
current=weather["currentConditions"]
resolved=weather["resolvedAddress"]

# ===== 固定模板（保证数据不乱）=====
script=f"""
这里是{resolved}天气播报。
当前{current['conditions']}，
气温{current['temp']}°C，
体感{current['feelslike']}°C，
湿度{current['humidity']}%。
今天最高{today['tempmax']}°C，
最低{today['tempmin']}°C，
降水概率{today['precipprob']}%。
"""

# ===== 生成语音 =====
os.makedirs("out",exist_ok=True)

mp3="out/weather.mp3"
gTTS(script,lang="zh-cn").save(mp3)

# ===== Telegram发送（含caption）=====
caption=f"{resolved} | now {current['temp']} | hi/lo {today['tempmax']}/{today['tempmin']} | rain {today['precipprob']}%"

requests.post(
    f"https://api.telegram.org/bot{TG_TOKEN}/sendAudio",
    data={
        "chat_id":TG_CHAT,
        "caption":caption
    },
    files={
        "audio":open(mp3,"rb")
    }
)

print("DONE")
