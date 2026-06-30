"""
MarketFish v4 — Live Dashboard
Real-time pipeline monitoring, market simulation visualization,
coupling & RL metrics, agent network graph.
"""

import json, time, sys, os, builtins
from datetime import datetime

# Load .env before anything else
from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="MarketFish v4 — 市场预测引擎",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS for polished look ──
st.markdown("""
<style>
    .main-header { font-size: 2.2rem; font-weight: 800; margin-bottom: 0; }
    .sub-header { color: #888; font-size: 1rem; margin-top: 0; }
    .metric-card { background: #1a1a2e; border-radius: 12px; padding: 1.2rem; text-align: center; }
    .metric-value { font-size: 2rem; font-weight: 700; color: #00d4ff; }
    .metric-label { font-size: 0.85rem; color: #aaa; }
    .alive-badge { color: #00ff88; font-weight: 600; }
    .dead-badge { color: #ff4444; font-weight: 600; }
    .promising-badge { color: #ffaa00; font-weight: 600; }
    .agent-card { background: #16213e; border-radius: 8px; padding: 0.8rem; margin: 0.3rem 0; font-size: 0.85rem; }
    .stage-done { color: #00ff88; }
    .stage-running { color: #00d4ff; animation: pulse 1.5s infinite; }
    @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.5; } }
</style>
""", unsafe_allow_html=True)

# ── Header ──
st.markdown('<p class="main-header"> MarketFish v4</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">6-LLM Heterogeneous Agents · Small-World Network · Cross-Domain Coupling · Economic Alignment RL</p>', unsafe_allow_html=True)

