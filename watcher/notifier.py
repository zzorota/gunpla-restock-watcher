"""Discord Webhookへの通知処理。"""

import requests


def send_discord(webhook_url: str, message: str) -> None:
    try:
        resp = requests.post(webhook_url, json={"content": message}, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"[ERROR] Discord通知に失敗しました: {e}")
