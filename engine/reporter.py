"""
Stage 5: Report Generation.
MENTOR Teacher-Student iteration + Social Agents wisdom-of-crowds aggregation.
Not simple summarization — iterative critique → improve → aggregate.
"""

import json
from engine.llm_client import get_llm

STUDENT_PROMPT = """You are a market analyst. Analyze the simulation results and produce insights.

Output EXACTLY this JSON:
{
  "top_performers": [
    {"product_id": "id", "name": "name", "survival_score": 0.0, "key_strength": "why it survived"}
  ],
  "failures": [
    {"product_id": "id", "name": "name", "death_cause": "what killed it", "death_round": 0}
  ],
  "pricing_insight": "what pricing range worked best",
  "timing_insight": "when did most products get traction or die",
  "market_pattern": "what common pattern emerged across products"
}"""

TEACHER_PROMPT = """You are a senior investment analyst reviewing a junior analyst's market simulation report.
Find logical flaws, data contradictions, and missing insights.

Output EXACTLY this JSON:
{
  "critique": "what the student got wrong or missed",
  "data_contradictions": ["specific contradictions between student report and simulation data"],
  "missing_angles": ["important perspectives the student missed"],
  "confidence_adjustment": 0.0 — how much to adjust the student's confidence (negative = reduce)
}"""

SYNTHESIS_PROMPT = """Synthesize multiple analyst perspectives into a final, unified report.

Output EXACTLY this JSON:
{
  "final_report": {
    "executive_summary": "2-3 sentences",
    "top_product_direction": {"name": "name", "survival_score": 0.0, "why": "why this is the best bet"},
    "runner_up": {"name": "name", "survival_score": 0.0},
    "market_verdict": "overall assessment of market opportunity",
    "actionable_recommendation": "what to build next, specifically",
    "confidence_level": 0.0-1.0
  }
}"""


def generate_report(simulation_results: list[dict], knowledge_graph: dict) -> dict:
    """Stage 5: Teacher-Student iterative report generation with multi-perspective aggregation."""
    llm = get_llm()

    sim_data = json.dumps(simulation_results, indent=2, ensure_ascii=False)

    # Phase 1: Multi-perspective Student analysis (Social Agents pattern)
    perspectives = [
        {"role": "消费者视角", "focus": "Which products actually solved consumer pain points?"},
        {"role": "投资人视角", "focus": "Which products have the highest ceiling and lowest risk?"},
        {"role": "竞品视角", "focus": "Which products threaten existing players and how would they respond?"},
        {"role": "宏观视角", "focus": "How do economic conditions affect which products survive?"},
    ]

    student_reports = []
    for p in perspectives:
        try:
            report = llm.chat_json(
                system=STUDENT_PROMPT,
                user=f"YOUR ROLE: {p['role']}. FOCUS: {p['focus']}\n\nSIMULATION DATA:\n{sim_data[:5000]}",
            )
            report["perspective"] = p["role"]
            student_reports.append(report)
        except Exception:
            continue

    # Phase 2: Teacher critique of each student (MENTOR pattern)
    improved_reports = []
    for report in student_reports:
        try:
            critique = llm.chat_json(
                system=TEACHER_PROMPT,
                user=f"STUDENT REPORT:\n{json.dumps(report, indent=2, ensure_ascii=False)}\n\nSIMULATION DATA:\n{sim_data[:3000]}",
            )
            # Merge critique into report
            report["teacher_critique"] = critique
            improved_reports.append(report)
        except Exception:
            improved_reports.append(report)

    # Phase 3: Wisdom-of-Crowds synthesis
    try:
        synthesis = llm.chat_json(
            system=SYNTHESIS_PROMPT,
            user=f"""Synthesize these {len(improved_reports)} analyst reports into one final verdict.

ANALYST REPORTS:
{json.dumps(improved_reports, indent=2, ensure_ascii=False)[:5000]}

SIMULATION SUMMARY:
{json.dumps([{
    'name': r.get('product_name', ''),
    'score': r.get('survival_score', 0),
    'purchasers': r.get('purchasers', 0),
    'churn': r.get('churn_rate', 0),
    'revenue': r.get('total_revenue_cny', 0),
    'status': r.get('status', '')
} for r in simulation_results], indent=2, ensure_ascii=False)}""",
        )
    except Exception:
        synthesis = {"final_report": {"executive_summary": "Synthesis failed — see individual analyst reports."}}

    return {
        "simulation_results": simulation_results,
        "analyst_reports": improved_reports,
        "synthesis": synthesis.get("final_report", {}),
    }
