"""
Agent Debate — 小组辩论 + 跨组碰撞，把回音壁变成集体智能。
在 agent_consensus.py 之后运行，产出 debate_report.md。

用法: python3 agent_debate.py [--groups 50] [--cross 25] [--per-group 5]
cron: agent_learn && agent_consensus && agent_debate (&& 串联)
"""
import json, os, sys, time, random, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

TZ = timezone(timedelta(hours=8))
DS_KEY = os.getenv("DEEPSEEK_API_KEY", "")

ROOT = Path(__file__).parent.parent
AGENT_DIR = ROOT / "data_lake" / "gold" / "agents"
INTEL_PATH = ROOT / "data_lake" / "gold" / "market_intel.md"
OUT_MD = ROOT / "data_lake" / "gold" / "debate_report.md"
OUT_JSON = ROOT / "data_lake" / "gold" / "debate_data.json"
PATTERNS_FILE = ROOT / "data_lake" / "gold" / "debate_patterns.json"

# ── Helpers (reused from agent_learn.py) ──

def get_profile(agent: dict) -> dict:
    return agent.get("profile", agent)

def call_deepseek(prompt: str, max_tokens: int = 800, temperature: float = 0.7) -> str:
    body = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens, "temperature": temperature,
    }).encode()
    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {DS_KEY}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"]

def parse_json(text: str) -> dict:
    text = text.strip()
    for fence in ["```json", "```"]:
        if text.startswith(fence): text = text[len(fence):].strip()
        if text.endswith("```"): text = text[:-3].strip()
    s, e = text.find("{"), text.rfind("}")
    if s >= 0 and e > s:
        try: return json.loads(text[s:e+1])
        except: pass
    return {}


# ── Pattern Learning (ruflo Pattern Learner) ──

def load_patterns() -> list:
    """Load past successful debate patterns for injection into new debates."""
    if not PATTERNS_FILE.exists():
        return []
    try:
        return json.loads(PATTERNS_FILE.read_text())
    except Exception:
        return []


def extract_patterns(groups_results: list, cross_results: list, agents: list) -> list:
    """Extract reusable patterns from debate outcomes.
    Pattern = {topic, consensus, confidence, perspectives, agent_types, timestamp}
    """
    patterns = load_patterns()
    existing_topics = {p.get("topic", "") for p in patterns}
    now = datetime.now(TZ).isoformat()

    for g in groups_results:
        consensus_list = g.get("consensus", [])
        if not consensus_list:
            continue

        # Extract consensus themes with high agreement
        for item in consensus_list:
            topic = str(item.get("topic", item))[:200]
            if not topic or topic in existing_topics:
                continue

            confidence = 0
            agreements = g.get("agreements", [])
            if agreements:
                # Higher confidence when multiple agents agree
                confidence = min(len(agreements) / max(len(g.get("members", [])), 1), 1.0)

            if confidence < 0.4:  # Only keep high-confidence patterns
                continue

            patterns.append({
                "topic": topic,
                "consensus": str(item)[:500],
                "confidence": round(confidence, 2),
                "perspectives": g.get("perspectives", [])[:5],
                "agent_count": len(g.get("members", [])),
                "timestamp": now,
                "reuse_count": 0,
            })
            existing_topics.add(topic)

    return patterns


def save_patterns(patterns: list):
    """Save patterns, keeping max 500 most recent + most reused."""
    # Sort by reuse_count (desc) then confidence (desc)
    patterns.sort(key=lambda p: (p.get("reuse_count", 0), p.get("confidence", 0)), reverse=True)
    PATTERNS_FILE.write_text(json.dumps(patterns[:500], ensure_ascii=False, indent=2))


def inject_patterns(debate_prompt: str, patterns: list, max_patterns: int = 3) -> str:
    """Inject relevant past patterns into a debate prompt for priming."""
    if not patterns:
        return debate_prompt

    # Select top patterns by confidence + reuse
    relevant = sorted(patterns, key=lambda p: (p.get("reuse_count", 0) + p.get("confidence", 0)), reverse=True)[:max_patterns]

    if not relevant:
        return debate_prompt

    injection = "\n【历史共识模式（参考，不是答案）】\n"
    for i, p in enumerate(relevant):
        injection += f"{i+1}. {p.get('topic', '')}: {p.get('consensus', '')[:200]}\n"

    # Insert after the system prompt but before the user message
    parts = debate_prompt.split("【本次议题】", 1)
    if len(parts) == 2:
        return parts[0] + injection + "\n【本次议题】" + parts[1]
    return debate_prompt + injection


