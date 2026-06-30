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
from engine.i18n import t, tabs as i18n_tabs, get_lang, set_lang

st.set_page_config(
    page_title=t("page.title"),
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
    # Language toggle
    if "lang" not in st.session_state:
        st.session_state.lang = "zh"
    lang = st.radio(t("sidebar.language"), ["🇨🇳 中文", "🇺🇸 English"],
                    index=0 if get_lang() == "zh" else 1,
                    horizontal=True)
    set_lang("zh" if lang == "🇨🇳 中文" else "en")

    st.header(t("sidebar.title"))

    st.subheader(t("sidebar.seed_sources"))
    seed_sources = st.multiselect(
        t("sidebar.select_sources"),
        ["freelancer", "economy", "tech", "consumer", "b2b"],
        default=["freelancer", "economy", "tech", "consumer", "b2b"],
    )

    st.subheader(t("sidebar.input_mode"))
    input_mode = st.radio("", ["explore", "validate", "hybrid"],
                          format_func=lambda m: {"explore": t("sidebar.explore"), "validate": t("sidebar.validate"), "hybrid": t("sidebar.hybrid")}[m])

    user_product = None
    if input_mode in ("validate", "hybrid"):
        with st.expander(t("sidebar.product_info"), expanded=True):
            product_name = st.text_input(t("sidebar.product_name"), placeholder=t("sidebar.product_name_placeholder"))
            product_desc = st.text_area(t("sidebar.product_desc"), placeholder=t("sidebar.product_desc_placeholder"))
            product_target = st.selectbox(t("sidebar.product_target"), ["consumer", "smb", "enterprise"])
            product_price = st.text_input(t("sidebar.product_price"), placeholder=t("sidebar.price_placeholder"))
            if product_name:
                user_product = {"name": product_name, "description": product_desc,
                                "target_market": product_target, "pricing": product_price}

    st.subheader(t("sidebar.sim_params"))
    sim_rounds = st.slider(t("sidebar.sim_rounds"), 10, 50, 30, 5,
                           help=t("sidebar.rounds_help"))
    agent_count = st.select_slider(t("sidebar.agent_count"),
                                    options=[30, 50, 100, 200, 500, 1000, 5000, 10000],
                                    value=50,
                                    help=t("sidebar.agent_help"))
    agent_cap = min(agent_count, 128)  # v5 max: 128 agents (8 batches × 16)
    if agent_count > 128:
        st.warning(t("sidebar.agent_limit_warn", n=agent_count))

    st.subheader(t("sidebar.model_config"))
    from engine.model_registry import get_registry
    registry = get_registry()
    status = registry.status_report()
    for name, s in status.items():
        st.markdown(f"{'🟢' if s['key_configured'] else '⚫'} {name}")

    st.divider()

    st.subheader(t("sidebar.load_result"))
    uploaded_result = st.file_uploader(t("sidebar.load_result") + " JSON", type=["json"], key="result_uploader",
                                        help=t("sidebar.load_help"))
    if uploaded_result is not None:
        try:
            st.session_state.uploaded_result = json.loads(uploaded_result.read())
            st.success(t("sidebar.load_success", name=uploaded_result.name))
        except Exception as e:
            st.error(t("sidebar.load_fail", error=str(e)))
    elif st.button(t("sidebar.reset"), use_container_width=True, help=t("sidebar.reset_help")):
        st.session_state.pop("uploaded_result", None)
        st.session_state.pop("agent_states", None)
        st.session_state.pop("dialogue_history", None)
        st.rerun()

    st.divider()
    st.caption(f"v5.0 · {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    st.caption("[GitHub](https://github.com/key-night-day/market-fish) · Keystart AI")
    st.caption(t("sidebar.lang_status"))

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
            st.warning(t("pipeline.seed_missing", path=path))
    return seed

seed = load_seed_data(tuple(seed_sources))

if not seed:
    st.error(t("pipeline.no_seed"))
    st.stop()

# ── KPI Bar ──
from engine.config import agent_batches
AGENT_BATCHES = agent_batches()
total_agent_target = sum(b['count'] for b in AGENT_BATCHES)
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric(t("kpi.mode"), {"explore": t("sidebar.explore"), "validate": t("sidebar.validate"), "hybrid": t("sidebar.hybrid")}[input_mode])
col2.metric("Target Agents", str(total_agent_target), f"{len(AGENT_BATCHES)} batches")
col3.metric("Sim Rounds", str(sim_rounds))
col4.metric("Seed Sources", str(len(seed)))
col5.metric("Providers", str(sum(1 for s in status.values() if s['key_configured'])), f"/{len(status)} active")

# ── Seed Data Transparency ──
with st.expander(t("seed_transparency.title"), expanded=False):
    st.caption(t("seed_transparency.desc"))
    for key in seed_sources:
        meta = seed.get(key, {}).get("_meta", {})
        if meta:
            with st.expander(f"{key} — {meta.get('source','?')[:60]}...", expanded=False):
                st.write(t("seed_transparency.collection_label", v=meta.get("collection_method","?")))
                st.write(t("seed_transparency.bias_label", v=meta.get("bias_declaration","?")))
                st.write(f"**局限**: {', '.join(meta.get('limitations',['?']))}")

    # File upload for custom seed data
    st.divider()
    st.caption(t("seed_transparency.upload_hint"))
    uploaded_seed = st.file_uploader(t("seed_transparency.upload_label"),
                                      type=["json"], key="seed_uploader")
    if uploaded_seed is not None:
        try:
            custom = json.loads(uploaded_seed.read())
            seed.update(custom)
            st.success(t("seed_transparency.merged", n=len(custom)))
        except Exception as e:
            st.error(t("pipeline.json_error", e=str(e)))

# ── Calibration Section ──
with st.expander(t("calibration.title"), expanded=False):
    st.caption(t("calibration.desc"))

    from engine.config import calibration_cases
    cases = calibration_cases()
    tested = [c for c in cases if c['outcome'] != 'untested']

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("calibration.total_cases"), len(cases))
    c2.metric(t("calibration.success"), sum(1 for c in cases if c['outcome'] == 'success'))
    c3.metric(t("calibration.failure"), sum(1 for c in cases if c['outcome'] == 'failure'))
    c4.metric(t("calibration.estimated_time"), f"~{len(tested) * 5}min")

    with st.expander(t("calibration.view_all"), expanded=False):
        for c in cases:
            icon = "🟢" if c['outcome'] == 'success' else ("🔴" if c['outcome'] == 'failure' else "⚪")
            source = t("calibration.public") if not c["name"].startswith("某") else t("calibration.anon")
            st.caption(f"{icon} {c['name'][:40]} | {c['target_market']} | {c['pricing'][:25]} | {source} · {c.get('evidence','')[:60]}")

    cal_col1, cal_col2 = st.columns([1, 3])
    with cal_col1:
        cal_runs = st.selectbox(t("calibration.runs_label"), [1, 3, 5], index=1, help=t("calibration.runs_help"))
        cal_btn = st.button(t("calibration.run_cal_btn"), type="secondary", use_container_width=True,
                           help=t("calibration.run_help_full", n=len(tested), t=len(tested)*cal_runs*5))

    if cal_btn:
        with cal_col2:
            st.info(t("calibration.ready_note"))
            st.caption(t("calibration.baseline_note"))

        # Run keyword baseline (fast, no LLM)
        from engine.calibrate import baseline_keyword, baseline_random, analyze_patterns
        kw_correct = 0
        for c in tested:
            kw = baseline_keyword(c)
            if kw['predicted'] == c['outcome']:
                kw_correct += 1

        patterns = analyze_patterns(cases)

        r1, r2, r3 = st.columns(3)
        r1.metric(t("calibration.keyword_acc"), f"{kw_correct}/{len(tested)} ({kw_correct/len(tested):.0%})")
        r2.metric(t("calibration.random_accuracy"), "50%")
        r3.metric(t("calibration.sim_estimate"), f"~{len(tested)*cal_runs*5}min")

        with st.expander(t("calibration.factor_analysis"), expanded=False):
            for f, d in patterns['factor_analysis'].items():
                disc = d['discrimination']
                bar = "█" * int(abs(disc) * 20) + ("░" * (20 - int(abs(disc) * 20)))
                st.write(f"{f}: {t('calibration.success')} {d['success_rate']:.0%} vs {t('calibration.failure')} {d['failure_rate']:.0%} ({t('calibration.disc')} {disc:+.2f}) {bar}")

# ── Main: Run Pipeline ──
st.divider()

run_col1, run_col2 = st.columns([1, 4])
with run_col1:
    run_btn = st.button(t("pipeline.btn"), type="primary", use_container_width=True, key=f"run_btn_{get_lang()}")

# Load last result for display when idle
_last_result = None
if not run_btn:
    # Check for manually uploaded result first
    if "uploaded_result" in st.session_state:
        _last_result = st.session_state.uploaded_result
    else:
        try:
            result_files = [f for f in os.listdir("uploads") if f.endswith(".json") and "validate" in f]
            if result_files:
                latest = max(result_files, key=lambda f: os.path.getmtime(f"uploads/{f}"))
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
        "ontology": st.progress(0, t("pipeline.stages.ontology")),
        "graph": st.progress(0, t("pipeline.stages.graph")),
        "agents": st.progress(0, t("pipeline.stages.agents")),
        "simulation": st.progress(0, t("pipeline.stages.simulation")),
        "report": st.progress(0, t("pipeline.stages.report")),
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
            result = pipeline.run(seed_data=seed, mode=input_mode, user_product=user_product,
                                  sim_rounds=sim_rounds, agent_cap=agent_cap)
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
                stage_names = {"ontology":"1","graph":"2","agents":"3","simulation":"4","report":"5"}
                bar.progress(100, t("pipeline.stage_done", stage_num=stage_names.get(k,"?")))

        if result.get("pipeline_status") == "complete":
            st.balloons()
            st.success(t("pipeline.complete_msg", elapsed=f"{elapsed:.0f}", elapsed_m=f"{elapsed/60:.1f}"))

            # ═══════════════════════════════════════
            # RESULTS DASHBOARD
            # ═══════════════════════════════════════

            tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(i18n_tabs())

            # ── Tab 1: Product Predictions ──
            with tab1:
                st.subheader(t("evidence_tab.product_survival"))

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
                            f"{t('status.score')}: {r['survival_score']:.2f}",
                            f"{t('status.buyers')}: {r['purchasers']} | {t('status.rev')}: ¥{r['total_revenue_cny']}",
                        )

                # Plotly charts
                if sim_results:
                    from engine.dashboard_viz import survival_score_chart, adoption_curve, emotion_timeline
                    st.plotly_chart(survival_score_chart(sim_results), use_container_width=True, key="survival_score")

                    # Adoption curve + Emotion timeline side by side
                    sim_stage2 = result.get("stages", {}).get("simulation", {})
                    sim_log_viz = sim_stage2.get("sim_log", [])
                    timeline_data = sim_stage2.get("timeline", [])
                    c1, c2 = st.columns(2)
                    with c1:
                        if sim_log_viz:
                            st.plotly_chart(adoption_curve(sim_log_viz), use_container_width=True, key="adoption_curve")
                    with c2:
                        if timeline_data:
                            st.plotly_chart(emotion_timeline(timeline_data), use_container_width=True, key="emotion_timeline")

                # Backtest filter results
                st.subheader(t("evidence_tab.backtest_title"))
                if directions:
                    bt_df = pd.DataFrame([
                        {t("backtest.product"): d["name"][:25], t("backtest.score"): d.get("backtest_score", 0),
                         t("backtest.verdict"): d.get("backtest_verdict", "?"),
                         t("backtest.factors"): ", ".join(d.get("backtest_flags", [])),
                         t("backtest.killers"): ", ".join(d.get("backtest_kill_flags", []))}
                        for d in directions
                    ])
                    st.dataframe(bt_df, use_container_width=True, hide_index=True)

            # ── Tab 2: Evidence Report ──
            with tab2:
                st.subheader(t("evidence_tab.title"))

                sim_results = result.get("final_report", {}).get("simulation_results", [])
                sim_stage = result.get("stages", {}).get("simulation", {})
                coupling_stats = sim_stage.get("cross_domain_coupling", {})
                sim_log = sim_stage.get("sim_log", [])

                # Try to rebuild agent_states from simulation log (shared across tabs)
                if "agent_states" not in st.session_state:
                    st.session_state.agent_states = {}
                agent_states = {}
                if sim_log:
                    from engine.evidence_report import _rebuild_agent_states_from_log
                    agent_states = _rebuild_agent_states_from_log(result)
                    st.session_state.agent_states = agent_states
                    st.caption(t("evidence_tab.rebuilt", m=len(sim_log), n=len(agent_states)))
                else:
                    st.warning(t("evidence_tab.old_pipeline_warn"))
                    st.caption(t("evidence_tab.limited_analysis"))

                if sim_results:
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
                                from engine.dashboard_viz import buyer_segments_donut, rl_strategy_radar

                                buyer = build_buyer_profile(p.get('product_id',''), agent_states, agents_list)
                                comps = compare_with_competitors(p.get('product_id',''), sim_results)
                                risks = generate_risk_signals(p.get('product_id',''), buyer, coupling_stats)

                                c1, c2 = st.columns(2)
                                with c1:
                                    st.write(t("evidence_tab.buyers_label"))
                                    if buyer["total_buyers"] > 0:
                                        st.plotly_chart(buyer_segments_donut(buyer), use_container_width=True, key="buyer_donut")
                                    else:
                                        st.write(t("evidence_tab.buyer_details_only"))
                                        st.write(t("evidence_tab.total_buyers_fmt", n=p.get("purchasers", 0)))
                                        st.write(t("evidence_tab.revenue_fmt", n=p.get("total_revenue_cny", 0)))

                                    st.write(t("evidence_tab.risks_label"))
                                    for r in risks:
                                        level_color = {"low": "green", "medium": "orange", "high": "red"}
                                        st.markdown(f":{level_color.get(r['level'],'gray')}[{r['signal']}] — {r['detail']}")

                                with c2:
                                    # RL strategy radar
                                    rl_data = result.get("stages", {}).get("simulation", {}).get("economic_alignment_rl", {})
                                    if rl_data:
                                        st.plotly_chart(rl_strategy_radar(rl_data), use_container_width=True, key="rl_radar_evidence")

                                    st.write(t("evidence_tab.comps_label"))
                                    for c in comps:
                                        icon = "🟢" if c["status"] == "alive" else "🔴"
                                        death = f" — {c['death_cause']}" if c.get("death_cause") else ""
                                        st.write(f"{icon} {c['name'][:25]}: score={c['score']:.2f}, buyers={c['purchasers']}{death}")

                                    # Show purchase motivation if log available
                                    if sim_log:
                                        reasons = extract_purchase_reasons(p.get('product_id',''), agent_states)
                                        if reasons:
                                            st.write(t("evidence_tab.motivation_count", n=len(reasons)))
                                            for r in reasons[:5]:
                                                st.caption(f"\"{r['reasoning'][:80]}\"")

                            except Exception as e:
                                st.caption(t("evidence_tab.evidence_error", e=str(e)))

                        # ── Price Elasticity Scanner ──
                        with st.expander(t("price_scanner.title"), expanded=False):
                            st.caption(t("price_scanner.desc"))
                            price_input = st.text_input(t("price_scanner.price_input"), "1,3,6,9,12,18,30",
                                help=t("price_scanner.price_help"), key=f"price_input_{pname}")
                            scan_rounds = st.slider(t("price_scanner.rounds_label"), 10, 30, 15,
                                help=t("price_scanner.rounds_help"), key=f"scan_rounds_{pname}")

                            if st.button(t("price_scanner.scan_btn"), key=f"scan_btn_{pname}", type="primary"):
                                try:
                                    prices = [float(x.strip()) for x in price_input.replace("¥","").split(",") if x.strip()]
                                    if len(prices) < 2:
                                        st.error(t("price_scanner.min_prices"))
                                    else:
                                        from engine.price_scanner import scan_price_elasticity, build_elasticity_chart
                                        scan_agents = result.get("stages", {}).get("agents", {}).get("agents",
                                                        result.get("stages", {}).get("agents_v2", {}).get("agents", []))
                                        if not scan_agents:
                                            st.error(t("price_scanner.no_agents"))
                                        else:
                                            status_text = st.empty()
                                            progress = st.progress(0, t("price_scanner.progress"))
                                            def update_prog(i, total):
                                                progress.progress(i / total, t("price_scanner.progress", price=f"¥{prices[i-1]}", i=i, total=total))
                                                status_text.caption(t("price_scanner.done", done=i, total=total))

                                            with st.spinner(t("price_scanner.scanning", n=len(prices), r=scan_rounds)):
                                                for pname2, pdata in seen.items():
                                                    # Find original product from product_directions
                                                    prod_template = None
                                                    for pd_item in result.get("product_directions", []):
                                                        if (pd_item.get("name") == pname2 or
                                                            pd_item.get("product_name") == pname2):
                                                            prod_template = pd_item
                                                            break
                                                    if not prod_template:
                                                        prod_template = {"id": pdata.get("product_id", ""), "name": pname2}

                                                    scan_result = scan_price_elasticity(
                                                        product=prod_template,
                                                        agents=scan_agents,
                                                        price_points=prices,
                                                        rounds=scan_rounds,
                                                        progress_callback=update_prog,
                                                    )
                                                    status_text.empty()
                                                    progress.empty()

                                                    # Show chart
                                                    fig = build_elasticity_chart(scan_result)
                                                    st.plotly_chart(fig, use_container_width=True, key=f"elasticity_{pname2}")

                                                    # Summary table
                                                    cols = st.columns(3)
                                                    cols[0].metric(t("price_scanner.optimal_revenue"), f"¥{scan_result['optimal_price_by_revenue']}")
                                                    cols[1].metric(t("price_scanner.optimal_score"), f"¥{scan_result['optimal_price_by_score']}")
                                                    cols[2].metric(t("price_scanner.elapsed"), f"{scan_result['elapsed_seconds']}s")
                                                    st.success(scan_result["recommendation"])
                                                    break  # Only scan first product
                                except ValueError:
                                    st.error(t("price_scanner.price_error"))

                else:
                    st.info(t("evidence_tab.no_sim_data"))

            # ── Tab 3: Agent Overview ──
            with tab3:
                st.subheader(t("agents_tab.title"))

                stages = result.get("stages", {})
                agents_list3 = stages.get("agents_v2", {}).get("agents", [])
                agent_count = stages.get("agents_v2", {}).get("count", len(agents_list3))
                st.metric(t("agents_tab.total_label"), agent_count)

                # Agent type distribution (Plotly)
                if agents_list3:
                    from engine.dashboard_viz import agent_type_distribution, rl_strategy_radar
                    st.plotly_chart(agent_type_distribution(agents_list3), use_container_width=True)

                # Show coupling & RL stats per market
                coupling_data = stages.get("simulation", {}).get("cross_domain_coupling", {})
                rl_data = stages.get("simulation", {}).get("economic_alignment_rl", {})

                if rl_data:
                    from engine.dashboard_viz import rl_strategy_radar
                    st.plotly_chart(rl_strategy_radar(rl_data), use_container_width=True, key="rl_radar_overview")

                if coupling_data:
                    st.subheader(t("agents_tab.market_comparison"))
                    for market, data in coupling_data.items():
                        rl_market = rl_data.get(market, {})
                        s_val = f"{data.get('final_sentiment', 0):.3f}"
                        with st.expander(t("market.market_header", m=market.upper(), s=s_val, n=rl_market.get("final_strategies_count", 0))):
                            col_a, col_b = st.columns(2)
                            with col_a:
                                st.write(t("agents_tab.coupling_stats"))
                                st.write(t("market.rounds_label") + ": " + str(data.get("rounds","?")))
                                st.write(t("market.sentiment_label") + ": " + str(data.get("final_sentiment","?")))
                            with col_b:
                                st.write(t("agents_tab.rl_stats"))
                                st.write(t("market.active_rounds_label") + ": " + str(rl_market.get("rounds_with_updates","?")) + "/30")
                                st.write(t("market.final_strategies_label") + ": " + str(rl_market.get("avg_final_strategies", {})))

            # ── Tab 4: Agent Graph ──
            with tab4:
                st.subheader(t("graph_tab.title"))

                agents_list = result.get("stages", {}).get("agents_v2", {}).get("agents", [])
                if agents_list:
                    try:
                        from engine.network_viz import build_agent_graph_html
                        graph_html = build_agent_graph_html(agents_list, height="550px", title="")
                        st.components.v1.html(graph_html, height=580, scrolling=False)
                        st.caption(t("graph_tab.caption2", n=len(agents_list)))
                    except Exception as e:
                        st.warning(t("graph_tab.graph_error", e=str(e)))
                else:
                    st.info(t("graph_tab.no_agent_data2"))

                # Bipartite graph
                sim_results = result.get("final_report", {}).get("simulation_results", [])
                if sim_results:
                    st.subheader(t("graph_tab.bipartite_title"))
                    try:
                        from engine.network_viz import build_bipartite_graph_html
                        bp_html = build_bipartite_graph_html(sim_results, st.session_state.get("agent_states", {}), agents_list, height="500px")
                        st.components.v1.html(bp_html, height=530, scrolling=False)
                    except Exception as e:
                        st.caption(t("graph_tab.bipartite_error", e=str(e)))

            # ── Tab 5: Agent Dialogue ──
            with tab5:
                st.subheader(t("chat_tab.title"))
                st.caption(t("chat_tab.desc"))

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
                    st.caption(t("chat_tab.total", total=len(agents_list), active=len(chatable)))

                    # Show all agents with history first, then type filter
                    filter_type = st.selectbox(t("chat_tab.filter_type"), [t("chat_tab.filter_all")] + sorted(set(a.get("type","unknown") for a in chatable)), key="dialogue_filter")
                    if filter_type != t("chat_tab.filter_all"):
                        chatable = [a for a in chatable if a["type"] == filter_type]

                    agent_options = {}
                    for a in chatable:
                        label = f"{a['name'][:20]} ({a['type']})"
                        if a['purchases'] > 0:
                            label += f" 🛒{a['purchases']}"
                        agent_options[label] = a["id"]

                    if agent_options:
                        # Session state for chat history
                        if "dialogue_history" not in st.session_state:
                            st.session_state.dialogue_history = {}
                        if "selected_agent" not in st.session_state:
                            st.session_state.selected_agent = None

                        selected_label = st.selectbox(t("chat_tab.select_label"), list(agent_options.keys()),
                            key="agent_selector")
                        st.session_state.selected_agent = agent_options[selected_label]

                        # Show agent profile summary
                        selected_id = st.session_state.selected_agent
                        agent_profile = next((a for a in agents_list if a["id"] == selected_id), None)
                        if agent_profile:
                            bdi = agent_profile.get("bdi", {})
                            st.caption(t("chat_tab.type_info", t=agent_profile.get("type","?"), b=agent_profile.get("budget_monthly_cny","?"), d=agent_profile.get("decision_speed","?")))
                            if bdi.get("beliefs"):
                                st.caption(f"{t('chat_tab.beliefs')}: {', '.join(bdi['beliefs'][:2])}")

                        user_msg = st.text_input(t("chat_tab.your_message"), placeholder=t("chat_tab.msg_placeholder"), key="chat_input")

                        if user_msg:
                            # Get or init chat history for this agent
                            if selected_id not in st.session_state.dialogue_history:
                                st.session_state.dialogue_history[selected_id] = []

                            with st.spinner(t("chat_tab.thinking", name=agent_profile.get("name", selected_id))):
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
                                    st.error(t("chat_tab.chat_fail", e=str(e)))

                        # Show chat history
                        if selected_id in st.session_state.dialogue_history:
                            for msg in st.session_state.dialogue_history[selected_id][-10:]:
                                if msg["role"] == "user":
                                    st.markdown(f"**你:** {msg['content']}")
                                else:
                                    st.markdown(f"**{agent_profile.get('name', 'Agent')}:** {msg['content']}")
                    else:
                        st.info(t("chat_tab.no_chat_agents"))
                else:
                    st.info(t("chat_tab.no_agent_data2"))

            # ── Tab 6: Coupling & Network ──
            with tab6:
                st.subheader(t("evidence_tab.coupling_title"))

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
                st.info(t("network_tab.network_desc"))

                # Network stats
                st.subheader(t("network_tab.title2"))
                st.markdown(f"""
                ```
                {t("network_tab.fully_connected")} ✗
                {t("network_tab.ring")} ✗
                {t("network_tab.small_world")} ✓
                ```
                """)

                if coupling_data:
                    for market, data in coupling_data.items():
                        st.metric(
                            f"{market.upper()} " + t("market.sentiment_label"),
                            f"{data.get("final_sentiment", 0):.3f}",
                            f"{data.get("rounds", 0)} rounds",
                        )

            # ── Tab 7: RL Strategy ──
            with tab7:
                st.subheader(t("rl_tab.title"))

                st.markdown(t("rl_tab.desc_full"))

                if rl_data:
                    from engine.dashboard_viz import rl_strategy_radar
                    st.plotly_chart(rl_strategy_radar(rl_data), use_container_width=True, key="rl_radar_tab")

                for market, data in rl_data.items():
                    strategies = data.get('avg_final_strategies', {})
                    if strategies:
                        st.subheader(t("rl_tab.active_rounds", market=market.upper(), rounds=data["rounds_with_updates"]))
                        # B2C vs SMB comparison text
                        st.caption(t("rl_tab.b2c_vs_smb"))
                        if "b2c" in rl_data and "smb" in rl_data:
                            b2c_strat = rl_data["b2c"].get("avg_final_strategies", {})
                            smb_strat = rl_data["smb"].get("avg_final_strategies", {})
                            if b2c_strat and smb_strat:
                                compare_df = pd.DataFrame({
                                    t("rl_tab.dimension_col"): list(b2c_strat.keys()),
                                    t("rl_tab.b2c_col"): list(b2c_strat.values()),
                                    t("rl_tab.smb_col"): list(smb_strat.values()),
                                })
                                st.dataframe(compare_df.set_index(t("rl_tab.dimension_col")), use_container_width=True)

            # ── Tab 8: Raw Data ──
            with tab8:
                st.subheader(t("raw_tab.title"))
                st.json(result.get("final_report", {}).get("synthesis", {}))

                st.subheader(t("raw_tab.sim_log_title"))
                st.code("\n".join(sim_lines[-50:]), language="text")

                st.download_button(
                    t("raw_tab.download_btn"),
                    json.dumps(result, indent=2, ensure_ascii=False),
                    f"marketfish_v5_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                )

        else:
            st.error(t("pipeline.pipeline_fail", err=result.get("error", "Unknown")))
            st.write(t("pipeline.failed_stage", s=result.get("failed_at_stage", "?")))
            st.write(t("pipeline.completed_stages", s=result.get("stages_completed", [])))

    except Exception as e:
        if run_btn:
            builtins.print = original_print
        st.error(t("pipeline.error", e=str(e)))
        import traceback
        st.code(traceback.format_exc())

else:
        st.info(t("pipeline.load_hint2"))

# ── Footer ──
st.divider()
st.caption("MarketFish v5 · 16 academic papers · 6 LLMs · Built by Keystart AI · https://github.com/key-night-day/market-fish")
