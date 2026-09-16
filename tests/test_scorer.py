# tests/test_scorer.py
# Offline check of the keyword/topic scorer via its test hook.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.scorer import score_headline_for_test

SAMPLES = [
    "NVIDIA wins $2B data-center contract, raises guidance",
    "Company is considering investment? rumor",
    "Federal Reserve holds rates steady",
    "中国启动对半导体产品反倾销调查，或影响高端GPU进口",
]

def main() -> None:
    for headline in SAMPLES:
        category, tags, score = score_headline_for_test(headline)
        assert isinstance(category, str) and isinstance(score, (int, float)), headline
        print(f"{score:>7.1f}  {category:<10} {tags!s:<30} {headline}")
    print("OK")

if __name__ == "__main__":
    main()