def bump_pattern_reuse(patterns: list, topics_touched: list):
    """Increment reuse_count for patterns whose topics were discussed."""
    for p in patterns:
        for topic in topics_touched:
            if topic and p.get("topic", "")[:50] in str(topic)[:50]:
                p["reuse_count"] = p.get("reuse_count", 0) + 1
                break


# ── Phase 0: Load agents ──

def load_agents(learned_only: bool = True) -> list:
    agents = []
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    for af in sorted(AGENT_DIR.glob("agent-*.json")):
        try:
            a = json.loads(af.read_text())
            prof = get_profile(a)
            if learned_only:
                last = prof.get("last_learned", "")
                if today not in str(last):
                    continue
            bdi = prof.get("bdi", {})
            agents.append({
                "_file": af,
                "name": prof.get("name", a.get("name", "?")),
                "type": prof.get("type", a.get("type", "?")),
                "beliefs": bdi.get("beliefs", []),
                "desires": bdi.get("desires", []),
                "intentions": bdi.get("intentions", []),
                "demographics": prof.get("demographics", {}),
                "budget": prof.get("budget_monthly_cny", 3000),
                "tech": prof.get("tech_savviness", 0.5),
            })
        except Exception:
            pass
    return agents


# ── Phase 1: Clustering ──

def cluster_agents(agents: list, n_groups: int = 50) -> list:
    """Stratified random assignment — mix types per group for richer debate.
    Skips keyword clustering because learned beliefs are too similar across agents."""
    by_type = defaultdict(list)
    for a in agents:
        by_type[a.get("type", "unknown")].append(a)

    total = len(agents)
    groups = [{"id": f"group-{i+1}", "type": "mixed", "size": 0, "members": []} for i in range(n_groups)]

    # Distribute agents round-robin per type to ensure even mixing
    for typ, members in by_type.items():
        random.shuffle(members)
        for i, a in enumerate(members):
            g = i % n_groups
            groups[g]["members"].append(a)
            groups[g]["size"] += 1

    # Keep only groups with enough members for a debate (>= 3)
    groups = [g for g in groups if len(g["members"]) >= 3]
    return groups


# ── Phase 2: Group Debate ──

GROUP_DEBATE_PROMPT = """你是圆桌主持人。{size} 个不同背景的人刚读完今天的市场情报，各自有不同的看法。

参与者：
{participants}

市场情报摘要：
{intel}

请列出这群人讨论中出现的不同观点。不强求共识——意见不同本身就是信号。输出 JSON：
{{
  "viewpoints": ["参与者1认为...", "参与者2认为...", "参与者3认为..."（每人1条，保留原话风格）],
  "hottest_take": "最大胆/最意外的观点",
  "split_opinion": "意见最分裂的话题（简单描述两方立场）",
  "mood": "optimistic/cautious/divided"
}}"""

def debate_group(group: dict, intel: str) -> dict:
    """Run one group debate"""
    members = group["members"]
    if len(members) < 2:
        return {"group_id": group["id"], "consensus": [], "disagreements": [],
                "novel_ideas": [], "mood": "neutral", "error": "too few members"}

    # Pick up to 5 reps with most diverse beliefs
    reps = _pick_diverse(members, min(5, len(members)))

    # Build participant profiles
    parts = []
    for i, r in enumerate(reps):
        beliefs_str = "；".join(r.get("beliefs", [])[:2])
        desires_str = "；".join(r.get("desires", [])[:1])
        parts.append(
            f"嘉宾{i+1}（{r['type']}，{r['name']}）：\n"
            f"  信念：{beliefs_str}\n"
            f"  目标：{desires_str}"
        )

    prompt = GROUP_DEBATE_PROMPT.format(
        size=len(reps),
        participants="\n".join(parts),
        intel=intel[:1500],
    )

    try:
        # Inject relevant past patterns for priming (ruflo Pattern Learner)
        _p = load_patterns()
        _prompt = inject_patterns(prompt, _p) if _p else prompt
        text = call_deepseek(_prompt, max_tokens=600, temperature=0.8)
        result = parse_json(text)
        result["group_id"] = group["id"]
        result["size"] = len(reps)
        return result
    except Exception as e:
        return {"group_id": group["id"], "error": str(e), "consensus": [],
                "disagreements": [], "novel_ideas": []}

def _pick_diverse(members: list, n: int) -> list:
    """Pick n members — prefer different types for diverse debate"""
    if len(members) <= n:
        return members
    # Sort by type then pick evenly from different types
    by_type = defaultdict(list)
    for m in members:
        by_type[m.get("type", "?")].append(m)
    picked = []
    type_list = list(by_type.values())
    idx = 0
    while len(picked) < n and type_list:
        group = type_list[idx % len(type_list)]
        if group:
            picked.append(group.pop(0))
        idx += 1
    return picked if picked else members[:n]


