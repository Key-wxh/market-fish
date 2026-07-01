"""Run v6 pipeline — supports explore/validate/hybrid modes."""
import json, sys, traceback, time, os, argparse
from dotenv import load_dotenv
load_dotenv()

# Fix Windows GBK encoding when piping to file
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from engine.pipeline import Pipeline


def main():
    parser = argparse.ArgumentParser(description="MarketFish Pipeline Runner")
    parser.add_argument("--mode", choices=["explore", "validate", "hybrid"], default="explore",
                        help="Input mode (default: explore)")
    parser.add_argument("--name", help="Product name (for validate/hybrid)")
    parser.add_argument("--description", help="Product description")
    parser.add_argument("--target", default="consumer", help="Target market")
    parser.add_argument("--pricing", default="", help="Pricing")
    parser.add_argument("--pain-point", help="Pain point addressed")
    parser.add_argument("--differentiation", help="What makes it different")
    parser.add_argument("--seed-dir", help="Custom seed data directory (legacy static JSON)")
    parser.add_argument("--seed-source", help="Path to gold seed_snapshot.json (new ingestion pipeline)")
    parser.add_argument("--reuse-agents", action="store_true", help="Load agents from store instead of regenerating")
    parser.add_argument("--sample-strategy", choices=["random", "stratified", "experienced"], default="stratified",
                        help="Agent sampling strategy when reusing (default: stratified)")
    parser.add_argument("--output", default="uploads/latest_result.json", help="Output JSON path")
    args = parser.parse_args()

    # Verify keys
    keys_ok = all(os.getenv(k) for k in ['DEEPSEEK_API_KEY', 'QIANWEN_API_KEY',
                                           'DOUBAO_API_KEY', 'ZHIPU_API_KEY',
                                           'BAIDU_API_KEY', 'HUNYUAN_API_KEY'])
    print(f'API keys: {"OK" if keys_ok else "SOME MISSING"}')
    sys.stdout.flush()

    # Build user product if validate/hybrid mode
    user_product = None
    if args.mode in ("validate", "hybrid"):
        if not args.name:
            print("ERROR: --name is required for validate/hybrid mode")
            sys.exit(1)
        user_product = {
            "name": args.name,
            "description": args.description or args.name,
            "target_market": args.target,
            "pricing": args.pricing,
            "pain_point": args.pain_point or "",
            "differentiation": args.differentiation or "",
        }
        print(f'Mode: {args.mode} | Product: {args.name} | Target: {args.target} | Price: {args.pricing}')

    # Load seed data — prefer gold snapshot, fall back to static JSON
    seed = None  # Let pipeline handle loading
    seed_source = args.seed_source

    if seed_source:
        print(f'Seed source: {seed_source} (gold snapshot)')
    elif args.seed_dir:
        # Legacy mode: load static JSON files
        seed_dir = args.seed_dir or "data"
        seed = {}
        for key in ['freelancer', 'economy', 'tech', 'consumer', 'b2b']:
            path = f'{seed_dir}/seed_{key}.json'
            try:
                with open(path, encoding='utf-8') as f:
                    seed[key] = json.load(f)
            except FileNotFoundError:
                pass
        print(f'Seed: {list(seed.keys())} (legacy static JSON)')
    else:
        # Try gold snapshot first, fall back to static JSON
        gold_path = "data_lake/gold/seed_snapshot.json"
        if os.path.exists(gold_path):
            seed_source = gold_path
            print(f'Seed source: {gold_path} (auto-detected gold snapshot)')
        else:
            print('Seed: legacy static JSON (no gold snapshot found)')

    print(f'Starting pipeline ({args.mode} mode)...')
    sys.stdout.flush()

    pipeline = Pipeline()
    t0 = time.time()

    try:
        result = pipeline.run(seed_data=seed or None, mode=args.mode,
                             user_product=user_product, seed_source=seed_source,
                             reuse_agents=args.reuse_agents,
                             sample_strategy=args.sample_strategy)
        elapsed = time.time() - t0

        os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else '.', exist_ok=True)
        # Sanitize: convert sets in agent_states to lists for JSON
        def _sanitize(obj):
            if isinstance(obj, set): return list(obj)
            if isinstance(obj, dict): return {k: _sanitize(v) for k, v in obj.items()}
            if isinstance(obj, list): return [_sanitize(v) for v in obj]
            return obj
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(_sanitize(result), f, indent=2, ensure_ascii=False)

        status = result.get("pipeline_status", "unknown")
        if status == "error":
            print(f'\n=== PIPELINE FAILED ({elapsed:.0f}s) ===')
            print(f'Failed at: {result.get("failed_at_stage","?")}')
            print(f'Error: {result.get("error","?")}')
            sys.exit(1)

        print(f'\n=== PIPELINE COMPLETE ({elapsed:.0f}s) ===')
        print(f'Stages: {result.get("stages_completed",[])}')

        sim = result.get('stages', {}).get('simulation', {})
        print(f'Results: {sim.get("total_results",0)}')
        print(f'Coupling: {sim.get("cross_domain_coupling",{})}')
        print(f'RL: {sim.get("economic_alignment_rl",{})}')

        report = result.get('final_report', {}).get('synthesis', {})
        if report:
            top = report.get('top_product_direction', {})
            print(f'\nTop: {top.get("name","?")} (score={top.get("survival_score","?")})')
            print(f'Verdict: {report.get("market_verdict","?")[:200]}')
            print(f'Action: {report.get("actionable_recommendation","?")[:200]}')

        sys.stdout.flush()

    except Exception as e:
        traceback.print_exc()
        print(f'\nCRASH at: {pipeline.status}')
        sys.exit(1)


if __name__ == "__main__":
    main()
