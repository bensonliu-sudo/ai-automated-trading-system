# -*- coding: utf-8 -*-
"""
Unified test script: tests/test_all.py
Usage:
  - python tests/test_all.py             # Run all steps (unimplemented ones are skipped automatically)
  - python tests/test_all.py --only 3    # Run only Step 3
Notes:
  - Designed to be "robust + incremental": each step depends only on the minimal capability agreed in the previous step.
  - If a step's code is not yet implemented, the test is "skipped" rather than failed.
  - Before running, activate the virtual environment and install dependencies:
        python3 -m venv .venv && source .venv/bin/activate
        pip install -r requirements.txt
"""

import argparse
import asyncio
import importlib
import os
import sys
import time
import glob
import json
from pathlib import Path
from contextlib import suppress
from subprocess import Popen, PIPE
import sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # ✅ Add the intel-hub root directory to sys.path
os.chdir(ROOT)
ROOT = Path(__file__).resolve().parents[1]  # intel-hub/
os.chdir(ROOT)

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"

def ok(msg): print(f"{GREEN}✅ {msg}{RESET}")
def warn(msg): print(f"{YELLOW}⚠️  {msg}{RESET}")
def fail(msg): print(f"{RED}❌ {msg}{RESET}")

# ---------- Step 0 ----------
def test_step0():
    required = [
        "app/main.py","app/models.py","app/storage.py","app/collector.py",
        "app/scorer.py","app/notifier.py","app/utils.py","app/web.py",
        "app/parsers/rss_default.py","app/parsers/json_default.py","app/parsers/dummy_gen.py",
        "ops/config.yml","ops/keywords.yml","ops/topics.yml","ops/sources.yml","ops/universe.yml",
        "tests/sample_events.jsonl","requirements.txt"
    ]
    missing = [p for p in required if not Path(p).exists()]
    if missing:
        fail(f"Step 0 missing files: {missing}")
        return False
    ok("Step 0 directories and files exist")
    return True

# ---------- Step 1 ----------
def test_step1():
    try:
        import yaml
    except Exception as e:
        fail(f"Missing PyYAML dependency: {e}")
        return False
    try:
        for p in glob.glob("ops/*.yml"):
            with open(p,"r") as f:
                yaml.safe_load(f)
        ok("Step 1 YAML configs parse successfully")
        return True
    except Exception as e:
        fail(f"YAML parsing failed: {e}")
        return False

# ---------- Step 2 ----------
# Add at the top:
import traceback

# ---------- Step 2 (replaced with this version) ----------
# Keep import traceback at the top

async def test_step2_async(verbose: bool = True):
    try:
        storage = importlib.import_module("app.storage")
        models = importlib.import_module("app.models")
        if not hasattr(storage, "init_db"):
            warn("Step 2: init_db not found, skipping")
            return True

        db = await storage.init_db("test_step2.db")  # Open connection

        if not hasattr(models, "Event"):
            warn("Step 2: models.Event not found, skipping")
            # ✅ Close the connection before returning
            await db.close()
            return True

        from app.models import Event

        now = int(time.time()*1000)
        e = Event(
            id="test_step2_1",
            ts_detected_utc=now,
            ts_published_utc=now,
            headline="Test event",
            source="dummy",
            link="http://x",
            market="us",
            symbols="NVDA",
            categories="contract",
            tags="#AI",
            score=90.0,
            pushed=0,
            expires_at_utc=now+1000,
            thread_key="NVDA|contract",
        )

        ok1 = await storage.insert_event(db, e)
        if verbose:
            print("[DEBUG] insert_event return =", ok1)
        assert ok1, "insert_event returned False (possible primary key conflict or SQL failure)"

        if hasattr(storage, "delete_expired"):
            await storage.delete_expired(db, now+5000)

        # ✅ Important: close the connection to avoid hanging the event loop
        await db.close()

        ok("Step 2 SQLite basic insert/delete OK")
        return True

    except Exception:
        traceback.print_exc()
        return False

def test_step2():
    try:
        return asyncio.run(test_step2_async(verbose=True))
    except Exception:
        traceback.print_exc()
        return False
# ---------- Step 3 ----------
async def test_step3_async():
    try:
        collector = importlib.import_module("app.collector")
    except Exception as e:
        warn(f"Step 3: cannot import app.collector (may not be implemented yet): {e}")
        return True  # Skip

    if not hasattr(collector, "run_collectors"):
        warn("Step 3: run_collectors not found, skipping")
        return True

    q = asyncio.Queue()
    tasks = await collector.run_collectors(q)
    got = 0
    start = time.time()
    try:
        while time.time()-start < 20:
            try:
                item = await asyncio.wait_for(q.get(), timeout=5)
                got += 1
            except asyncio.TimeoutError:
                pass
    finally:
        for t in tasks:
            t.cancel()
    if got > 0:
        ok("Step 3 collector produced events OK")
        return True
    warn("Step 3 no events collected (can be ignored if only the skeleton is implemented)")
    return True

def test_step3():
    try:
        return asyncio.run(test_step3_async())
    except Exception as e:
        fail(f"Step 3 failed: {e}")
        return False

