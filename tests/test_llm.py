# tests/test_llm.py
import asyncio
from app.llm_decider import LLMDecider
from app.main import load_cfg

async def main():
    cfg = load_cfg()
    llm_cfg = cfg["llm"]

    llm = LLMDecider(
        api_key=llm_cfg["api_key"],
        base_url=llm_cfg["base_url"],
        model=llm_cfg["model"],
    )

    result = await llm.ask(
        news_title="NVIDIA announces new AI GPU H200 with 2x performance gains",
        news_body="The new GPU is expected to drive strong demand among datacenter clients."
    )

    print("LLM result:")
    print(result)

asyncio.run(main())