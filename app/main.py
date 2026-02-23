import os
import requests
from google import genai
from gtts import gTTS

VISUAL_KEY = os.environ["VISUAL_CROSSING_API_KEY"]
GEMINI_KEY = os.environ["GEMINI_API_KEY"]
LOCATION = os.environ["LOCATION"]

TG_TOKEN = os.environ["TG_BOT_TOKEN"]
TG_CHAT = os.environ["TG_CHAT_ID"]

# ===== 获取天气 =====
url=f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{LOCATION}"
weather=requests.get(url,params={"key":VISUAL_KEY,"contentType":"json"}).json()

today=weather["days"][0]

# ===== Gemini 生成播报稿 =====
client=genai.Client(api_key=GEMINI_KEY)

text=f"""
今天天气：
温度{today['temp']}，
最高{today['tempmax']}，
最低{today['tempmin']}，
降水概率{today['precipprob']}。
请生成简短中文天气播报。
"""

resp=client.models.generate_content(
model="gemini-3-flash-preview",
contents=text)

script=resp.text

# ===== 语音 =====
os.makedirs("out",exist_ok=True)
mp3="out/weather.mp3"
gTTS(script,lang="zh-cn").save(mp3)

# ===== Telegram发送 =====
requests.post(
f"https://api.telegram.org/bot{TG_TOKEN}/sendAudio",
data={"chat_id":TG_CHAT},
files={"audio":open(mp3,"rb")}
)

print("DONE")
