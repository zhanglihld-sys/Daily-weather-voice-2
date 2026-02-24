import os
import requests
import subprocess

TG_TOKEN = os.environ["TG_BOT_TOKEN"]
TG_CHAT = os.environ["TG_CHAT_ID"]

def get_updates():
    url = f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()

def clear_updates():
    url = f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates"
    requests.get(url, params={"offset": -1}, timeout=10)

def main():
    data = get_updates()
    if not data.get("ok"):
        return

    for item in data.get("result", []):
        msg = item.get("message", {})
        text = msg.get("text", "").lower().strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))

        if chat_id == TG_CHAT and text == "weather":
            print("Trigger detected.")
            subprocess.run(["python", "app/main.py"])
            clear_updates()
            return

if __name__ == "__main__":
    main()
