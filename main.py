import os
import re
import time
import ollama
from web_search_agent import WebSearchAgent

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")

# 初始化搜尋模組
search_agent = WebSearchAgent(max_results=2, timeout=4)


def build_stock_price_reply(user_voice_input: str, context: str) -> str:
    if "股價" not in user_voice_input or not context:
        return ""

    subject = re.sub(r"[？?，,。.!！]", " ", user_voice_input)
    subject = re.sub(r"^(今天|現在|請問|幫我|想知道|查一下|查詢|搜尋|請幫我|麻煩幫我)", "", subject)
    subject = re.sub(r"(今天|現在)?(的)?股價.*$", "", subject).strip() or "這檔股票"

    price_match = re.search(r"(?:成交|股價)[^\d]*(\d[\d,\.]*)", context)
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

def voice_assistant_pipeline(user_voice_input: str):
    """語音助理的核心對話管線"""
    
    # 1. 關鍵字簡單判斷（或者你也可以讓小模型自己決定要不要聯網）
    need_web = any(k in user_voice_input for k in ["搜尋", "今天", "天氣", "最新", "現在", "新聞", "股票", "股價", "即時"])
    
    context = ""
    if need_web:
        print(" [系統提示] 偵測到即時性問題，正在觸發免 API 網路搜尋...")
        # 這裡可以直接把使用者的話當關鍵字，或者做簡單的文字清洗
        context = search_agent.search(user_voice_input)

    stock_price_reply = build_stock_price_reply(user_voice_input, context)
    if stock_price_reply:
        return stock_price_reply
    
    # 2. 打造適合「語音助理」的 System Prompt（要求短小精悍、口語化）
    system_prompt = (
        "你是一個親切的語音助理。請用繁體中文回答，口吻要自然、像人在說話一樣。\n"
        "【重要】請限制在 50 字以內回答，不要條列式，不要使用 Markdown 符號（如 **、* 或 #）。\n"
    )
    
    if context:
        system_prompt += f"請參考以下最新網路即時資訊來回答問題：\n{context}"
    else:
        system_prompt += "請用你既有的知識回答即可。"

    # 3. 呼叫本地端模型 (例如 llama3、gemma 或 misral)
    client = ollama.Client()
    try:
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_voice_input}
            ],
            options={"temperature": 0, "seed": 42} # 固定取樣，降低同樣上下文時的回答漂移
        )
        
        reply = response['message']['content']
        return reply

    except Exception as e:
        return f"模型生成失敗，錯誤原因: {e}"
    finally:
        client.close()

# --- 測試模擬 ---
if __name__ == "__main__":
    # 模擬語音轉文字 (STT) 後的輸入
    test_question = "查今天台北到台中高鐵時間？"
    
    start_time = time.time()
    ai_reply = voice_assistant_pipeline(test_question)
    end_time = time.time()
    
    print("\n==============================")
    print(f"使用者說: {test_question}")
    print(f"助理回答: {ai_reply}")
    print(f"總耗時: {end_time - start_time:.2f} 秒")
    print("==============================")