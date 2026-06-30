"""Run v4 pipeline and save results."""
import json, sys, traceback, time, os
from dotenv import load_dotenv
load_dotenv()

# Verify keys
keys_ok = all(os.getenv(k) for k in ['DEEPSEEK_API_KEY','QIANWEN_API_KEY','DOUBAO_API_KEY',
                                       'ZHIPU_API_KEY','BAIDU_API_KEY','HUNYUAN_API_KEY'])
print(f'API keys: {"OK" if keys_ok else "MISSING"}')
sys.stdout.flush()

from engine.pipeline import Pipeline

# Load seed
seed = {}
for key in ['freelancer', 'economy', 'tech', 'consumer', 'b2b']:
    with open(f'data/seed_{key}.json', encoding='utf-8') as f:
        seed[key] = json.load(f)

print(f'Seed: {list(seed.keys())}')
print(f'Starting v4 pipeline...')
sys.stdout.flush()

pipeline = Pipeline()
t0 = time.time()

try:
    result = pipeline.run(seed)
    elapsed = time.time() - t0

    with open('uploads/latest_v4.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    status = result.get("pipeline_status", "unknown")
    if status == "error":
        print(f'\n=== PIPELINE FAILED ({elapsed:.0f}s) ===')
        print(f'Failed at: {result.get("failed_at_stage","?")}')
        print(f'Error: {result.get("error","?")}')
        print(f'Completed stages: {result.get("stages_completed",[])}')
        sys.exit(1)

    print(f'\n=== V4 PIPELINE COMPLETE ({elapsed:.0f}s) ===')
    print(f'Stages: {result.get("stages_completed",[])}')

    sim = result.get('stages', {}).get('simulation', {})
    print(f'Results: {sim.get("total_results",0)}')
    print(f'Coupling: {sim.get("cross_domain_coupling",{})}')
    print(f'RL: {sim.get("economic_alignment_rl",{})}')

    report = result.get('final_report', {}).get('synthesis', {})
    if report:
        top = report.get('top_product_direction', {})
        print(f'\nTop Product: {top.get("name","?")} (score={top.get("survival_score","?")})')
        print(f'Market Verdict: {report.get("market_verdict","?")[:200]}')
        print(f'Recommendation: {report.get("actionable_recommendation","?")[:200]}')

    sys.stdout.flush()

except Exception as e:
    traceback.print_exc()
    print(f'\nCRASH at: {pipeline.status}')
    sys.exit(1)