# ── Phase 3: Cross-Group Debate ──

CROSS_DEBATE_PROMPT = """你是辩论裁判。两组人对市场有不同看法：

A组观点: {view_a}
A组最分裂话题: {split_a}

B组观点: {view_b}
B组最分裂话题: {split_b}

请碰撞两组的不同视角。输出 JSON：
{{
  "clash_points": ["具体碰撞点1", "碰撞点2"],
  "synthesis": "综合两方视角的平衡判断 (2-3句)",
  "insight": "这个碰撞产生的最有价值的洞察"
}}"""

def cross_debate(g1: dict, g2: dict) -> dict:
    """Debate two groups with opposing views"""
    va = "；".join(g1.get("viewpoints", [])[:3]) or "无"
    sa = g1.get("split_opinion", "") or "无"
    vb = "；".join(g2.get("viewpoints", [])[:3]) or "无"
    sb = g2.get("split_opinion", "") or "无"

    prompt = CROSS_DEBATE_PROMPT.format(view_a=va, split_a=sa, view_b=vb, split_b=sb)

    try:
        _p = load_patterns()
        _prompt = inject_patterns(prompt, _p) if _p else prompt
        text = call_deepseek(_prompt, max_tokens=400, temperature=0.7)
        result = parse_json(text)
        result["group_a"] = g1["group_id"]
        result["group_b"] = g2["group_id"]
        return result
    except Exception as e:
        return {"group_a": g1["group_id"], "group_b": g2["group_id"],
                "error": str(e), "clash_points": [], "synthesis": ""}


# ── Phase 4: Report ──

SUMMARY_PROMPT = """你是 CEO 策略顾问。以下是今天 {n_groups} 组 agents 的辩论结果。

组内共识:
{group_summaries}

跨组碰撞:
{cross_summaries}

请写一份 CEO 简报（Markdown，300字内），包含：
1. 最值得关注的 3 个共识
2. 最激烈的 2 个分歧
3. 今天辩论中出现的意外洞察
4. 对产品决策的建议

用数据说话，不要恭维。"""

def generate_report(groups_results: list, cross_results: list, agents: list) -> str:
    today = datetime.now(TZ).strftime("%Y年%m月%d日")
    n_agents = len(agents)
    n_groups = len(groups_results)
    n_cross = len(cross_results)

    # Count stats
    total_viewpoints = sum(len(g.get("viewpoints", [])) for g in groups_results)
    total_splits = sum(1 for g in groups_results if g.get("split_opinion"))
    total_hot = sum(1 for g in groups_results if g.get("hottest_take"))

    # Build summaries for LLM
    group_summaries = []
    for g in groups_results[:30]:
        v = "；".join(g.get("viewpoints", [])[:2]) or "无"
        s = g.get("split_opinion", "") or "无"
        group_summaries.append(f"[{g.get('group_id','?')}] 观点:{v} | 分裂:{s}")

    cross_summaries = []
    for c in cross_results[:15]:
        clash = "；".join(c.get("clash_points", [])[:2]) or "无"
        cross_summaries.append(f"{c.get('group_a','?')} vs {c.get('group_b','?')}: {clash}")

    prompt = SUMMARY_PROMPT.format(
        n_groups=n_groups,
        group_summaries="\n".join(group_summaries),
        cross_summaries="\n".join(cross_summaries),
    )

    try:
        ceo_brief = call_deepseek(prompt, max_tokens=500, temperature=0.5)
    except Exception:
        ceo_brief = "_(AI 总结生成失败)_"

    # Top consensus themes
    all_consensus = []
    for g in groups_results:
        for c in g.get("consensus", []):
            if c: all_consensus.append(c)

    lines = [
        f"# Agent 辩论报告 · {today}",
        "",
        f"> {n_groups} 组辩论 | {n_cross} 场跨组碰撞 | {n_agents} agents 参与",
        "",
        "---",
        "",
        "## 辩论统计",
        "",
        f"| 指标 | 值 |",
        f"|------|:--:|",
        f"| 参与小组 | {n_groups} |",
        f"| 多元观点 | {total_viewpoints} 条 |",
        f"| 意见分裂 | {total_splits} 组 |",
        f"| 大胆观点 | {total_hot} 条 |",
        f"| 跨组碰撞 | {n_cross} 场 |",
        "",
        "---",
        "",
        "## 🔥 各组核心观点",
        "",
    ]

    # Show viewpoints from all groups
    for g in groups_results[:15]:
        vps = g.get("viewpoints", [])
        hottest = g.get("hottest_take", "")
        split = g.get("split_opinion", "")
        if vps:
            lines.append(f"### {g.get('group_id','?')} ({g.get('mood','?')})")
            for v in vps[:2]:
                lines.append(f"- {v}")
            if hottest:
                lines.append(f"  - 💥 最大胆: {hottest}")
            if split:
                lines.append(f"  - ⚡ 最分裂: {split}")
            lines.append("")

    lines += [
        "",
        "## 💡 跨组碰撞洞察",
        "",
    ]
    for c in cross_results[:10]:
        insight = c.get("insight") or c.get("synthesis", "")
        if insight:
            lines.append(f"- **{c.get('group_a','?')}** vs **{c.get('group_b','?')}**: {insight}")

    lines += [
        "",
        "---",
        "",
        "## 📋 CEO 决策参考",
        "",
        ceo_brief,
        "",
        f"*自动生成 · {datetime.now(TZ).strftime('%H:%M')} · {n_groups}组辩论*",
    ]

    return "\n".join(lines)


