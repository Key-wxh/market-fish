"""
Price Elasticity Scanner — find optimal pricing by simulating the same product
at multiple price points. Reuses saved agents + simulate() — no pipeline changes.
"""

import copy
import time
from engine.config import simulation_cfg as _cfg


def scan_price_elasticity(
    product: dict,
    agents: list,
    price_points: list,
    rounds: int = None,
    market_type: str = "consumer",
    progress_callback=None,
) -> dict:
    """
    Run simulate() for each price point on the same product.

    Args:
        product: Product direction dict (from pipeline output)
        agents: Agent list (from pipeline output agents_v2.agents)
        price_points: List of prices to test, e.g. [1, 3, 6, 9, 12, 18, 30]
        rounds: Simulation rounds per price point (default: config value, min 10)
        market_type: "consumer" | "smb"
        progress_callback: Optional fn(step, total) for UI progress bar

    Returns:
        {
            "price_points": [1, 3, 6, ...],
            "results": [{"price": 6, "buyers": 27, "revenue": 162, "score": 1.0, "status": "alive"}, ...],
            "optimal_price": 6,
            "max_revenue_price": 9,
            "recommendation": "...",
            "elapsed_seconds": 45.2,
        }
    """
    from engine.simulator import simulate

    if rounds is None:
        rounds = max(10, _cfg().get("rounds", 20))

    # Filter agents to relevant market type
    relevant_agents = [a for a in agents if a.get("type") in (market_type, "competitor", "environment")]
    if not relevant_agents:
        relevant_agents = agents

    results = []
    total = len(price_points)
    started = time.time()

    for i, price in enumerate(price_points):
        if progress_callback:
            progress_callback(i + 1, total)

        variant = copy.deepcopy(product)
        variant["estimated_pricing_cny"] = f"¥{price}"
        variant["_price_scan_target"] = price

        try:
            sim_result = simulate(
                agents=relevant_agents,
                product_directions=[variant],
                rounds=rounds,
                market_type=market_type,
            )
            sim_data = sim_result.get("results", [{}])[0] if sim_result.get("results") else {}
            results.append({
                "price": price,
                "buyers": sim_data.get("purchasers", 0),
                "revenue": round(sim_data.get("total_revenue_cny", 0), 1),
                "score": round(sim_data.get("survival_score", 0), 3),
                "status": sim_data.get("status", "dead"),
                "churn_rate": sim_data.get("churn_rate", 0),
            })
        except Exception as e:
            results.append({
                "price": price,
                "buyers": 0,
                "revenue": 0,
                "score": 0,
                "status": "error",
                "churn_rate": 0,
                "error": str(e),
            })

    elapsed = time.time() - started

    # Find optimal price by revenue (primary) and survival score (secondary)
    valid = [r for r in results if r.get("status") not in ("error", "dead")]
    if not valid:
        valid = results

    max_revenue = max(valid, key=lambda r: r["revenue"])
    max_score = max(valid, key=lambda r: (r["score"], r["revenue"]))

    # Generate recommendation
    if max_revenue["buyers"] == 0:
        recommendation = f"所有价格点均无买家。产品可能需要重新定位或功能调整。"
    elif max_revenue["revenue"] == max_score.get("revenue", 0):
        recommendation = f"最优价格 ¥{max_revenue['price']} — 营收 ¥{max_revenue['revenue']} · {max_revenue['buyers']} 买家"
    else:
        recommendation = (
            f"营收最优: ¥{max_revenue['price']} (¥{max_revenue['revenue']} · {max_revenue['buyers']}人)\n"
            f"得分最优: ¥{max_score.get('price','?')} (score={max_score.get('score','?')})"
        )

    return {
        "price_points": price_points,
        "results": results,
        "optimal_price_by_revenue": max_revenue["price"],
        "optimal_price_by_score": max_score.get("price", max_revenue["price"]),
        "recommendation": recommendation,
        "elapsed_seconds": round(elapsed, 1),
    }


def build_elasticity_chart(scan_result: dict, height: int = 350):
    """
    Build a Plotly dual-axis chart: price vs buyers (bar) + price vs revenue (line).
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    results = scan_result.get("results", [])
    if not results:
        return go.Figure()

    prices = [r["price"] for r in results]
    buyers = [r["buyers"] for r in results]
    revenues = [r["revenue"] for r in results]
    scores = [r["score"] for r in results]
    statuses = [r.get("status", "dead") for r in results]

    # Bar colors based on status
    bar_colors = []
    for s in statuses:
        if s == "alive":
            bar_colors.append("rgba(0, 255, 136, 0.7)")
        elif s == "struggling":
            bar_colors.append("rgba(255, 170, 0, 0.7)")
        else:
            bar_colors.append("rgba(255, 68, 68, 0.4)")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Buyers bars
    fig.add_trace(go.Bar(
        x=[f"¥{p}" for p in prices], y=buyers,
        marker=dict(color=bar_colors, line=dict(width=0)),
        text=[f"{b}人" for b in buyers],
        textposition="outside", textfont=dict(size=12, color="#ccccee"),
        name="Buyers",
    ), secondary_y=False)

    # Revenue line
    fig.add_trace(go.Scatter(
        x=[f"¥{p}" for p in prices], y=revenues,
        mode="lines+markers+text",
        line=dict(color="#ffaa00", width=3),
        marker=dict(size=10, color="#ffaa00"),
        text=[f"¥{rv:.0f}" for rv in revenues],
        textposition="top center", textfont=dict(size=11, color="#ffaa00"),
        name="Revenue (¥)",
    ), secondary_y=True)

    # Optimal price annotation
    optimal = scan_result.get("optimal_price_by_revenue")
    if optimal and results:
        opt_idx = prices.index(optimal) if optimal in prices else -1
        if opt_idx >= 0:
            fig.add_annotation(
                x=f"¥{optimal}", y=revenues[opt_idx],
                text=f"← 营收最优 ¥{optimal}",
                showarrow=True, arrowhead=2,
                font=dict(size=13, color="#ffaa00"),
                ax=40, ay=-30,
            )

    fig.update_layout(
        title=dict(text="💰 价格弹性分析", font=dict(size=14)),
        height=height,
        hovermode="x unified",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#ccccee", size=12),
        margin=dict(l=10, r=10, t=30, b=10),
    )
    fig.update_yaxes(title_text="Buyers", secondary_y=False, gridcolor="#333355")
    fig.update_yaxes(title_text="Revenue (¥)", secondary_y=True, gridcolor="#333355")
    fig.update_xaxes(gridcolor="#333355")

    return fig
