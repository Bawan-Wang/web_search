import json
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

    def _build_query(self, query: str) -> str:
        """針對常見即時查詢補上更能命中關鍵資訊的搜尋詞。"""
        stock_keywords = ("股市", "台股", "加權指數", "大盤", "股票")
        if any(keyword in query for keyword in stock_keywords):
            return f"{query} 台股 加權指數 即時 盤勢 漲跌"
        return query

    def search(self, query: str) -> str:
        """執行免 API 搜尋並格式化文本"""
        search_chunks = []
        search_query = self._build_query(query)
        cached_result = self._get_cached_result(search_query)
        if cached_result:
            return cached_result

        try:
            # 限制超時，確保語音助理的流暢度
            with DDGS(timeout=self.timeout) as ddgs:
                results = list(
                    ddgs.text(
                        search_query,
                        region=self.region,
                        max_results=self.max_results,
                    )
                )
                
                if not results:
                    return ""

                for idx, r in enumerate(results, 1):
                    # 唯讀取標題與摘要，精簡字數以配合小模型的 Context
                    title = r.get("title", "").strip()
                    body = r.get("body", "").strip()
                    if title or body:
                        search_chunks.append(f"資料源 {idx}: [{title}] - {body}")

            result_text = "\n".join(search_chunks)
            if result_text:
                self._set_cached_result(search_query, result_text)
            return result_text
            
        except Exception as e:
            # 聯網失敗時優雅降級，不讓主程式崩潰
            print(f"[WebSearch 錯誤]: {e}")
            return ""