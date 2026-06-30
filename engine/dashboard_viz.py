"""
Dashboard Visualization — Plotly interactive charts for Streamlit.
Replaces bare st.bar_chart / st.metric with professional visualizations.
"""

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from collections import defaultdict, Counter
from engine.i18n import t as _t

# ── Color palette ──
COLORS = {
    "alive": "#00ff88", "struggling": "#ffaa00", "dead": "#ff4444",
    "consumer": "#00d4ff", "smb": "#00ff88", "enterprise": "#ff6b6b",
    "competitor": "#ffaa00", "environment": "#aa88ff",
    "price_sensitive": "#ff6b6b", "impulsive": "#ffaa00", "rational": "#00d4ff",
    "b2c": "#00ff88", "smb": "#00d4ff",
}

PLOT_BG = "rgba(0,0,0,0)"  # transparent — lets Streamlit dark theme through
GRID_COLOR = "#333355"
FONT_COLOR = "#ccccee"


def _dark_template(fig: go.Figure) -> go.Figure:
    """Apply dark theme to a plotly figure."""
    fig.update_layout(
        plot_bgcolor=PLOT_BG, paper_bgcolor=PLOT_BG,
        font=dict(color=FONT_COLOR, size=12),
        xaxis=dict(gridcolor=GRID_COLOR, zerolinecolor=GRID_COLOR),
        yaxis=dict(gridcolor=GRID_COLOR, zerolinecolor=GRID_COLOR),
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(font=dict(color=FONT_COLOR)),
        hoverlabel=dict(bgcolor="#1a1a2e", font_size=12),
    )
    return fig


# ═══════════════════════════════════════════════════════════
# 1. Product Survival Score — horizontal bar + revenue
# ═══════════════════════════════════════════════════════════

def survival_score_chart(sim_results: list, height: int = 280) -> go.Figure:
    """Horizontal bar chart: product survival scores with revenue overlay."""
    # Dedup by name
    seen = {}
    for r in sim_results:
        name = r.get("product_name", r.get("name", "?"))
        if name not in seen:
            seen[name] = dict(r)
        else:
            seen[name]["purchasers"] = seen[name].get("purchasers", 0) + r.get("purchasers", 0)
            seen[name]["total_revenue_cny"] = round(
                seen[name].get("total_revenue_cny", 0) + r.get("total_revenue_cny", 0), 2)

    names = list(seen.keys())
    scores = [seen[n].get("survival_score", 0) for n in names]
    buyers = [seen[n].get("purchasers", 0) for n in names]
    revenues = [seen[n].get("total_revenue_cny", 0) for n in names]
    statuses = [seen[n].get("status", "dead") for n in names]

    colors = [COLORS.get(s, COLORS["dead"]) for s in statuses]
    hover_text = [
        f"<b>{n}</b><br>Score: {sc:.3f}<br>Buyers: {b}<br>Revenue: ¥{rv:.0f}"
        for n, sc, b, rv in zip(names, scores, buyers, revenues)
    ]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=names, x=scores, orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        text=[f"{s:.2f} | {b} buyers | ¥{rv:.0f}" for s, b, rv in zip(scores, buyers, revenues)],
        textposition="auto", textfont=dict(size=11, color="#ffffff"),
        hovertext=hover_text, hoverinfo="text",
        name=_t("status.alive") + " Score",
    ))

    fig.update_layout(
        title=dict(text=_t("products_tab.survival_chart"), font=dict(size=14)),
        xaxis=dict(title=_t("status.alive") + " Score", range=[0, 1.1], showgrid=True),
        yaxis=dict(title="", autorange="reversed"),
        showlegend=False, height=height,
    )
    return _dark_template(fig)


# ═══════════════════════════════════════════════════════════
# 2. Buyer Segments — donut chart
# ═══════════════════════════════════════════════════════════

def buyer_segments_donut(buyer_profile: dict, height: int = 260) -> go.Figure:
    """Donut chart showing buyer type segments."""
    segments = buyer_profile.get("segments", [])
    if not segments:
        return _dark_template(go.Figure())

    labels = [s["name"] for s in segments]
    values = [s["count"] for s in segments]
    colors = [COLORS.get(s["name"], "#888888") for s in segments]

    fig = go.Figure()
    fig.add_trace(go.Pie(
        labels=labels, values=values,
        hole=0.6,
        marker=dict(colors=[COLORS.get("price_sensitive", COLORS["price_sensitive"]),
                            COLORS.get("impulsive", COLORS["impulsive"]),
                            COLORS.get("rational", COLORS["rational"])][:len(labels)]),
        textinfo="label+percent",
        textfont=dict(size=11),
        hoverinfo="label+value+percent",
    ))

    fig.update_layout(
        title=dict(text=f"{_t('evidence_tab.buyer_segments')} ({buyer_profile.get('total_buyers', 0)} buyers · avg ¥{buyer_profile.get('avg_budget', 0):.0f})", font=dict(size=13)),
        height=height,
        showlegend=False,
    )
    return _dark_template(fig)


# ═══════════════════════════════════════════════════════════
# 3. Adoption Curve — cumulative S-curve over 30 rounds
# ═══════════════════════════════════════════════════════════

