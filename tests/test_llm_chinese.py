# tests/test_llm_chinese.py
"""
Test whether the LLM can identify US stock tickers from Chinese-language news
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.llm_decider import LLMDecider
from app.main import load_cfg


async def main():
    print("\n" + "="*70)
    print("Test LLM Recognition of Chinese Company Names")
    print("="*70)
    
    cfg = load_cfg()
    llm_cfg = cfg.get("llm", {})
    
    llm = LLMDecider(
        api_key=llm_cfg["api_key"],
        base_url=llm_cfg["base_url"],
        model=llm_cfg["model"],
    )
    
    # Test cases - Chinese-language news
    test_cases = [
        {
            "title": "36氪晚报 | 诺基亚与意大利电信达成合作",
            "body": "诺基亚公司宣布与意大利电信签署5G网络建设协议"
        },
        {
            "title": "英伟达发布新一代AI芯片，性能提升10倍",
            "body": "NVIDIA推出H200 GPU，针对数据中心市场"
        },
        {
            "title": "特斯拉Q4交付量创历史新高",
            "body": "特斯拉公司报告第四季度交付量超过分析师预期"
        },
        {
            "title": "苹果公司计划在印度扩大生产",
            "body": "Apple将在印度建立新的iPhone组装工厂"
        },
        {
            "title": "微软Azure云服务增长强劲",
            "body": "Microsoft云计算业务营收同比增长30%"
        },
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n{'='*70}")
        print(f"Test {i}: {case['title']}")
        print('='*70)
        
        try:
            decision = await llm.ask(
                news_title=case['title'],
                news_body=case['body']
            )
            
            print(f"\n✅ LLM response:")
            print(f"  Action: {decision['action']}")
            print(f"  Confidence: {decision['confidence']}")
            print(f"  Symbols: {decision['symbols']}")
            print(f"  Reason: {decision['reason']}")
            
            # Check whether a ticker was identified
            if decision['symbols']:
                print(f"\n✅ Ticker identified: {decision['symbols']}")
            else:
                print(f"\n⚠️  No ticker identified")
                
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        
        await asyncio.sleep(2)  # Avoid rate limiting
    
    print("\n" + "="*70)
    print("Test complete")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())