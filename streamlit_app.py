"""
MarketFish v5 — Live Dashboard
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
    page_title="MarketFish v5 — 市场预测引擎",
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
st.markdown('<p class="main-header"> MarketFish v5</p>', unsafe_allow_html=True)
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

    st.subheader("输入模式")
    input_mode = st.radio("", ["explore", "validate", "hybrid"],
                          format_func=lambda m: {"explore": "🔍 探索", "validate": "✅ 验证", "hybrid": "⚔️ 混合"}[m])

    user_product = None
    if input_mode in ("validate", "hybrid"):
        with st.expander("📝 产品信息", expanded=True):
            product_name = st.text_input("产品名", placeholder="一键翻译")
            product_desc = st.text_area("描述", placeholder="复制文本自动弹窗翻译，无需切换App")
            product_target = st.selectbox("目标市场", ["consumer", "smb", "enterprise"])
            product_price = st.text_input("定价", placeholder="¥3-6 一次性")
            if product_name:
                user_product = {"name": product_name, "description": product_desc,
                                "target_market": product_target, "pricing": product_price}

    st.subheader("模型配置")
    from engine.model_registry import get_registry
    registry = get_registry()
    status = registry.status_report()
    for name, s in status.items():
        st.markdown(f"{'🟢' if s['key_configured'] else '⚫'} {name}")

    st.divider()
    st.caption(f"v5.0 · {datetime.now().strftime('%Y-%m-%d %H:%M')}")

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
from engine.agent_factory import _get_batches
AGENT_BATCHES = _get_batches()
total_agent_target = sum(b['count'] for b in AGENT_BATCHES)
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Mode", {"explore": "探索", "validate": "验证", "hybrid": "混合"}[input_mode])
col2.metric("Target Agents", str(total_agent_target), f"{len(AGENT_BATCHES)} batches")
col3.metric("Sim Rounds", "30")
col4.metric("Seed Sources", str(len(seed)))
col5.metric("Providers", str(sum(1 for s in status.values() if s['key_configured'])), f"/{len(status)} active")

# ── Calibration Section ──
with st.expander("🧪 校准验证 — 20个已知产品验证准确率", expanded=False):
    st.caption("用已知成败的外部产品独立验证管道预测能力。方向性验证（非统计显著性）。")

    from engine.config import calibration_cases
    cases = calibration_cases()
    tested = [c for c in cases if c['outcome'] != 'untested']

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("案例总数", len(cases))
    c2.metric("成功", sum(1 for c in cases if c['outcome'] == 'success'))
    c3.metric("失败", sum(1 for c in cases if c['outcome'] == 'failure'))
    c4.metric("预计耗时", f"~{len(tested) * 5}min")

    with st.expander("📋 查看全部案例", expanded=False):
        for c in cases:
            icon = "🟢" if c['outcome'] == 'success' else ("🔴" if c['outcome'] == 'failure' else "⚪")
            source = "公开" if not c['name'].startswith('某') else "脱敏"
            st.caption(f"{icon} {c['name'][:40]} | {c['target_market']} | {c['pricing'][:25]} | {source} · {c.get('evidence','')[:60]}")

    cal_col1, cal_col2 = st.columns([1, 3])
    with cal_col1:
        cal_runs = st.selectbox("每案例跑几次", [1, 3, 5], index=1, help="多次取mode减少随机性")
        cal_btn = st.button("🚀 运行校准", type="secondary", use_container_width=True,
                           help=f"用{len(tested)}个已知产品验证管道。预计{len(tested)*cal_runs*5}分钟。不调LLM则用模拟基线。")

    if cal_btn:
        with cal_col2:
            st.info("⏳ 校准功能已就绪。完整校准需调用 LLM，耗时较长。")
            st.caption("以下为基线参考（无需 LLM）：")

        # Run keyword baseline (fast, no LLM)
        from engine.calibrate import baseline_keyword, baseline_random, analyze_patterns
        kw_correct = 0
        for c in tested:
            kw = baseline_keyword(c)
            if kw['predicted'] == c['outcome']:
                kw_correct += 1

        patterns = analyze_patterns(cases)

        r1, r2, r3 = st.columns(3)
        r1.metric("关键词基线准确率", f"{kw_correct}/{len(tested)} ({kw_correct/len(tested):.0%})")
        r2.metric("随机基线准确率", "50%")
        r3.metric("模拟需跑管道", f"~{len(tested)*cal_runs*5}min")

        with st.expander("📊 因子分析 (来自20案例)", expanded=False):
            for f, d in patterns['factor_analysis'].items():
                disc = d['discrimination']
                bar = "█" * int(abs(disc) * 20) + ("░" * (20 - int(abs(disc) * 20)))
                st.write(f"{f}: 成功{d['success_rate']:.0%} vs 失败{d['failure_rate']:.0%} (区分度 {disc:+.2f}) {bar}")

# ── Main: Run Pipeline ──
st.divider()

run_col1, run_col2 = st.columns([1, 4])
with run_col1:
    run_btn = st.button("🚀 运行市场预测", type="primary", use_container_width=True)

# Load last result for display when idle
_last_result = None
if not run_btn:
    try:
        result_files = [f for f in os.listdir("uploads") if f.endswith(".json") and "validate" in f]
        if result_files:
            latest = sorted(result_files)[-1]
            with open(f"uploads/{latest}", encoding='utf-8') as lf:
                _last_result = json.load(lf)
    except Exception:
        pass

status_container = st.container()

if run_btn or _last_result:

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
    sim_lines = []

    if run_btn:
        # Patch simulator to stream progress to Streamlit
        import engine.simulator as sim_module
        original_print = builtins.print
        def stream_print(*args, **kwargs):
            msg = " ".join(str(a) for a in args)
            sim_lines.append(msg)
            if "[SIM]" in msg:
                sim_log_placeholder.code("\n".join(sim_lines[-15:]), language="text")
            original_print(*args, **kwargs)
        builtins.print = stream_print

    try:
        if run_btn:
            # Stage 1 — run full pipeline
            result = pipeline.run(seed_data=seed, mode=input_mode, user_product=user_product)
            elapsed = time.time() - t0
            builtins.print = original_print
        else:
            # Use cached result
            result = _last_result
            elapsed = result.get("elapsed_seconds", 0)
            # Mark all progress bars as done
            for k, bar in progress_bars.items():
                bar.progress(100)

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

            tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
                "📊 产品预测", "📋 证据报告", "🤖 Agent 总览", "🕸️ Agent 图谱",
                "💬 Agent 对话", "🕸️ 耦合 & 网络", "🧠 RL 策略", "📋 原始数据"
            ])

            # ── Tab 1: Product Predictions ──
            with tab1:
                st.subheader("🎯 产品方向生存预测")

                directions = result.get("product_directions", [])
                sim_results_raw = result.get("final_report", {}).get("simulation_results", [])
                # Deduplicate by product name (same product appears per-market)
                seen = {}
                sim_results = []
                for r in sim_results_raw:
                    name = r.get('product_name', '')
                    if name not in seen:
                        seen[name] = dict(r)
                        sim_results.append(seen[name])
                    else:
                        seen[name]['purchasers'] = seen[name].get('purchasers',0) + r.get('purchasers',0)
                        seen[name]['total_revenue_cny'] = round(seen[name].get('total_revenue_cny',0) + r.get('total_revenue_cny',0), 2)
                        seen[name]['survival_score'] = max(seen[name].get('survival_score',0), r.get('survival_score',0))

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

            # ── Tab 2: Evidence Report ──
            with tab2:
                st.subheader("📋 证据报告 — 不只是分数")

                sim_results = result.get("final_report", {}).get("simulation_results", [])
                sim_stage = result.get("stages", {}).get("simulation", {})
                coupling_stats = sim_stage.get("cross_domain_coupling", {})
                sim_log = sim_stage.get("sim_log", [])

                if sim_results:
                    # Try to rebuild agent_states from simulation log
                    agent_states = {}
                    if sim_log:
                        from engine.evidence_report import _rebuild_agent_states_from_log
                        agent_states = _rebuild_agent_states_from_log(result)
                        st.caption(f"从 {len(sim_log)} 条模拟日志重建了 {len(agent_states)} 个 agent 状态")
                    else:
                        st.warning("⚠️ 此结果来自旧版管道，缺少模拟日志。新管道运行后会有完整证据链。")
                        st.caption("以下是基于汇总数据的有限分析：")

                    # Dedup products
                    seen = {}
                    for r in sim_results:
                        name = r.get('product_name', '')
                        if name not in seen:
                            seen[name] = dict(r)
                        else:
                            seen[name]['purchasers'] = seen[name].get('purchasers',0) + r.get('purchasers',0)
                            seen[name]['total_revenue_cny'] = round(seen[name].get('total_revenue_cny',0) + r.get('total_revenue_cny',0), 2)

                    for pname, p in seen.items():
                        score = p.get("survival_score", 0)
                        status = p.get("status", "dead")
                        emoji = "🟢" if status == "alive" else ("🟡" if status == "struggling" else "🔴")

                        with st.expander(f"{emoji} {pname[:40]} — score: {score:.2f} | {p.get('purchasers',0)} buyers | ¥{p.get('total_revenue_cny',0)}"):
                            try:
                                agents_list = result.get("stages", {}).get("agents_v2", {}).get("agents", [])
                                from engine.evidence_report import build_buyer_profile, compare_with_competitors, generate_risk_signals, extract_purchase_reasons

                                buyer = build_buyer_profile(p.get('product_id',''), agent_states, agents_list)
                                comps = compare_with_competitors(p.get('product_id',''), sim_results)
                                risks = generate_risk_signals(p.get('product_id',''), buyer, coupling_stats)

                                c1, c2 = st.columns(2)
                                with c1:
                                    st.write("**买家画像**")
                                    if buyer["total_buyers"] > 0:
                                        for seg in buyer["segments"]:
                                            st.write(f"- {seg['name']}: {seg['pct']}%")
                                        st.write(f"平均月预算: ¥{buyer['avg_budget']}")
                                    else:
                                        st.write("买家细节需模拟日志（新管道运行后可用）")
                                        st.write(f"买家总数: {p.get('purchasers', 0)}")
                                        st.write(f"营收: ¥{p.get('total_revenue_cny', 0)}")

                                    st.write("**风险信号**")
                                    for r in risks:
                                        level_color = {"low": "green", "medium": "orange", "high": "red"}
                                        st.markdown(f":{level_color.get(r['level'],'gray')}[{r['signal']}] — {r['detail']}")

                                with c2:
                                    st.write("**竞品对比**")
                                    for c in comps:
                                        icon = "🟢" if c["status"] == "alive" else "🔴"
                                        death = f" — {c['death_cause']}" if c.get("death_cause") else ""
                                        st.write(f"{icon} {c['name'][:25]}: score={c['score']:.2f}, buyers={c['purchasers']}{death}")

                                    # Show purchase motivation if log available
                                    if sim_log:
                                        reasons = extract_purchase_reasons(p.get('product_id',''), agent_states)
                                        if reasons:
                                            st.write("**购买动机 (示例)**")
                                            for r in reasons[:3]:
                                                st.caption(f"\"{r['reasoning'][:80]}\"")

                            except Exception as e:
                                st.caption(f"证据提取受限: {e}")
                else:
                    st.info("无模拟结果数据")

            # ── Tab 3: Agent Overview ──
            with tab3:
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

            # ── Tab 4: Agent Graph ──
            with tab4:
                st.subheader("🕸️ Agent 社交网络")

                agents_list = result.get("stages", {}).get("agents_v2", {}).get("agents", [])
                if agents_list:
                    try:
                        from engine.network_viz import build_agent_graph_html
                        graph_html = build_agent_graph_html(agents_list, height="550px")
                        st.components.v1.html(graph_html, height=580, scrolling=False)
                        st.caption(f"{len(agents_list)} agents · 小世界网络")
                    except Exception as e:
                        st.warning(f"图谱生成失败: {e}")
                else:
                    st.info("无 agent 数据")

                # Bipartite graph
                sim_results = result.get("final_report", {}).get("simulation_results", [])
                if sim_results:
                    st.subheader("📊 产品-买家 二分图")
                    try:
                        from engine.network_viz import build_bipartite_graph_html
                        bp_html = build_bipartite_graph_html(sim_results, {}, agents_list, height="500px")
                        st.components.v1.html(bp_html, height=530, scrolling=False)
                    except Exception as e:
                        st.caption(f"二分图暂不可用: {e}")

            # ── Tab 5: Agent Dialogue ──
            with tab5:
                st.subheader("💬 和 Agent 对话")
                st.caption("选中一个 agent，用它的身份和你聊天")

                agents_list = result.get("stages", {}).get("agents_v2", {}).get("agents", [])
                sim_stage_data = result.get("stages", {}).get("simulation", {})
                sim_log_data = sim_stage_data.get("sim_log", [])

                if agents_list:
                    # Build agent_states from sim_log if available, else minimal
                    agent_states = {}
                    if sim_log_data:
                        from engine.evidence_report import _rebuild_agent_states_from_log
                        agent_states = _rebuild_agent_states_from_log(result)

                    from engine.agent_dialogue import list_chatable_agents
                    chatable = list_chatable_agents(agents_list, agent_states, min_history=0)
                    agent_options = {f"{a['name'][:20]} ({a['type']})" : a["id"] for a in chatable[:30]}

                    if agent_options:
                        # Session state for chat history
                        if "dialogue_history" not in st.session_state:
                            st.session_state.dialogue_history = {}
                        if "selected_agent" not in st.session_state:
                            st.session_state.selected_agent = None

                        selected_label = st.selectbox("选择 Agent", list(agent_options.keys()),
                            key="agent_selector")
                        st.session_state.selected_agent = agent_options[selected_label]

                        # Show agent profile summary
                        selected_id = st.session_state.selected_agent
                        agent_profile = next((a for a in agents_list if a["id"] == selected_id), None)
                        if agent_profile:
                            bdi = agent_profile.get("bdi", {})
                            st.caption(f"类型: {agent_profile.get('type','?')} | "
                                      f"预算: ¥{agent_profile.get('budget_monthly_cny','?')} | "
                                      f"决策: {agent_profile.get('decision_speed','?')}")
                            if bdi.get("beliefs"):
                                st.caption(f"信念: {', '.join(bdi['beliefs'][:2])}")

                        user_msg = st.text_input("你的消息", placeholder="你为什么会买这个产品？", key="chat_input")

                        if user_msg:
                            # Get or init chat history for this agent
                            if selected_id not in st.session_state.dialogue_history:
                                st.session_state.dialogue_history[selected_id] = []

                            with st.spinner(f"{agent_profile.get('name', selected_id)} 正在思考..."):
                                try:
                                    from engine.agent_dialogue import chat_with_agent
                                    response = chat_with_agent(
                                        selected_id, user_msg, agents_list,
                                        agent_states if agent_states else {selected_id: {
                                            "profile": agent_profile, "history": [], "purchased_products": {},
                                            "emotional_state": "neutral", "rl_strategy": {}, "total_spent": 0
                                        }},
                                    )
                                    reply = response.get("response", "（无法回复）")
                                    st.session_state.dialogue_history[selected_id].append(
                                        {"role": "user", "content": user_msg})
                                    st.session_state.dialogue_history[selected_id].append(
                                        {"role": "agent", "content": reply})
                                except Exception as e:
                                    st.error(f"对话失败: {e}")

                        # Show chat history
                        if selected_id in st.session_state.dialogue_history:
                            for msg in st.session_state.dialogue_history[selected_id][-10:]:
                                if msg["role"] == "user":
                                    st.markdown(f"**你:** {msg['content']}")
                                else:
                                    st.markdown(f"**{agent_profile.get('name', 'Agent')}:** {msg['content']}")
                    else:
                        st.info("无可对话的 agent — 请先运行管道")
                else:
                    st.info("无 agent 数据 — 请先运行管道")

            # ── Tab 6: Coupling & Network ──
            with tab6:
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

            # ── Tab 7: RL Strategy ──
            with tab7:
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

            # ── Tab 8: Raw Data ──
            with tab8:
                st.subheader("📋 完整 JSON 输出")
                st.json(result.get("final_report", {}).get("synthesis", {}))

                st.subheader("模拟日志")
                st.code("\n".join(sim_lines[-50:]), language="text")

                st.download_button(
                    "📥 下载完整结果 (JSON)",
                    json.dumps(result, indent=2, ensure_ascii=False),
                    f"marketfish_v5_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                )

        else:
            st.error(f"❌ 管道失败: {result.get('error', 'Unknown')}")
            st.write(f"失败阶段: {result.get('failed_at_stage', '?')}")
            st.write(f"已完成: {result.get('stages_completed', [])}")

    except Exception as e:
        if run_btn:
            builtins.print = original_print
        st.error(f"💥 致命错误: {e}")
        import traceback
        st.code(traceback.format_exc())

else:
    st.info("👆 点击「🚀 运行市场预测」启动全管道。已有的验证结果会自动加载。")

    # Clean up old idle code
    if False:
        latest = sorted(result_files)[-1]
        filepath = f"uploads/{latest}"
        try:
            with open(filepath, encoding='utf-8') as f:
                last_result = json.load(f)
        except Exception:
            last_result = None

        if last_result:
            st.success(f"📁 上次运行: `{latest}` ({last_result.get('elapsed_seconds',0):.0f}s, {last_result.get('input_mode','?')} mode)")

            if st.button("📊 展开完整报告", use_container_width=True):
                # Re-use the same tab display logic from above by setting result
                result = last_result
                sim_lines = []
                # Show tabs (same code as post-run)
                if result.get("pipeline_status") == "complete":
                    st.balloons()
                    # Re-import tab rendering by re-running the tab block inline
                    # For now, show key metrics
                    sim_results = result.get("final_report", {}).get("simulation_results", [])
                    # Deduplicate by product name
                    seen_names = {}
                    unique_results = []
                    for r in sim_results:
                        name = r.get('product_name', '')
                        if name not in seen_names:
                            seen_names[name] = r
                            unique_results.append(r)
                        else:
                            # Merge: sum purchasers and revenue
                            seen_names[name]['purchasers'] = seen_names[name].get('purchasers',0) + r.get('purchasers',0)
                            seen_names[name]['total_revenue_cny'] = round(
                                seen_names[name].get('total_revenue_cny',0) + r.get('total_revenue_cny',0), 2)
                            seen_names[name]['survival_score'] = max(
                                seen_names[name].get('survival_score',0), r.get('survival_score',0))

                    if unique_results:
                        st.subheader("🎯 产品预测")
                        cols = st.columns(min(len(unique_results), 4))
                        for i, name in enumerate(list(seen_names.keys())[:4]):
                            r = seen_names[name]
                            with cols[i % 4]:
                                status = r.get("status", "dead")
                                emoji = "🟢" if status == "alive" else "🔴"
                                st.metric(f"{emoji} {name[:25]}",
                                    f"Score: {r.get('survival_score',0):.2f}",
                                    f"Buyers: {r.get('purchasers',0)} | Rev: ¥{r.get('total_revenue_cny',0)}")

                    # Show coupling & RL summary
                    sim_stage = result.get("stages", {}).get("simulation", {})
                    coupling = sim_stage.get("cross_domain_coupling", {})
                    rl_data = sim_stage.get("economic_alignment_rl", {})
                    if coupling:
                        st.subheader("📊 市场对比")
                        c1, c2 = st.columns(2)
                        for idx, (mkt, data) in enumerate(coupling.items()):
                            rl_mkt = rl_data.get(mkt, {})
                            with [c1, c2][idx % 2]:
                                st.metric(f"{mkt.upper()} 情绪", f"{data.get('final_sentiment',0):.3f}")
                                st.metric("RL Agents", rl_mkt.get('final_strategies_count', 0))
                        # Total unique buyers across all markets
                        total_buyers = sum(seen_names[n].get('purchasers', 0) for n in seen_names)
                        st.metric("总买家", total_buyers)
                    st.info("💡 点击「🚀 运行市场预测」触发完整管道，跑完后可查看全部 8 个 tab")
                else:
                    st.error(f"管道失败: {result.get('error','?')}")
    else:
        st.info("👆 点击「🚀 运行市场预测」启动全管道。上次验证结果: `v5_validate_v3.json` (蜜洲翻译, 51min, 6/6 stages)")

# ── Footer ──
st.divider()
st.caption("MarketFish v5 · 16 academic papers · 6 LLMs · Built by Keystart AI · https://github.com/key-night-day/market-fish")
