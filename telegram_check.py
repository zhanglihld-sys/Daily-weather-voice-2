import os
import requests
import subprocess

TG_TOKEN = os.environ["TG_BOT_TOKEN"].strip()
TG_CHAT = str(os.environ["TG_CHAT_ID"]).strip()

OFFSET_FILE = ".tg_offset.txt"


def load_offset() -> int:
    try:
        with open(OFFSET_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip() or "0")
    except:
        return 0


def save_offset(offset: int):
    with open(OFFSET_FILE, "w", encoding="utf-8") as f:
        f.write(str(offset))


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
        chat = msg.get("chat", {}) or {}
        chat_id = str(chat.get("id", "")).strip()

        cmd = normalize_cmd(text)
        if chat_id == TG_CHAT and cmd in ("weather", "w"):
            print("Trigger detected from chat:", chat_id, "cmd:", cmd)
            triggered = True

    # ✅ 无论触发与否，都先推进 offset，避免重复读取同一条消息
    if max_update_id >= 0:
        save_offset(max_update_id + 1)
        print("Advance offset ->", max_update_id + 1)

    if triggered:
        # 运行你的主程序（会自动发语音到 Telegram）
        r = subprocess.run(["python", "app/main.py"], check=False)
        print("main.py exit code:", r.returncode)


if __name__ == "__main__":
    main()
