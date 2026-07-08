"""ガンプラ再販監視ツールの本体。

products.yaml に列挙した商品ページを定期的にチェックし、
「在庫なし → 在庫あり」に変化したタイミングでDiscordに通知する。

WATCHER_MODE 環境変数で動作を切り替える:
  cloud (デフォルト): Amazon・駿河屋"以外"を対象に、通常のHTTP取得でチェックする。
                      GitHub Actions側で使う。
  local             : Amazon・駿河屋"だけ"を対象に、ヘッドレスブラウザ(Playwright)で
                      チェックする。GitHub ActionsのIPだとこの2サイトはボット判定
                      されて正しく取得できないため、ローカルPC(自分の回線)から
                      実行する用。状態は state.local.json に保存し、
                      GitHubにはコミットしない(.gitignore済み)。
"""

import json
import os
import random
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml
from playwright.sync_api import sync_playwright

from watcher.checkers import extract_price, get_status
from watcher.notifier import send_discord

ROOT_DIR = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT_DIR / "state.json"
LOCAL_STATE_PATH = ROOT_DIR / "state.local.json"
PRODUCTS_PATH = ROOT_DIR / "products.yaml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# Amazon・駿河屋はボット対策が厳しく、GitHub ActionsのIPからだと
# ヘッドレスブラウザで見に行ってもブロックされる。ローカルPCからだけ
# チェックする対象として切り分ける。
BROWSER_DOMAINS = {
    "amazon.co.jp",
    "www.amazon.co.jp",
    "suruga-ya.jp",
    "www.suruga-ya.jp",
}


def load_products() -> list[dict]:
    data = yaml.safe_load(PRODUCTS_PATH.read_text(encoding="utf-8")) or {}
    return [p for p in data.get("products", []) if not p.get("disabled")]


def load_state(state_path: Path) -> dict:
    if state_path.exists():
        return json.loads(state_path.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict, state_path: Path) -> None:
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def needs_browser(url: str) -> bool:
    return urlparse(url).netloc.lower() in BROWSER_DOMAINS


def fetch(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def fetch_with_browser(browser, url: str) -> str:
    """URLごとに新しいブラウザコンテキスト(Cookie等をリセットした状態)で取得する。

    同じコンテキストを使い回して連続アクセスすると、駿河屋のCloudflare対策に
    セッション単位でブロックされることが確認できたため、1件ごとに毎回
    まっさらな状態で見に行くようにしている。
    """
    context = browser.new_context(
        user_agent=HEADERS["User-Agent"],
        locale="ja-JP",
        extra_http_headers={"Accept-Language": HEADERS["Accept-Language"]},
    )
    try:
        page = context.new_page()
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        return page.content()
    finally:
        context.close()


def main() -> None:
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("DISCORD_WEBHOOK_URL が設定されていません", file=sys.stderr)
        sys.exit(1)

    mode = os.environ.get("WATCHER_MODE", "cloud")
    all_products = load_products()
    if mode == "local":
        products = [p for p in all_products if needs_browser(p["url"])]
        state_path = LOCAL_STATE_PATH
    else:
        products = [p for p in all_products if not needs_browser(p["url"])]
        state_path = STATE_PATH

    if not products:
        print(f"products.yaml に有効な商品がありません（mode={mode}）")
        return

    state = load_state(state_path)
    changed = False

    browser = None
    playwright_cm = None
    if mode == "local":
        playwright_cm = sync_playwright().start()
        browser = playwright_cm.chromium.launch()

    try:
        for product in products:
            name = product["name"]
            url = product["url"]
            prev_entry = state.get(url)
            prev_status = prev_entry.get("status") if prev_entry else None
            is_first_check = prev_entry is None

            try:
                if mode == "local":
                    html = fetch_with_browser(browser, url)
                else:
                    html = fetch(url)
                status = get_status(url, html)
            except Exception as e:
                print(f"[ERROR] {name}: {e}")
                continue

            max_price = product.get("max_price")
            price = None
            if status == "in_stock" and max_price is not None:
                price = extract_price(url, html)
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
    finally:
        if browser is not None:
            browser.close()
        if playwright_cm is not None:
            playwright_cm.stop()

    if changed:
        save_state(state, state_path)


if __name__ == "__main__":
    main()
