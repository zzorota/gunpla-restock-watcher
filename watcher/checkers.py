"""サイトごとの在庫判定ロジック。

各判定関数は "in_stock" / "out_of_stock" / "blocked" / "unknown" のいずれかを返す。
サイトのHTML構造が変わって判定がおかしくなった場合は、ここのキーワードや
セレクタを調整してください。
"""

from urllib.parse import urlparse

from bs4 import BeautifulSoup

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
}


def get_status(url: str, html: str) -> str:
    domain = urlparse(url).netloc.lower()
    checker = _DOMAIN_CHECKERS.get(domain, _generic)
    return checker(html)