# ── Main ──

def main():
    n_groups = 50
    n_cross = 25
    per_group = 5
    for arg in sys.argv[1:]:
        if arg.startswith("--groups="): n_groups = int(arg.split("=")[1])
        if arg.startswith("--cross="): n_cross = int(arg.split("=")[1])
        if arg.startswith("--per-group="): per_group = int(arg.split("=")[1])

    t0 = time.time()
    print(f"[{datetime.now(TZ).strftime('%m-%d %H:%M')}] Agent Debate: clustering...")

    # Phase 1: Load + Cluster
    agents = load_agents(learned_only=True)
    if len(agents) < 10:
        print(f"  Not enough learned agents ({len(agents)}), skipping debate")
        return

    groups = cluster_agents(agents, n_groups)
    print(f"  {len(groups)} groups from {len(agents)} agents")

    # Load intel for context
    intel = ""
    if INTEL_PATH.exists():
        intel = INTEL_PATH.read_text(encoding="utf-8")[:2000]

    # Phase 2: Group debates (parallel)
    print(f"  Phase 2: {len(groups)} group debates...")
    group_results = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(debate_group, g, intel): g for g in groups}
        for i, future in enumerate(as_completed(futures)):
            try:
                r = future.result(timeout=90)
                group_results.append(r)
            except Exception:
                group_results.append({"group_id": futures[future]["id"], "error": "timeout",
                                      "consensus": [], "disagreements": [], "novel_ideas": []})
            if (i + 1) % 20 == 0:
                print(f"    {i+1}/{len(groups)} groups done")

    # Phase 3: Cross-group debates (pair opposing groups)
    # Sort groups by consensus "optimism" — pair optimistic vs cautious
    scored = []
    for r in group_results:
        mood = r.get("mood", "neutral")
        score = 1 if mood == "optimistic" else (-1 if mood == "cautious" else 0)
        scored.append((score, r))
    scored.sort(key=lambda x: x[0])

    n_cross_actual = min(n_cross, len(scored) // 2)
    cross_pairs = []
    for i in range(n_cross_actual):
        g_opt = scored[-(i+1)][1]  # most optimistic
        g_cau = scored[i][1]       # most cautious
        cross_pairs.append((g_opt, g_cau))

    print(f"  Phase 3: {len(cross_pairs)} cross-group debates...")
    cross_results = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(cross_debate, g1, g2): (g1, g2) for g1, g2 in cross_pairs}
        for future in as_completed(futures):
            try:
                cross_results.append(future.result(timeout=60))
            except Exception:
                pass

    # Phase 4: Report
    print(f"  Phase 4: generating report...")
    report = generate_report(group_results, cross_results, agents)

    # Extract + save patterns for next run (ruflo Pattern Learner)
    patterns = extract_patterns(group_results, cross_results, agents)
    if patterns:
        save_patterns(patterns)
        print(f"  Patterns: {len(patterns)} saved")

    OUT_MD.write_text(report, encoding="utf-8")
    OUT_JSON.write_text(json.dumps({
        "date": datetime.now(TZ).strftime("%Y-%m-%d"),
        "groups": n_groups,
        "cross_debates": n_cross_actual,
        "agents": len(agents),
        "group_results": group_results,
        "cross_results": cross_results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    elapsed = time.time() - t0
    print(f"  Done: {len(group_results)} groups, {len(cross_results)} cross | {elapsed:.0f}s")
    print(f"  Report: {OUT_MD}")


if __name__ == "__main__":
    main()
