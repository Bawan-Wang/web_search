import re


STOCK_MARKET_KEYWORDS = ("股市", "台股", "加權指數", "大盤", "股票")


def is_stock_price_query(query: str) -> bool:
    return "股價" in query


def is_stock_market_query(query: str) -> bool:
    return any(keyword in query for keyword in STOCK_MARKET_KEYWORDS)


def extract_stock_price_subject(query: str) -> str:
    if not is_stock_price_query(query):
        return ""

    cleaned_query = re.sub(r"[？?，,。.!！]", " ", query)
    cleaned_query = re.sub(
        r"^(今天|現在|請問|幫我|想知道|查一下|查詢|搜尋|請幫我|麻煩幫我)",
        "",
        cleaned_query,
    )
    cleaned_query = re.sub(r"(今天|現在)?(的)?股價.*$", "", cleaned_query).strip()
    return cleaned_query


def build_stock_search_queries(query: str) -> list[str]:
    stock_price_subject = extract_stock_price_subject(query)
    if stock_price_subject:
        return [
            (
                f"{stock_price_subject} 股價 即時 "
                "site:tw.stock.yahoo.com OR site:histock.tw OR site:goodinfo.tw"
            ),
            f"{stock_price_subject} 即時股價 site:tw.stock.yahoo.com OR site:histock.tw",
            f"{stock_price_subject} 股價 site:tw.stock.yahoo.com OR site:histock.tw OR site:goodinfo.tw",
        ]

    if is_stock_market_query(query):
        return ["今天 台股 加權指數 即時 走勢 site:tw.stock.yahoo.com OR site:histock.tw"]

    return []


def is_quote_like_result(text: str) -> bool:
    quote_keywords = ("成交", "開盤", "昨收", "漲跌幅", "最高", "最低", "股價")
    return any(keyword in text for keyword in quote_keywords) and bool(re.search(r"\d[\d,\.]*", text))


def build_stock_price_reply(user_voice_input: str, context: str) -> str:
    if not is_stock_price_query(user_voice_input) or not context:
        return ""

    subject = extract_stock_price_subject(user_voice_input) or "這檔股票"
    price_match = re.search(r"成交[^\d]*(\d[\d,\.]*)", context)
    if not price_match:
        price_match = re.search(r"股價[^\d]*(\d[\d,\.]*)", context)
    high_match = re.search(r"最高[^\d]*(\d[\d,\.]*)", context)
    low_match = re.search(r"最低[^\d]*(\d[\d,\.]*)", context)
    change_match = re.search(r"漲跌幅[^\d-]*([+-]?\d[\d,\.]*%)", context)

    if not price_match:
        return ""

    reply_parts = [f"{subject}目前成交{price_match.group(1)}元"]
    if change_match:
        reply_parts.append(f"漲跌幅{change_match.group(1)}")
    if high_match and low_match:
        reply_parts.append(f"盤中區間約{low_match.group(1)}到{high_match.group(1)}元")
    return "，".join(reply_parts) + "。"