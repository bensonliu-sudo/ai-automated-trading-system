# tests/diagnose_llm_api.py
"""
Diagnose LLM API connection issues
"""
import asyncio
import httpx
import yaml
import json
from pathlib import Path


async def test_api_connection(api_key, base_url, model):
    """Test basic API connectivity"""
    print("\n" + "="*70)
    print("Test 1: Basic API connectivity")
    print("="*70)
    
    print(f"Base URL: {base_url}")
    print(f"Model: {model}")
    print(f"API Key: {api_key[:20]}..." if api_key else "None")
    
    if not api_key:
        print("❌ API key not configured")
        return False
    
    # Send a simple test request
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            print("\nSending test request...")
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": "Say 'test' in JSON: {\"result\": \"test\"}"
                        }
                    ],
                    "max_tokens": 50,
                    "temperature": 0.1,
                }
            )
            
            print(f"Status code: {resp.status_code}")
            
            if resp.status_code == 200:
                data = resp.json()
                print("✅ API connection succeeded")
                print(f"Response: {json.dumps(data, indent=2)[:200]}...")
                return True
            else:
                print(f"❌ API returned an error: {resp.status_code}")
                print(f"Response body: {resp.text[:500]}")
                return False
                
    except httpx.TimeoutException:
        print("❌ Request timed out")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


async def test_model_availability(api_key, base_url):
    """Test listing available models"""
    print("\n" + "="*70)
    print("Test 2: Fetch available models")
    print("="*70)
    
    try:
        # Groq model list endpoint
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{base_url.replace('/chat/completions', '')}/models",
                headers={
                    "Authorization": f"Bearer {api_key}",
                }
            )
            
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("data", [])
                print(f"✅ Found {len(models)} available models:")
                for m in models[:10]:  # Show only the first 10
                    model_id = m.get("id", "unknown")
                    print(f"  - {model_id}")
                return True
            else:
                print(f"⚠️  Unable to fetch model list: {resp.status_code}")
                return False
                
    except Exception as e:
        print(f"⚠️  Failed to fetch model list: {e}")
        return False


async def test_rate_limits(api_key, base_url, model):
    """Test rate limits"""
    print("\n" + "="*70)
    print("Test 3: Rate limit check")
    print("="*70)
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Send 3 requests back to back
            for i in range(3):
                print(f"\nRequest {i+1}/3...")
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "test"}],
                        "max_tokens": 10,
                    }
                )
                
                print(f"  Status code: {resp.status_code}")
                
                if resp.status_code == 429:
                    print("⚠️  Rate limit triggered")
                    return False
                elif resp.status_code != 200:
                    print(f"⚠️  Error: {resp.status_code}")
                    
                await asyncio.sleep(1)  # 1-second interval
            
            print("\n✅ Rate limit test passed")
            return True
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


async def test_with_trading_prompt(api_key, base_url, model):
    """Test with the real trading prompt"""
    print("\n" + "="*70)
    print("Test 4: Real trading prompt")
    print("="*70)
    
    prompt = """You are a US stock quantitative trading AI. Based on the news, decide if a stock is worth trading.

Output ONLY a JSON object with these fields:
- "action": "buy" / "sell" / "hold"
- "confidence": 0-100 (trading confidence score)
- "symbols": ["AAPL", "TSLA"] (US stock tickers involved)
- "reason": one sentence explaining why

News Title: NVIDIA announces breakthrough AI chip with 10x performance gains
News Body: The new H200 GPU is expected to drive strong demand among datacenter clients.

CRITICAL: Your ENTIRE response must be ONLY valid JSON. Do NOT include any other text.
Start with { and end with }.

Example:
{"action": "buy", "confidence": 85, "symbols": ["NVDA"], "reason": "Strong AI chip demand"}
"""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            print("Sending trading decision request...")
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a trading assistant. You MUST respond with ONLY valid JSON."
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                    "temperature": 0.2,
                    "max_tokens": 200,
                }
            )
            
            print(f"Status code: {resp.status_code}")
            
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                print(f"\nRaw response:\n{content}\n")
                
                # Try to parse JSON
                import re
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group())
                        print(f"✅ Parsed JSON successfully: {result}")
                        return True
                    except:
                        print(f"⚠️  Found JSON but failed to parse it")
                else:
                    print(f"⚠️  No JSON found in response")
                
            else:
                print(f"❌ API error: {resp.status_code}")
                print(f"Response: {resp.text[:500]}")
                return False
                
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all diagnostics"""
    ROOT = Path(__file__).resolve().parents[1]
    cfg_path = ROOT / "ops" / "config.yml"
    
    print("\n" + "="*70)
    print("LLM API Diagnostic Tool")
    print("="*70)
    
    # Load configuration
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
        llm_cfg = cfg.get("llm", {})
    except Exception as e:
        print(f"❌ Unable to load configuration: {e}")
        return
    
    api_key = llm_cfg.get("api_key")
    base_url = llm_cfg.get("base_url")
    model = llm_cfg.get("model")
    
    print(f"\nCurrent configuration:")
    print(f"  Base URL: {base_url}")
    print(f"  Model: {model}")
    print(f"  API Key: {'set' if api_key else 'not set'}")
    
    if not api_key:
        print("\n❌ Error: API key not configured")
        print("Set llm.api_key in ops/config.yml")
        return
    
    # Run tests
    results = {}
    
    print("\n" + "="*70)
    print("Starting diagnostics...")
    print("="*70)
    
    # Test 1: Basic connectivity
    results["Basic connectivity"] = await test_api_connection(api_key, base_url, model)
    
    if results["Basic connectivity"]:
        # Test 2: Model availability
        results["Model list"] = await test_model_availability(api_key, base_url)
        
        # Test 3: Rate limits
        results["Rate limits"] = await test_rate_limits(api_key, base_url, model)
        
        # Test 4: Real prompt
        results["Trading prompt"] = await test_with_trading_prompt(api_key, base_url, model)
    
    # Summary
    print("\n" + "="*70)
    print("Diagnostic summary")
    print("="*70)
    
    for name, passed in results.items():
        status = "✅ Passed" if passed else "❌ Failed"
        print(f"{status} - {name}")
    
    # Recommendations
    print("\n" + "="*70)
    print("Recommendations")
    print("="*70)
    
    if not results.get("Basic connectivity"):
        print("\n🔧 Basic connectivity failed. Possible causes:")
        print("  1. API key invalid or expired")
        print("     → Get a new API key at https://console.groq.com/keys")
        print("  2. Incorrect model name")
        print(f"     → Current model: {model}")
        print("     → Common models: llama-3.3-70b-versatile, llama-3.1-70b-versatile")
        print("  3. Incorrect base URL")
        print(f"     → Current: {base_url}")
        print("     → Should be: https://api.groq.com/openai/v1")
        print("  4. Network issue")
        print("     → Check firewall/proxy settings")
        print("  5. Groq server issue")
        print("     → Check service status at https://status.groq.com")
    
    elif not results.get("Rate limits"):
        print("\n⚠️  Rate limit triggered. Recommendations:")
        print("  1. Reduce request frequency")
        print("  2. Add delays between requests")
        print("  3. Consider upgrading to a paid plan")
    
    elif not results.get("Trading prompt"):
        print("\n⚠️  Trading prompt test failed. Recommendations:")
        print("  1. Simplify the prompt")
        print("  2. Lower the temperature")
        print("  3. Try a different model")


if __name__ == "__main__":
    asyncio.run(main())