def adoption_curve(sim_log: list, height: int = 260) -> go.Figure:
    """Cumulative adoption over rounds — the key market-fit visualization."""
    if not sim_log:
        return _dark_template(go.Figure())

    # Cumulative purchases per round
    cumulative = defaultdict(int)
    for entry in sim_log:
        if not isinstance(entry, dict):
            continue
        rnd = entry.get("round", 0)
        if entry.get("action") == "purchase" and entry.get("product_id"):
            cumulative[rnd] += 1

    rounds = sorted(cumulative.keys())
    if not rounds:
        return _dark_template(go.Figure())

    cumsum = []
    total = 0
    for r in range(1, max(rounds) + 1):
        total += cumulative.get(r, 0)
        cumsum.append(total)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(range(1, len(cumsum) + 1)), y=cumsum,
        mode="lines+markers",
        line=dict(color=COLORS["alive"], width=3, shape="spline"),
        marker=dict(size=6, color=COLORS["alive"]),
        fill="tozeroy", fillcolor="rgba(0,255,136,0.1)",
        name="Cumulative Buyers",
    ))

    # Add vertical markers for FOMO rounds (where adoption accelerates)
    if len(cumsum) >= 3:
        deltas = [cumsum[i] - cumsum[i-1] for i in range(1, len(cumsum))]
        avg_delta = sum(deltas) / len(deltas) if deltas else 0
        for i, d in enumerate(deltas):
            if d >= avg_delta * 2:  # FOMO spike: 2x normal adoption
                fig.add_vline(x=i+2, line_dash="dot", line_color=COLORS["competitor"],
                            annotation_text="FOMO", annotation_position="top",
                            annotation_font=dict(size=10, color=COLORS["competitor"]))

    fig.update_layout(
        title=dict(text=_t("products_tab.adoption_curve"), font=dict(size=13)),
        xaxis=dict(title=_t("agents_tab.rounds"), dtick=5),
        yaxis=dict(title="Cumulative Buyers"),
        showlegend=False, height=height,
    )
    return _dark_template(fig)


# ═══════════════════════════════════════════════════════════
# 4. RL Strategy Radar — spider chart per market
# ═══════════════════════════════════════════════════════════

def rl_strategy_radar(rl_stats: dict, height: int = 300) -> go.Figure:
    """Radar chart: 5-dimension RL strategy vector per market type."""
    dimensions = ["price_sensitivity", "early_adopter", "social_susceptibility", "loyalty", "risk_tolerance"]
    labels = [_t("rl_tab.price_sensitivity"), _t("rl_tab.early_adopter"), _t("rl_tab.social_susceptibility"), _t("rl_tab.loyalty"), _t("rl_tab.risk_tolerance")]

    fig = go.Figure()
    for mkt, stats in rl_stats.items():
        if not isinstance(stats, dict):
            continue
        avg = stats.get("avg_final_strategies", {})
        values = [avg.get(d, 0) for d in dimensions]
        values.append(values[0])  # close the loop

        color = COLORS.get(mkt, "#888888")
        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=labels + [labels[0]],
            fill="toself",
            name=mkt.upper(),
            line=dict(color=color, width=2),
            fillcolor=color.replace(")", ",0.15)").replace("rgb", "rgba"),
        ))

    fig.update_layout(
        title=dict(text=_t("rl_tab.title"), font=dict(size=13)),
        polar=dict(
            radialaxis=dict(range=[0, 1], gridcolor=GRID_COLOR, tickfont=dict(size=10)),
            angularaxis=dict(gridcolor=GRID_COLOR, tickfont=dict(size=10)),
            bgcolor=PLOT_BG,
        ),
        height=height,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.2),
    )
    return _dark_template(fig)


# ═══════════════════════════════════════════════════════════
# 5. Emotion Timeline — sentiment over rounds by market
# ═══════════════════════════════════════════════════════════

def emotion_timeline(timeline: list, height: int = 250) -> go.Figure:
    """Line chart: market sentiment over simulation rounds."""
    if not timeline:
        return _dark_template(go.Figure())

    rounds = [t.get("round", i) for i, t in enumerate(timeline)]
    sentiments = [t.get("market_sentiment", 0) for t in timeline]
    adoptions = [t.get("adoption_rate", 0) for t in timeline]

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(go.Scatter(
        x=rounds, y=sentiments,
        mode="lines+markers",
        line=dict(color=COLORS["alive"], width=2),
        marker=dict(size=5),
        name=_t("agents_tab.sentiment"),
    ), secondary_y=False)

    fig.add_trace(go.Bar(
        x=rounds, y=adoptions,
        marker=dict(color=COLORS["consumer"], opacity=0.3),
        name="Adoption Rate",
    ), secondary_y=True)

    fig.update_layout(
        title=dict(text=_t("products_tab.emotion_timeline"), font=dict(size=13)),
        height=height,
        hovermode="x unified",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    fig.update_yaxes(title_text=_t("agents_tab.sentiment"), secondary_y=False, range=[-1, 1], gridcolor=GRID_COLOR)
    fig.update_yaxes(title_text=_t("evidence_tab.revenue") + " %", secondary_y=True, range=[0, 1], showgrid=False)
    fig.update_xaxes(title_text=_t("agents_tab.rounds"), dtick=5)
    return _dark_template(fig)


# ═══════════════════════════════════════════════════════════
# 6. Agent Type Distribution — colorful bar
# ═══════════════════════════════════════════════════════════

def agent_type_distribution(agents: list, height: int = 220) -> go.Figure:
    """Bar chart: agent count by type, styled."""
    types = Counter(a.get("type", "unknown") for a in agents)
    labels = list(types.keys())
    values = list(types.values())
    colors = [COLORS.get(t, "#888888") for t in labels]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels, y=values,
        marker=dict(color=colors, line=dict(width=0)),
        text=values, textposition="outside",
        textfont=dict(size=14, color=FONT_COLOR),
        hovertext=[f"{t}: {v} agents" for t, v in zip(labels, values)],
        hoverinfo="text",
    ))

    fig.update_layout(
        title=dict(text=_t("agents_tab.type_distribution"), font=dict(size=13)),
        xaxis=dict(title=""),
        yaxis=dict(title=_t("sidebar.agent_count"), showgrid=True),
        showlegend=False, height=height,
    )
    return _dark_template(fig)
