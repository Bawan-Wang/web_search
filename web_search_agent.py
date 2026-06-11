import json
import re
import time
from pathlib import Path

from ddgs import DDGS

class WebSearchAgent:
    def __init__(self, max_results=3, timeout=5, region="tw-tpe", cache_ttl=300):
        """
        :param max_results: 回傳的搜尋結果數量，語音助理建議 2~3 個即可
        :param timeout: 搜尋超時時間（秒），防止網路卡住導致語音助理沒反應
        :param region: 搜尋區域，預設鎖定台灣以提升在地即時資訊品質
        :param cache_ttl: 相同查詢的快取秒數，降低短時間重跑時的結果漂移
        """
        self.max_results = max_results
        self.timeout = timeout
        self.region = region
        self.cache_ttl = cache_ttl
        self.cache_path = Path(__file__).with_name(".web_search_cache.json")

    def _load_cache(self) -> dict:
        if not self.cache_path.exists():
            return {}

        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_cache(self, cache: dict) -> None:
        try:
            self.cache_path.write_text(
                json.dumps(cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _get_cached_result(self, search_query: str) -> str:
        cache = self._load_cache()
        entry = cache.get(search_query)
        if not entry:
            return ""

        expires_at = entry.get("expires_at", 0)
        if expires_at < time.time():
            cache.pop(search_query, None)
            self._save_cache(cache)
            return ""

        return entry.get("result", "")

    def _set_cached_result(self, search_query: str, result: str) -> None:
        cache = self._load_cache()
        cache[search_query] = {
            "expires_at": time.time() + self.cache_ttl,
            "result": result,
        }
        self._save_cache(cache)

    def _build_queries(self, query: str) -> list[str]:
        """針對常見即時查詢建立較穩定的候選搜尋詞。"""
        stock_price_subject = self._extract_stock_price_subject(query)
        if stock_price_subject:
            return [
                (
                    f"{stock_price_subject} 股價 即時 "
                    "site:tw.stock.yahoo.com OR site:histock.tw OR site:goodinfo.tw"
                ),
                f"{stock_price_subject} 即時股價 site:tw.stock.yahoo.com OR site:histock.tw",
                f"{stock_price_subject} 股價 site:tw.stock.yahoo.com OR site:histock.tw OR site:goodinfo.tw",
            ]

        stock_keywords = ("股市", "台股", "加權指數", "大盤", "股票")
        if any(keyword in query for keyword in stock_keywords):
            return ["今天 台股 加權指數 即時 走勢 site:tw.stock.yahoo.com OR site:histock.tw"]
        return [query]

    def _extract_stock_price_subject(self, query: str) -> str:
        if "股價" not in query:
            return ""

        cleaned_query = re.sub(r"[？?，,。.!！]", " ", query)
        cleaned_query = re.sub(
            r"^(今天|現在|請問|幫我|想知道|查一下|查詢|搜尋|請幫我|麻煩幫我)",
            "",
            cleaned_query,
        )
        cleaned_query = re.sub(r"(今天|現在)?(的)?股價.*$", "", cleaned_query).strip()
        return cleaned_query

    def _is_quote_like_result(self, text: str) -> bool:
        quote_keywords = ("成交", "開盤", "昨收", "漲跌幅", "最高", "最低", "股價")
        return any(keyword in text for keyword in quote_keywords) and bool(re.search(r"\d[\d,\.]*", text))

    def search(self, query: str) -> str:
        """執行免 API 搜尋並格式化文本"""
        search_chunks = []
        cache_key = query.strip()
        search_queries = self._build_queries(query)
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            print(" [WebSearch] 使用快取結果")
            return cached_result

        try:
            # 限制超時，確保語音助理的流暢度
            with DDGS(timeout=self.timeout) as ddgs:
                for search_query in search_queries:
                    print(f" [WebSearch] 正在搜尋: {search_query}")
                    results = list(
                        ddgs.text(
                            search_query,
                            region=self.region,
                            max_results=max(self.max_results, 3),
                        )
                    )

                    if not results:
                        continue

                    filtered_results = []
                    stock_price_subject = self._extract_stock_price_subject(query)
                    for result in results:
                        title = result.get("title", "").strip()
                        body = result.get("body", "").strip()
                        text = f"{title} {body}"
                        if stock_price_subject and not self._is_quote_like_result(text):
                            continue
                        filtered_results.append(result)

                    chosen_results = filtered_results if filtered_results else results[: self.max_results]
                    search_chunks = []
                    for idx, result in enumerate(chosen_results[: self.max_results], 1):
                        title = result.get("title", "").strip()
                        body = result.get("body", "").strip()
                        if title or body:
                            search_chunks.append(f"資料源 {idx}: [{title}] - {body}")

                    result_text = "\n".join(search_chunks)
                    if stock_price_subject and not filtered_results:
                        continue
                    if result_text:
                        self._set_cached_result(cache_key, result_text)
                        return result_text

            return ""
            
        except Exception as e:
            # 聯網失敗時優雅降級，不讓主程式崩潰
            print(f"[WebSearch 錯誤]: {e}")
            return ""