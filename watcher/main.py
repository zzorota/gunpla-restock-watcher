"""ガンプラ再販監視ツールの本体。

products.yaml に列挙した商品ページを定期的にチェックし、
「在庫なし → 在庫あり」に変化したタイミングでDiscordに通知する。
"""

import json
import os
import random
import sys
import time
from pathlib import Path

import requests
import yaml

from watcher.checkers import extract_price, get_status
from watcher.notifier import send_discord

ROOT_DIR = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT_DIR / "state.json"
PRODUCTS_PATH = ROOT_DIR / "products.yaml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


def load_products() -> list[dict]:
    data = yaml.safe_load(PRODUCTS_PATH.read_text(encoding="utf-8")) or {}
    return [p for p in data.get("products", []) if not p.get("disabled")]


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def fetch(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def main() -> None:
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("DISCORD_WEBHOOK_URL が設定されていません", file=sys.stderr)
        sys.exit(1)

    products = load_products()
    if not products:
        print("products.yaml に有効な商品がありません（disabled: true になっていないか確認してください）")
        return

    state = load_state()
    changed = False

    for product in products:
        name = product["name"]
        url = product["url"]
        prev_entry = state.get(url)
        prev_status = prev_entry.get("status") if prev_entry else None
        is_first_check = prev_entry is None

        try:
            html = fetch(url)
            status = get_status(url, html)
        except Exception as e:
            print(f"[ERROR] {name}: {e}")
            continue

        max_price = product.get("max_price")
        price = None
        if status == "in_stock" and max_price is not None:
            price = extract_price(html)
            if price is not None and price > max_price:
                status = "in_stock_overpriced"

        price_info = f" price=¥{price:,}" if price is not None else ""
        print(f"[CHECK] {name}: {prev_status} -> {status}{price_info}")

        if status == "blocked" and prev_status != "blocked":
            send_discord(
                webhook_url,
                f"⚠️「{name}」のチェックがブロックされました(CAPTCHA等の可能性)。\n{url}",
            )

        if status == "in_stock" and not is_first_check and prev_status in (
            "out_of_stock",
            "unknown",
            "blocked",
            "in_stock_overpriced",
        ):
            price_note = f"（¥{price:,}）" if price is not None else ""
            send_discord(
                webhook_url,
                f"🎉「{name}」が定価{price_note}で入荷/再販されました!\n{url}",
            )

        if status != prev_status:
            state[url] = {
                "name": name,
                "status": status,
                "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            changed = True

        time.sleep(random.uniform(1.5, 3.5))

    if changed:
        save_state(state)


if __name__ == "__main__":
    main()
