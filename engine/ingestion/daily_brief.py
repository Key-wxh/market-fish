"""
Daily Brief Generator — reads Gold snapshot, produces human-readable Markdown briefing.
Each signal cites its source and validating paper. Zero LLM involved — pure data→text.
"""
import json
from datetime import datetime, timezone
from pathlib import Path


def generate_daily_brief(data_lake_root: str = None) -> str:
    """Generate daily market briefing Markdown from the latest gold snapshot.

    Returns the brief as a Markdown string. Also writes to gold/daily_brief.md.
    """
    if data_lake_root is None:
        data_lake_root = str(Path(__file__).parent.parent.parent / "data_lake")

    gold_dir = Path(data_lake_root) / "gold"
    snapshot_path = gold_dir / "seed_snapshot.json"

    if not snapshot_path.exists():
        msg = "# MarketFish Daily Brief\n\n*No data yet. Run ingestion first.*\n"
        _write_brief(gold_dir, msg)
        return msg

    with open(snapshot_path, encoding="utf-8") as f:
        snap = json.load(f)

    dims = snap.get("dimensions", {})
    signals = snap.get("signals", {})
    prov = snap.get("provenance", {})
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = []
    lines.append(f"# MarketFish 每日市场简报 — {now}")
    lines.append("")
    lines.append(f"> 数据源: {', '.join(prov.get('data_sources', ['无']))}")
    lines.append(f"> 快照: {snap.get('snapshot_id', '?')} | 信号数: {len(signals)}")
    lines.append("")

    # ── Macro Section ──
    macro = dims.get("macroeconomic", {}).get("global", {})
    if macro:
        lines.append("## 宏观经济 (World Bank)")
        lines.append("")
        lines.append("| 指标 | 值 |")
        lines.append("|------|------|")
        gdp = macro.get("us_gdp_growth_pct")
        if gdp is not None:
            icon = "🔴" if gdp < 1.5 else ("🟡" if gdp < 2.5 else "🟢")
            lines.append(f"| 美国 GDP 增速 | {gdp:.1f}% {icon} |")
        inf = macro.get("us_inflation_pct")
        if inf is not None:
            icon = "🔴" if inf > 5 else ("🟡" if inf > 3 else "🟢")
            lines.append(f"| 美国 CPI 通胀 | {inf:.1f}% {icon} |")
        unemp = macro.get("us_unemployment_pct")
        if unemp is not None:
            lines.append(f"| 美国失业率 | {unemp:.1f}% |")
        cn = macro.get("cn_gdp_growth_pct")
        if cn is not None:
            icon = "🔴" if cn < 4 else ("🟡" if cn < 5 else "🟢")
            lines.append(f"| 中国 GDP 增速 | {cn:.1f}% {icon} |")
        wld = macro.get("world_gdp_growth_pct")
        if wld is not None:
            lines.append(f"| 全球 GDP 增速 | {wld:.1f}% |")
        lines.append(f"| 数据点 | {macro.get('datapoints_fetched', '?')} 个 |")
        lines.append("")

    # ── Tech Section ──
    tech = dims.get("technology_adoption", {})
    gh = tech.get("github", {})
    hn = tech.get("hackernews", {})
    so = tech.get("stackoverflow", {})
    if gh or hn or so:
        lines.append("## 技术趋势")
        lines.append("")
        if gh:
            lines.append(f"- **GitHub**: {gh.get('total_trending_repos', '?')} 个热门仓库本周，其中 AI/ML 占 {gh.get('ai_ml_ratio', 0)*100:.0f}%")
        if hn:
            lines.append(f"- **Hacker News**: {hn.get('ai_stories', '?')}/{hn.get('stories_fetched', '?')} AI 相关 ({hn.get('ai_story_ratio', 0)*100:.0f}%)，情绪 {'📈 看多' if hn.get('sentiment_score', 0) > 0 else '📉 偏空'} ({hn.get('sentiment_score', 0):+.2f})")
        if so:
            lines.append(f"- **Stack Overflow**: AI 标签问题占 {so.get('ai_question_ratio', 0)*100:.1f}%")
        lines.append("")

    ph = tech.get("producthunt", {})
    if ph:
        lines.append(f"- **Product Hunt**: {ph.get('total_launches', '?')} 个新品，AI 占 {ph.get('ai_ratio', 0)*100:.0f}%，均票 {ph.get('avg_votes', '?')}")
        lines.append("")

    # ── Market Section ──
    em = dims.get("price_volume", {}).get("eastmoney", {})
    if em:
        source = em.get("source", "")
        lines.append(f"## 中国市场 ({source})")
        lines.append("")
        if source and "ChainGold" in (source or ""):
            close = em.get("benchmark_latest_close")
            change = em.get("benchmark_latest_change_pct")
            ratio = em.get("recent_20d_up_ratio") or 0
            icon = "🔥" if ratio > 0.6 else ("🟢" if ratio > 0.5 else "🔴")
            if close and change is not None:
                lines.append(f"- **海康威视(002415)**: {close} ({change:+.2f}%)")
            lines.append(f"- **20日涨跌比**: {em.get('recent_up_days','?')}/{em.get('recent_down_days','?')} ({ratio*100:.0f}%上涨) {icon}")
            lines.append(f"- **活跃行业**: {em.get('active_industries','?')}/{em.get('total_industries','?')}")
            lines.append(f"- **瓶颈节点**: {em.get('total_bottlenecks','?')} 个")
        else:
            ratio = (em.get("up_ratio") or 0)
            icon = "🔥" if ratio > 0.6 else ("🟢" if ratio > 0.4 else "🔴")
            lines.append(f"- **市场宽度**: {ratio*100:.0f}%上涨 {icon}")
            lines.append(f"- **成交额**: {em.get('total_turnover_yi', '?')} 亿")
            pe = em.get("avg_pe")
            if pe:
                lines.append(f"- **平均 PE**: {pe}")
        lines.append("")

    # ── Active Signals ──
    if signals:
        lines.append("## 活跃市场信号")
        lines.append("")

        signal_desc = {
            "signal_economic_slowdown": ("🔴 美国经济放缓", "GDP 增速 < 1.5% — 衰退风险", "World Bank indicators"),
            "signal_inflation_accelerating": ("🔴 通胀加速", "CPI 同比 > 5% — 通胀压力", "World Bank CPI data"),
            "signal_china_economy_weak": ("🟡 中国经济疲软", "GDP 增速 < 4% — 增长放缓", "993 Chinese predictors (Dai et al., 2025)"),
            "signal_global_synchronized_slowdown": ("🔴 全球同步放缓", "美中全球同时低于阈值 — 全球衰退风险", "Multi-country factor models"),
            "signal_ai_tools_demand_surge": ("🔥 AI 工具需求激增", "GitHub AI/ML 仓库占比 > 25%", "Frequency-domain prediction (Dai et al., 2025)"),
            "signal_tech_sentiment_bullish": ("📈 科技情绪看多", "HN AI 故事正面情绪 > 0.1", "News-based macro forecasts"),
            "signal_tech_adoption_accelerating": ("🚀 技术采用加速", "GitHub + Stack Overflow AI 信号同时走强", "Frequency-domain prediction"),
            "signal_china_economy_weak": ("🟡 中国经济疲软", "PMI < 50 — 制造业收缩", "993 Chinese predictors (Dai et al., 2025)"),
            "signal_eu_stagnation": ("🟡 欧洲停滞", "GDP 增速 < 0.5% 且失业率 > 8%", "Stock & Watson (2012)"),
            "signal_labor_market_cooling": ("🟡 劳动力市场降温", "失业率上升 + 职位空缺减少", "FRED-MD labor indicators"),
            "signal_global_synchronized_slowdown": ("🔴 全球同步放缓", "美中欧同时示弱 — 全球衰退风险", "Multi-country factor models"),
            "signal_b2b_saas_growing": ("🟢 B2B SaaS 增长", "G2 AI 品类评论增速 > 15%", "SMIF (r=0.893 calibration)"),
            "signal_china_consumption_downgrade": ("🟡 中国消费降级", "零售增速 < 2% 且 CPI < 0.5%", "993 Chinese predictors"),
        }

        for sig_name in sorted(signals.keys()):
            if sig_name in signal_desc:
                icon_title, desc, paper = signal_desc[sig_name]
                lines.append(f"### {icon_title}")
                lines.append(f"- **描述**: {desc}")
                lines.append(f"- **论文验证**: {paper}")
                lines.append("")

        if not lines[-1] == "":
            lines.append("")

    # ── Footer ──
    lines.append("---")
    lines.append(f"*自动生成于 {now} | 数据源: {', '.join(prov.get('data_sources', ['无']))} | 零 AI — 纯数据驱动*")
    lines.append(f"*MarketFish v6 — Keystart AI*")
    lines.append("")

    brief_text = "\n".join(lines)
    _write_brief(gold_dir, brief_text)

    return brief_text


def _write_brief(gold_dir: Path, text: str):
    """Write brief to file."""
    brief_path = gold_dir / "daily_brief.md"
    with open(brief_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"  [BRIEF] daily_brief.md generated ({len(text)} chars)", flush=True)
