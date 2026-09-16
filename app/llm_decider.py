# app/llm_decider.py

import os
import json
import re
import httpx

class LLMDecider:
    def __init__(self, api_key=None, base_url=None, model=None):
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.base_url = base_url or os.getenv("LLM_BASE_URL")
        self.model = model or os.getenv("LLM_MODEL", "deepseek-chat")

    def _extract_json(self, text: str) -> dict:
        """
        Extract JSON from an LLM response; supports several formats:
        1. Plain JSON
        2. ```json ... ```
        3. ``` ... ```
        4. Mixed text + JSON
        """
        if not text or not text.strip():
            raise ValueError("LLM return empty")
        
        text = text.strip()
        
        # Method 1: if it starts with {, try parsing directly
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass  # fall through to other methods
        
        # Method 2: extract a markdown code block
        # Match ```json ... ``` or ``` ... ```
        code_block_pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
        matches = re.findall(code_block_pattern, text, re.DOTALL)
        
        if matches:
            for match in matches:
                match = match.strip()
                if match.startswith("{"):
                    try:
                        return json.loads(match)
                    except json.JSONDecodeError:
                        continue
        
        # Method 3: find the first { and the last }
        start = text.find("{")
        end = text.rfind("}")
        
        if start != -1 and end != -1 and start < end:
            json_str = text[start:end+1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        
        # Method 4: scan line by line for JSON
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        
        # All methods failed
        raise ValueError(f"couldn't get JSON. Original response:\n{text}")

    async def ask(self, news_title: str, news_body: str = ""):
        """
        Ask the LLM for a trading decision
        """
        prompt = f"""You are a US stock quantitative trading AI. Analyze this news (may be in Chinese/English) and decide if any stocks are worth trading.

News Title: {news_title}
News Body: {news_body or "N/A"}

CRITICAL INSTRUCTIONS:
1. **Extract ALL companies mentioned** (even if just in passing):
   - Chinese names: 诺基亚→NOK, 英伟达→NVDA, 特斯拉→TSLA, 苹果→AAPL, 微软→MSFT, 
     亚马逊→AMZN, 谷歌→GOOGL, Meta→META, 阿里巴巴→BABA, 腾讯→TCEHY
   - English names: NVIDIA→NVDA, Tesla→TSLA, Apple→AAPL, etc.

2. **Always include symbols[]** even if you recommend "hold":
   - If news mentions NVIDIA partnership → symbols: ["NVDA"]  
   - If news mentions "诺基亚与意大利电信" → symbols: ["NOK"]
   - Even if action is "hold", still extract the symbols!

3. Trading decision:
   - "buy" if positive news (growth, partnership, earnings beat, innovation)
   - "sell" if negative news (lawsuit, loss, downgrade, scandal)
   - "hold" if neutral or insufficient info to trade

4. Confidence: 0-100 (how strong is the signal)

Output ONLY this JSON (no other text):
{{"action": "buy/sell/hold", "confidence": 0-100, "symbols": ["TICKER1", "TICKER2"], "reason": "brief reason"}}

Examples:
- News: "NVIDIA announces new AI chip" → {{"action": "buy", "confidence": 85, "symbols": ["NVDA"], "reason": "New product launch"}}
- News: "诺基亚与意大利电信达成5G合作" → {{"action": "buy", "confidence": 65, "symbols": ["NOK"], "reason": "5G partnership deal"}}
- News: "特斯拉召回部分车辆" → {{"action": "sell", "confidence": 60, "symbols": ["TSLA"], "reason": "Vehicle recall"}}
""".strip()

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": self.model,
                            "messages": [
                                {
                                    "role": "system",
                                    "content": "You are a trading AI. You MUST respond with ONLY valid JSON. ALWAYS include symbols[] array even for hold decisions.",
                                },
                                {
                                    "role": "user",
                                    "content": prompt,
                                },
                            ],
                            "temperature": 0.2,
                        },
                    )
            
            # Check HTTP status
            if resp.status_code != 200:
                raise RuntimeError(f"LLM API error: status={resp.status_code}, response={resp.text}")
            
            data = resp.json()
            print(f"[LLM] raw response status: {resp.status_code}")
            
            # Check API response format
            if "error" in data:
                raise RuntimeError(f"LLM API return error: {data['error']}")
            
            if "choices" not in data or not data["choices"]:
                raise RuntimeError(f"LLM response format error: {data}")
            
            # Get content
            content = data["choices"][0]["message"]["content"]
            print(f"[LLM] raw content: {repr(content[:200])}...")  # print only the first 200 characters
            
            # Extract JSON
            result = self._extract_json(content)
            
            # Validate required fields
            required_fields = ["action", "confidence", "symbols"]
            missing_fields = [f for f in required_fields if f not in result]
            
            if missing_fields:
                print(f"[LLM] ⚠️  warning: missing {missing_fields}, using defaults")
                # Fill in defaults
                if "action" not in result:
                    result["action"] = "hold"
                if "confidence" not in result:
                    result["confidence"] = 0
                if "symbols" not in result:
                    result["symbols"] = []
                if "reason" not in result:
                    result["reason"] = "Unknown"
            
            # Normalize fields
            result["action"] = str(result["action"]).lower()
            result["confidence"] = int(result["confidence"])
            
            if not isinstance(result["symbols"], list):
                result["symbols"] = [result["symbols"]] if result["symbols"] else []
            
            print(f"[LLM] ✓ parsed decision: {result}")
            return result
            
        except httpx.TimeoutException:
            print("[LLM] ❌ request out of time")
            # Return a conservative default decision
            return {
                "action": "hold",
                "confidence": 0,
                "symbols": [],
                "reason": "LLM timeout"
            }
        except Exception as e:
            print(f"[LLM] ❌ error: {e}")
            # Return a conservative default decision
            return {
                "action": "hold",
                "confidence": 0,
                "symbols": [],
                "reason": f"LLM error: {str(e)[:50]}"
            }