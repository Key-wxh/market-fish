#!/usr/bin/env python3
"""
Agent Learning Verification — ruflo Verification Gate 模式

在学习管线后运行：抽样10个Agent → 提问测试 → 检查回答质量 → 标记异常Agent。
如果超过30%的Agent验证失败，阻止后续管线（debate/trend）继续。

用法: python3 agent_verify.py [--sample 10] [--threshold 0.3]
cron: agent_learn && agent_consensus && agent_verify && agent_debate
"""
import json, os, sys, time, random, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ = timezone(timedelta(hours=8))
DS_KEY = os.getenv("DEEPSEEK_API_KEY", "")

ROOT = Path(__file__).parent.parent
AGENT_DIR = ROOT / "data_lake" / "gold" / "agents"
FLAG_FILE = ROOT / "data_lake" / "gold" / "verify_flags.json"

# Test questions by agent type (domain-specific verification)
TEST_QUESTIONS = {
    "default": "用一句话描述你最近学到的最重要的东西。",
    "投资者": "当前市场环境下，你最关注的风险因素是什么？",
    "分析师": "基于你最近的学习，最重要的市场趋势是什么？",
    "工程师": "最近技术领域最大的变化是什么？",
    "创业者": "当前创业环境中最值得注意的变化是什么？",
    "消费者": "你最近注意到的消费习惯变化是什么？",
}

def call_deepseek(prompt: str, max_tokens: int = 200) -> str:
    if not DS_KEY:
        return ""
    body = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens, "temperature": 0.3,
    }).encode()
    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {DS_KEY}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"]

def verify_agent(agent: dict) -> dict:
    """Test a single agent and return verification result."""
    profile = agent.get("profile", agent)
    agent_type = profile.get("type", "default")
    name = profile.get("name", "?")
    beliefs = profile.get("bdi", {}).get("beliefs", [])

    # Select test question based on agent type
    question = TEST_QUESTIONS.get(agent_type, TEST_QUESTIONS["default"])

    # Build verification prompt
    prompt = f"""你是以下AI Agent，请用中文回答测试问题。

Agent角色: {name}（{agent_type}）
你的核心信念: {', '.join(beliefs[:5]) if beliefs else '无特定信念'}

测试问题: {question}

【要求】
- 用1-3句话回答
- 必须引用你的角色和信念
- 如果你不知道，说"我不确定"
- 不要编造具体数据"""

    try:
        answer = call_deepseek(prompt, max_tokens=200)
    except Exception as e:
        return {"agent": name, "type": agent_type, "pass": False,
                "reason": f"API error: {str(e)[:50]}"}

    # Quality checks (ruflo verification gates)
    checks = {
        "not_empty": len(answer.strip()) > 10,
        "not_generic": not any(phrase in answer for phrase in [
            "作为AI助手", "根据我的训练数据", "我没有个人观点"
        ]),
        "has_substance": len(answer.strip().split()) > 3,
        "not_hallucinating_numbers": not any(c.isdigit() for c in answer.split("%")[0])
            if "%" in answer else True,
    }

    passed = all(checks.values())
    failed_checks = [k for k, v in checks.items() if not v]

    return {
        "agent": name,
        "type": agent_type,
        "pass": passed,
        "answer": answer[:200],
        "failed_checks": failed_checks if not passed else [],
        "reason": "; ".join(failed_checks) if not passed else "OK",
    }

def main(sample_size: int = 10, fail_threshold: float = 0.3):
    print("\n" + "="*60)
    print("  Agent Verification Gate (ruflo pattern)")
    print("="*60)

    # Load today's learned agents
    agents = []
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    for af in sorted(AGENT_DIR.glob("agent-*.json")):
        try:
            a = json.loads(af.read_text())
            prof = a.get("profile", a)
            last = prof.get("last_learned", "")
            if today in str(last):
                agents.append(a)
        except Exception:
            pass

    if not agents:
        print(f"  No agents learned today ({today}), skip verification")
        return True

    # Stratified sample: pick from different types
    type_groups = {}
    for a in agents:
        t = a.get("profile", a).get("type", "unknown")
        type_groups.setdefault(t, []).append(a)

    sample = []
    for t, group in type_groups.items():
        n = max(1, int(sample_size * len(group) / len(agents)))
        sample.extend(random.sample(group, min(n, len(group))))

    if len(sample) > sample_size:
        sample = random.sample(sample, sample_size)

    print(f"  Testing {len(sample)} agents (from {len(agents)} learned today)...")

    results = []
    for i, agent in enumerate(sample):
        r = verify_agent(agent)
        results.append(r)
        status = "✅" if r["pass"] else "❌"
        print(f"  [{i+1}/{len(sample)}] {status} {r['agent']}: {r['reason'][:60]}")
        time.sleep(0.3)  # Rate limit

    passed = sum(1 for r in results if r["pass"])
    failed = len(results) - passed
    fail_rate = failed / len(results) if results else 0

    print(f"\n  Results: {passed}/{len(results)} passed, {failed} failed ({fail_rate:.0%})")

    # Save flags for downstream inspection
    flags = {
        "date": today,
        "tested": len(results),
        "passed": passed,
        "failed": failed,
        "fail_rate": round(fail_rate, 2),
        "details": results,
    }
    FLAG_FILE.write_text(json.dumps(flags, ensure_ascii=False, indent=2))

    # Gate decision (ruflo: block pipeline if too many failures)
    if fail_rate > fail_threshold:
        print(f"\n  ⛔ VERIFICATION FAILED: {fail_rate:.0%} > {fail_threshold:.0%} threshold")
        print(f"  Blocking downstream pipeline (debate/trend)")
        print(f"  Check {FLAG_FILE} for details")
        return False

    print(f"  ✅ VERIFICATION PASSED ({fail_rate:.0%} <= {fail_threshold:.0%})")
    print(f"  Proceeding to debate pipeline")
    return True

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--sample", type=int, default=10)
    p.add_argument("--threshold", type=float, default=0.3)
    args = p.parse_args()

    ok = main(args.sample, args.threshold)
    sys.exit(0 if ok else 1)
