import os
import requests
import subprocess

TG_TOKEN = os.environ["TG_BOT_TOKEN"].strip()
TG_CHAT = str(os.environ["TG_CHAT_ID"]).strip()
OFFSET_FILE = ".tg_offset.txt"


def load_offset() -> int:
    try:
        with open(OFFSET_FILE, "r", encoding="utf-8") as f:
            return int((f.read() or "").strip() or "0")
    except:
        return 0


def save_offset(offset: int):
    with open(OFFSET_FILE, "w", encoding="utf-8") as f:
        f.write(str(offset))


def tg_api(method: str, params=None):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/{method}"
    r = requests.post(url, data=(params or {}), timeout=30)
    r.raise_for_status()
    return r.json()


def ensure_long_polling_mode():
    # ✅ 关键：如果 bot 之前设置过 webhook，getUpdates 会拿不到消息
    # 这里每次轮询都主动 deleteWebhook，确保走 getUpdates
    tg_api("deleteWebhook", {"drop_pending_updates": "false"})


def send_text(text: str):
    tg_api("sendMessage", {"chat_id": TG_CHAT, "text": text})


def get_updates(offset: int):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates"
    r = requests.get(url, params={"offset": offset, "timeout": 0}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        return []
    return data.get("result", [])


def normalize_cmd(text: str) -> str:
    t = (text or "").strip().lower()
    if t.startswith("/"):
        t = t[1:]
    return t


def main():
    ensure_long_polling_mode()

    offset = load_offset()
    updates = get_updates(offset)

    if not updates:
        print("No new updates. offset=", offset)
        return

    max_update_id = offset - 1
    triggered = False

    for u in updates:
        uid = u.get("update_id")
        if isinstance(uid, int):
            max_update_id = max(max_update_id, uid)

        msg = u.get("message", {}) or u.get("edited_message", {}) or {}
        text = msg.get("text", "")
        chat_id = str((msg.get("chat", {}) or {}).get("id", "")).strip()

        cmd = normalize_cmd(text)
        if chat_id == TG_CHAT and cmd in ("weather", "w"):
            triggered = True

    # ✅ 先推进 offset，防止重复触发
    if max_update_id >= 0:
        save_offset(max_update_id + 1)
        print("Advance offset ->", max_update_id + 1)

    if triggered:
        # 先给手机一个“立刻可见”的反馈
        send_text("收到，正在生成语音天气（约30秒）…")

        r = subprocess.run(["python", "app/main.py"], check=False)
        print("main.py exit code:", r.returncode)


if __name__ == "__main__":
    main()