# ── Sidebar ──
with st.sidebar:
    st.header("⚙️ 配置")

    st.subheader("种子数据源")
    seed_sources = st.multiselect(
        "选择数据源",
        ["freelancer", "economy", "tech", "consumer", "b2b"],
        default=["freelancer", "economy", "tech", "consumer", "b2b"],
    )

    st.subheader("模拟参数")
    sim_rounds = st.slider("模拟轮数", 10, 60, 30, 5)
    agent_cap = st.slider("消费者上限", 10, 100, 50, 10)

    st.subheader("模型配置")
    st.caption("6-LLM Heterogeneous Architecture")
    models_status = {}
    for name in ["deepseek", "qwen", "doubao", "zhipu", "baidu", "hunyuan"]:
        key_var = f"{'DEEPSEEK' if name == 'deepseek' else name.upper()}_API_KEY"
        has_key = bool(os.getenv(key_var))
        models_status[name] = has_key
        st.markdown(f"{'🟢' if has_key else '🔴'} {name}")

    st.divider()
    st.caption(f"v4.0 · {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# ── Load seed data ──
@st.cache_data
def load_seed_data(sources):
    seed = {}
    for key in sources:
        path = f"data/seed_{key}.json"
        try:
            with open(path, encoding='utf-8') as f:
                seed[key] = json.load(f)
        except FileNotFoundError:
            st.warning(f"种子数据缺失: {path}")
    return seed

seed = load_seed_data(tuple(seed_sources))

if not seed:
    st.error("没有可用的种子数据")
    st.stop()

# ── KPI Bar ──
from engine.agent_factory import BATCHES as AGENT_BATCHES
total_agent_target = sum(b['count'] for b in AGENT_BATCHES)
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("LLMs", "6", "Multi-model")
col2.metric("Target Agents", str(total_agent_target), f"{len(AGENT_BATCHES)} batches")
col3.metric("Sim Rounds", str(sim_rounds))
col4.metric("Seed Sources", str(len(seed)))
col5.metric("Backtest Factors", "4", "100% validated")

# ── Main: Run Pipeline ──
st.divider()

run_col1, run_col2 = st.columns([1, 4])
with run_col1:
    run_btn = st.button("🚀 运行市场预测", type="primary", use_container_width=True)

status_container = st.container()

if run_btn:
    from engine.pipeline import Pipeline

    pipeline = Pipeline()
    progress_bars = {
        "ontology": st.progress(0, "阶段 1/5: 本体生成..."),
        "graph": st.progress(0, "阶段 2/5: 知识图谱..."),
        "agents": st.progress(0, "阶段 3/5: Agent + 产品方向..."),
        "simulation": st.progress(0, "阶段 4/5: 市场模拟 (耦合+RL)..."),
        "report": st.progress(0, "阶段 5/5: 报告生成..."),
    }

    sim_log_placeholder = st.empty()

    t0 = time.time()

    # Patch simulator to stream progress to Streamlit
    import engine.simulator as sim_module
    original_print = builtins.print

    sim_lines = []
    def stream_print(*args, **kwargs):
        msg = " ".join(str(a) for a in args)
        sim_lines.append(msg)
        if "[SIM]" in msg:
            sim_log_placeholder.code("\n".join(sim_lines[-15:]), language="text")
        original_print(*args, **kwargs)

    builtins.print = stream_print

    try:
        # Stage 1
        result = pipeline.run(seed)

        elapsed = time.time() - t0
        builtins.print = original_print

        # Update all progress bars
        for k, bar in progress_bars.items():
            if k in result.get("stages_completed", []):
                bar.progress(100, f"✅ 阶段 {['1','2','3','4','5'][['ontology','graph','agents','simulation','report'].index(k)]}/5 完成")

        if result.get("pipeline_status") == "complete":
            st.balloons()
            st.success(f"🎉 管道完成！耗时 {elapsed:.0f} 秒 ({elapsed/60:.1f} 分钟)")

            # ═══════════════════════════════════════
            # RESULTS DASHBOARD
            # ═══════════════════════════════════════

            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "📊 产品预测", "🤖 Agent 总览", "🕸️ 耦合 & 网络", "🧠 RL 策略", "📋 原始数据"
            ])

            # ── Tab 1: Product Predictions ──
            with tab1:
                st.subheader("🎯 产品方向生存预测")

                directions = result.get("product_directions", [])
                sim_results = result.get("final_report", {}).get("simulation_results", [])

                # Score cards
                cols = st.columns(min(len(sim_results), 4))
                for i, r in enumerate(sim_results[:8]):
                    with cols[i % 4]:
                        status = r.get("status", "dead")
                        emoji = "🟢" if status == "alive" else ("🟡" if status == "struggling" else "🔴")
                        st.metric(
                            f"{emoji} {r['product_name'][:25]}",
                            f"Score: {r['survival_score']:.2f}",
                            f"Buyers: {r['purchasers']} | Rev: ¥{r['total_revenue_cny']}",
                        )

                # Survival chart
                if sim_results:
                    df = pd.DataFrame([
                        {"产品": r["product_name"][:20], "存活分数": r["survival_score"],
                         "买家数": r["purchasers"], "收入": r["total_revenue_cny"],
                         "流失率": r["churn_rate"]}
                        for r in sim_results
                    ])
                    st.subheader("📈 产品表现对比")
                    chart_col1, chart_col2 = st.columns(2)
                    with chart_col1:
                        st.bar_chart(df.set_index("产品")[["存活分数"]], height=300)
                    with chart_col2:
                        st.bar_chart(df.set_index("产品")[["收入"]], height=300)

                # Backtest filter results
                st.subheader("🔍 回测因子过滤")
                if directions:
                    bt_df = pd.DataFrame([
                        {"产品": d["name"][:25], "回测分": d.get("backtest_score", 0),
                         "判定": d.get("backtest_verdict", "?"),
                         "因子": ", ".join(d.get("backtest_flags", [])),
                         "杀手": ", ".join(d.get("backtest_kill_flags", []))}
                        for d in directions
                    ])
                    st.dataframe(bt_df, use_container_width=True, hide_index=True)

            # ── Tab 2: Agent Overview ──
            with tab2:
                st.subheader("🤖 异质 Agent 群体")

                stages = result.get("stages", {})
                agent_count = stages.get("agents_v2", {}).get("count", stages.get("agents", {}).get("count", 0))
                st.metric("Agent 总数", agent_count)

                # Agent type distribution
                # Extract from simulation timeline
                sim_stage = stages.get("simulation", {})
                tl = sim_stage.get("timeline", []) if isinstance(sim_stage, dict) else []
                if hasattr(sim_stage, 'get'):
                    pass

                # Show coupling & RL stats per market
                coupling_data = stages.get("simulation", {}).get("cross_domain_coupling", {})
                rl_data = stages.get("simulation", {}).get("economic_alignment_rl", {})

                if coupling_data:
                    st.subheader("📊 市场对比")
                    for market, data in coupling_data.items():
                        rl_market = rl_data.get(market, {})
                        with st.expander(f"{market.upper()} 市场 — 情绪: {data.get('final_sentiment', 0):.3f} | {rl_market.get('final_strategies_count', 0)} RL agents"):
                            col_a, col_b = st.columns(2)
                            with col_a:
                                st.write("**耦合统计**")
                                st.write(f"轮数: {data.get('rounds', '?')}")
                                st.write(f"最终情绪: {data.get('final_sentiment', '?')}")
                            with col_b:
                                st.write("**RL 统计**")
                                st.write(f"活跃轮数: {rl_market.get('rounds_with_updates', '?')}/30")
                                strategies = rl_market.get('avg_final_strategies', {})
                                if strategies:
                                    strat_df = pd.DataFrame([
                                        {"策略维度": k, "值": v} for k, v in strategies.items()
                                    ])
                                    st.bar_chart(strat_df.set_index("策略维度"), height=200)

            # ── Tab 3: Coupling & Network ──
            with tab3:
                st.subheader("🕸️ 跨域耦合 & 小世界网络")

                # Sentiment timeline
                sim_stage = stages.get("simulation", {})
                timeline = []
                if isinstance(sim_stage, dict):
                    # Try to get timeline from the full result
                    final_report = result.get("final_report", {})
                    # We stored coupling_history in the simulation output
                    # Use the raw timeline from simulation log
                    pass

                # Show sentiment over rounds if we have timeline data
                # (timeline is per-market in the sim_result, not in pipeline output)
                st.info("📈 市场情绪通过小世界网络每轮传播\n"
                        "• 负向情绪传播速度 2x (negativity bias)\n"
                        "• FOMO 触发: 3+ 同伴购买 → +25% 购买概率\n"
                        "• 情绪影响支付意愿: 兴奋 +30%, 沮丧 -50%")

                # Network stats
                st.subheader("🌐 网络拓扑 — Watts-Strogatz 小世界")
                st.markdown("""
                ```
                全连接网络: 过早收敛, 杀死多样性 ✗
                环形网络:   扩散太慢, 保留多样性但无传播 ✗
                小世界网络: 最优平衡 — 既保留多样性又有传播速度 ✓
                ```
                """)

                if coupling_data:
                    for market, data in coupling_data.items():
                        st.metric(
                            f"{market.upper()} 最终情绪",
                            f"{data.get('final_sentiment', 0):.3f}",
                            f"{data.get('rounds', 0)} rounds",
                        )

            # ── Tab 4: RL Strategy ──
            with tab4:
                st.subheader("🧠 经济对齐 RL — 策略自适应")

                st.markdown("""
                **5 轴策略向量** (每个 Agent 独立学习):
                - `price_sensitivity` — 价格敏感度
                - `early_adopter` — 尝鲜倾向
                - `social_susceptibility` — 社交影响力敏感度
                - `loyalty` — 忠诚度 (低=容易流失)
                - `risk_tolerance` — 风险承受力
                """)

                for market, data in rl_data.items():
                    strategies = data.get('avg_final_strategies', {})
                    if strategies:
                        st.subheader(f"{market.upper()} 市场 — 平均策略演化 ({data['rounds_with_updates']}/30 轮活跃)")
                        strat_df = pd.DataFrame({
                            "维度": list(strategies.keys()),
                            "终值": list(strategies.values()),
                        })
                        st.bar_chart(strat_df.set_index("维度"), height=250)

                        # B2C vs SMB comparison
                        st.caption("B2C 消费者 vs SMB 商家策略差异:")
                        if "b2c" in rl_data and "smb" in rl_data:
                            b2c_strat = rl_data["b2c"].get("avg_final_strategies", {})
                            smb_strat = rl_data["smb"].get("avg_final_strategies", {})
                            if b2c_strat and smb_strat:
                                compare_df = pd.DataFrame({
                                    "维度": list(b2c_strat.keys()),
                                    "B2C 消费者": list(b2c_strat.values()),
                                    "SMB 商家": list(smb_strat.values()),
                                })
                                st.bar_chart(compare_df.set_index("维度"), height=300)

            # ── Tab 5: Raw Data ──
            with tab5:
                st.subheader("📋 完整 JSON 输出")
                st.json(result.get("final_report", {}).get("synthesis", {}))

                st.subheader("模拟日志")
                st.code("\n".join(sim_lines[-50:]), language="text")

                st.download_button(
                    "📥 下载完整结果 (JSON)",
                    json.dumps(result, indent=2, ensure_ascii=False),
                    f"marketfish_v4_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                )

        else:
            st.error(f"❌ 管道失败: {result.get('error', 'Unknown')}")
            st.write(f"失败阶段: {result.get('failed_at_stage', '?')}")
            st.write(f"已完成: {result.get('stages_completed', [])}")

    except Exception as e:
        builtins.print = original_print
        st.error(f"💥 致命错误: {e}")
        import traceback
        st.code(traceback.format_exc())

else:
    # ── Idle state: show last run results if available ──
    result_files = []
    for f in os.listdir("uploads"):
        if f.startswith("latest_v4") and f.endswith(".json"):
            result_files.append(f)

    if result_files:
        latest = sorted(result_files)[-1]
        st.info(f"📁 上次运行结果: `uploads/{latest}` — 点击「运行市场预测」开始新的分析")

        with st.expander("📊 查看上次结果"):
            try:
                with open(f"uploads/{latest}", encoding='utf-8') as f:
                    last_result = json.load(f)

                status = last_result.get("pipeline_status", "?")
                elapsed = last_result.get("elapsed_seconds", 0)
                stages = last_result.get("stages_completed", [])

                col1, col2, col3 = st.columns(3)
                col1.metric("状态", status)
                col2.metric("耗时", f"{elapsed:.0f}s" if elapsed else "?")
                col3.metric("阶段", f"{len(stages)}/6")

                # Product results
                sim_results = last_result.get("final_report", {}).get("simulation_results", [])
                if sim_results:
                    st.write("**产品存活情况:**")
                    for r in sim_results:
                        icon = "🟢" if r.get("status") == "alive" else "🔴"
                        st.write(f"{icon} {r.get('product_name','?')[:40]} — score={r.get('survival_score','?')}")

            except Exception:
                st.warning("无法加载上次结果")
    else:
        st.info("👆 点击「运行市场预测」启动 6-LLM 多智能体市场模拟")

# ── Footer ──
st.divider()
st.caption("MarketFish v4 · 16 academic papers · 6 LLMs · Built by Keystart AI · https://github.com/key-night-day/market-fish")
