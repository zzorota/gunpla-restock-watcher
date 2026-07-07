"""サイトごとの在庫判定ロジック。

各判定関数は "in_stock" / "out_of_stock" / "blocked" / "unknown" のいずれかを返す。
サイトのHTML構造が変わって判定がおかしくなった場合は、ここのキーワードや
セレクタを調整してください。
"""

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

_PRICE_RE = re.compile(r"(?:¥|￥)\s?([\d,]{3,8})|([\d,]{3,8})\s?円(?:\(税込\))?")

NEGATIVE_KEYWORDS = [
    "売り切れ",
    "在庫切れ",
    "在庫なし",
    "販売終了",
    "sold out",
    "完売",
    "現在お取り扱いできません",
    "入荷時期未定",
    "取り扱いを終了しました",
    "受付終了",
]
POSITIVE_KEYWORDS = [
    "カートに入れる",
    "今すぐ買う",
    "今すぐ購入",
    "予約受付中",
    "購入する",
    "buy now",
    "add to cart",
]
BLOCKED_KEYWORDS = [
    "captcha",
    "ロボットではないことを確認",
    "自動アクセスと判断",
    "attention required",
    "access denied",
    "just a moment",
    "このサイトへのアクセスが拒否されました",
]


def _text(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True).lower()


def _generic(html: str) -> str:
    text = _text(html)
    if any(k.lower() in text for k in BLOCKED_KEYWORDS):
        return "blocked"
    has_negative = any(k.lower() in text for k in NEGATIVE_KEYWORDS)
    has_positive = any(k.lower() in text for k in POSITIVE_KEYWORDS)
    if has_positive and not has_negative:
        return "in_stock"
    if has_negative and not has_positive:
        return "out_of_stock"
    if has_positive and has_negative:
        return "in_stock"
    return "unknown"


def _amazon(html: str) -> str:
    text = _text(html)
    if any(k in text for k in BLOCKED_KEYWORDS):
        return "blocked"
    soup = BeautifulSoup(html, "html.parser")
    availability = soup.select_one("#availability")
    if availability is not None:
        avail_text = availability.get_text(strip=True)
        if "在庫切れ" in avail_text or "現在お取り扱いできません" in avail_text:
            return "out_of_stock"
        if "在庫あり" in avail_text or "残り" in avail_text:
            return "in_stock"
    if soup.select_one("#add-to-cart-button") or soup.select_one("#buy-now-button"):
        return "in_stock"
    return _generic(html)


def _yodobashi(html: str) -> str:
    text = _text(html)
    if "現在お取り扱いできません" in text or "販売を終了しました" in text:
        return "out_of_stock"
    if "カートに入れる" in text:
        return "in_stock"
    return _generic(html)


def _hobbysearch(html: str) -> str:
    text = _text(html)
    if "メーカー完売" in text or "販売終了" in text or "取扱終了" in text:
        return "out_of_stock"
    if "在庫あり" in text or "予約受付中" in text or "限定予約受付中" in text:
        return "in_stock"
    return _generic(html)


def _pbandai(html: str) -> str:
    text = _text(html)
    if "受付終了" in text or "sold out" in text:
        return "out_of_stock"
    if "カートに入れる" in text or "予約する" in text:
        return "in_stock"
    return _generic(html)


def _gundam_base(html: str) -> str:
    """THE GUNDAM BASE / GUNDAM SIDE-F の店舗別在庫表示に対応。

    商品ページには「GUNDAM SIDE-F在庫: 在庫あり」のように店舗ごとの
    在庫が文字で列挙されている（在庫なしの場合は「-」）。
    """
    text = _text(html)
    if any(k in text for k in BLOCKED_KEYWORDS):
        return "blocked"
    idx = text.find("side-f在庫")
    if idx != -1:
        window = text[idx: idx + 30]
        return "in_stock" if "在庫あり" in window else "out_of_stock"
    return _generic(html)


def _surugaya(html: str) -> str:
    """駿河屋。ボット対策が強く、GitHub ActionsのIPだとブロックされやすい点に注意。"""
    text = _text(html)
    if any(k in text for k in BLOCKED_KEYWORDS):
        return "blocked"
    if "品切れ" in text or "売り切れ" in text:
        return "out_of_stock"
    if "カートに入れる" in text or "買い物カゴに入れる" in text:
        return "in_stock"
    return _generic(html)


_DOMAIN_CHECKERS = {
    "amazon.co.jp": _amazon,
    "www.amazon.co.jp": _amazon,
    "yodobashi.com": _yodobashi,
    "www.yodobashi.com": _yodobashi,
    "1999.co.jp": _hobbysearch,
    "www.1999.co.jp": _hobbysearch,
    "p-bandai.jp": _pbandai,
    "premium-bandai.jp": _pbandai,
    "www.p-bandai.jp": _pbandai,
    "www.premium-bandai.jp": _pbandai,
    "gundam-base.net": _gundam_base,
    "www.gundam-base.net": _gundam_base,
    "gundam-side-f.net": _gundam_base,
    "www.gundam-side-f.net": _gundam_base,
    "suruga-ya.jp": _surugaya,
    "www.suruga-ya.jp": _surugaya,
}


def get_status(url: str, html: str) -> str:
    domain = urlparse(url).netloc.lower()
    checker = _DOMAIN_CHECKERS.get(domain, _generic)
    return checker(html)


def extract_price(html: str) -> int | None:
    """ページ内で最初に見つかった、それらしい価格(円)を返す。

    サイトごとの価格欄の場所までは特定していないベストエフォート実装。
    転売・プレミア価格の商品は本文中にも定価が併記されていることがあるため
    完全ではない点に注意（うまく効かない場合は products.yaml の max_price を
    調整するか、ここに個別サイト向けの抽出処理を追加する）。
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    for m in _PRICE_RE.finditer(text):
        raw = m.group(1) or m.group(2)
        if not raw:
            continue
        try:
            value = int(raw.replace(",", ""))
        except ValueError:
            continue
        if 300 <= value <= 300000:
            return value
    return None