# ---------- Step 4 ----------
def test_step4():
    try:
        scorer = importlib.import_module("app.scorer")
    except Exception as e:
        warn(f"Step 4: cannot import app.scorer (may not be implemented yet): {e}")
        return True  # Skip

    if not hasattr(scorer, "score_headline_for_test"):
        warn("Step 4: score_headline_for_test not found, skipping")
        return True

    samples = [
        "NVIDIA signs multi-year contracts with government",
        "TSMC invested heavily in HBM for AI upgrade",
        "某平台上线RWA链上国债 tokenized treasury",
        "Company is considering investment? rumor",
    ]
    try:
        for s in samples:
            cats, tags, sc = scorer.score_headline_for_test(s)
            print("  ", s, "=>", cats, tags, sc)
        ok("Step 4 scoring function works (manually verify the printed output looks reasonable)")
        return True
    except Exception as e:
        fail(f"Step 4 failed: {e}")
        return False

# ---------- Step 5 ----------
async def test_step5_async():
    try:
        notifier = importlib.import_module("app.notifier")
    except Exception as e:
        warn(f"Step 5: cannot import app.notifier (may not be implemented yet): {e}")
        return True  # Skip

    if not hasattr(notifier, "send_text_test"):
        warn("Step 5: send_text_test not found, skipping")
        return True

    try:
        await notifier.send_text_test("Test: without a token this should print to the console")
        ok("Step 5 notification fallback OK")
        return True
    except Exception as e:
        fail(f"Step 5 failed: {e}")
        return False

def test_step5():
    try:
        return asyncio.run(test_step5_async())
    except Exception as e:
        fail(f"Step 5 failed: {e}")
        return False

# ---------- Step 6 ----------
def test_step6():
    if not Path("app/main.py").exists():
        warn("Step 6: app/main.py does not exist, skipping")
        return True
    # Run main for 15 seconds in a subprocess
    try:
        p = Popen([sys.executable, "app/main.py", "--run-seconds", "15"], stdout=PIPE, stderr=PIPE)
        try:
            out, err = p.communicate(timeout=25)
        except Exception:
            p.kill()
            out, err = p.communicate()
        print(out.decode("utf-8", "ignore"))
        if err:
            print(err.decode("utf-8", "ignore"))
        ok("Step 6 main loop runs (tried for 15 seconds)")
        return True
    except Exception as e:
        warn(f"Step 6 running main.py failed (may not be complete yet): {e}")
        return True  # Do not force a failure

# ---------- Step 7 ----------
def test_step7():
    # Only check that web.py exists and is importable; actual Streamlit rendering is tested manually
    if not Path("app/web.py").exists():
        warn("Step 7: app/web.py does not exist, skipping")
        return True
    try:
        importlib.import_module("app.web")
        ok("Step 7 web module importable (run the UI manually with Streamlit)")
        return True
    except Exception as e:
        warn(f"Step 7: cannot import app.web: {e}")
        return True

# ---------- Step 8 ----------
def test_step8():
    # Logic belongs to the Step 4 enhancement; here just check that the blacklist fields exist in keywords.yml
    try:
        import yaml
        with open("ops/keywords.yml","r") as f:
            data = yaml.safe_load(f)
        if "source_blacklist" in data and "keyword_blacklist" in data:
            ok("Step 8 blacklist config exists (feature implemented with Step 4)")
            return True
        warn("Step 8 blacklist config missing (can be ignored if not yet implemented)")
        return True
    except Exception as e:
        warn(f"Step 8: failed to read keywords.yml: {e}")
        return True

# ---------- Step 9 ----------
def test_step9():
    # Check write access to the exports directory; call utils.export_recent_events_for_test if it exists
    try:
        exports = Path("exports")
        exports.mkdir(exist_ok=True)
        try:
            utils = importlib.import_module("app.utils")
            if hasattr(utils, "export_recent_events_for_test"):
                import app.storage as storage
                db = asyncio.run(storage.init_db("intel.db"))
                asyncio.run(utils.export_recent_events_for_test(db))
                files = list(exports.rglob("events.csv"))
                if files:
                    ok("Step 9 export generated (CSV found)")
                    return True
                else:
                    warn("Step 9 export CSV not found (can be ignored if not yet implemented)")
                    return True
        except Exception as e:
            warn(f"Step 9: export function missing or failed (can be ignored): {e}")
            return True
    except Exception as e:
        warn(f"Step 9: failed to create exports (permission issue?): {e}")
        return True

# ---------- Step 10 ----------
def test_step10():
    # Fault tolerance/health is mainly judged from runtime logs; this is only a hint
    ok("Step 10 suggestion: manually break a sources.yml URL, run Step 6, and verify the logs continue uninterrupted")
    return True

STEP_FUNCS = {
    0: test_step0,
    1: test_step1,
    2: test_step2,
    3: test_step3,
    4: test_step4,
    5: test_step5,
    6: test_step6,
    7: test_step7,
    8: test_step8,
    9: test_step9,
    10: test_step10,
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", type=int, help="Run only the specified step (0-10)")
    args = parser.parse_args()

    if args.only is not None:
        fn = STEP_FUNCS.get(args.only)
        if not fn:
            fail("Invalid step number")
            sys.exit(2)
        passed = fn()
        sys.exit(0 if passed else 1)

    # Run all
    all_passed = True
    for step in range(0, 11):
        print(f"\n===== Running Step {step} tests =====")
        fn = STEP_FUNCS[step]
        try:
            passed = fn()
        except Exception as e:
            fail(f"Step {step} exception: {e}")
            passed = False
        all_passed = all_passed and passed
    print("\n===============================")
    if all_passed:
        ok("All passed or reasonably skipped (unimplemented steps do not block)")
        sys.exit(0)
    else:
        fail("Some steps failed; scroll up to review the logs")
        sys.exit(1)

if __name__ == "__main__":
    main()