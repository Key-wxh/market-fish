"""
MarketFish — Streamlit Dashboard
Trigger full pipeline runs and view results.
"""

import json
import streamlit as st
from engine.pipeline import Pipeline

st.set_page_config(page_title="MarketFish", page_icon="", layout="wide")
st.title("MarketFish — 市场预测引擎")

st.markdown("输入市场信号 → 30轮Agent模拟 → 预测产品方向存活概率")

# Sidebar: Seed data preview
with st.sidebar:
    st.header("种子数据")
    seed_files = {
        "freelancer": "data/seed_freelancer.json",
        "economy": "data/seed_economy.json",
        "tech": "data/seed_tech.json",
    }
    for key, path in seed_files.items():
        with st.expander(f"{key}.json"):
            try:
                with open(path) as f:
                    st.json(json.load(f))
            except FileNotFoundError:
                st.warning("文件不存在")

# Main: Run pipeline
if st.button("运行市场预测", type="primary", use_container_width=True):
    seed = {}
    for key, path in seed_files.items():
        try:
            with open(path) as f:
                seed[key] = json.load(f)
        except FileNotFoundError:
            st.error(f"种子数据缺失: {path}")
            st.stop()

    with st.spinner("五阶段流水线运行中..."):
        pipeline = Pipeline()
        result = pipeline.run(seed)

    if result.get("pipeline_status") == "complete":
        st.success(f"完成！耗时 {result['elapsed_seconds']} 秒")

        # Show product directions
        st.header("预测产品方向")
        directions = result.get("product_directions", [])
        for d in directions:
            with st.expander(f"{d.get('name', 'Unnamed')} — 存活分数: {d.get('survival_score', 'N/A')}"):
                st.write(f"**目标市场**: {d.get('target_market', 'N/A')}")
                st.write(f"**类别**: {d.get('category', 'N/A')}")
                st.write(f"**定价**: {d.get('estimated_pricing_cny', 'N/A')}")
                st.write(f"**为什么有机会**: {d.get('why_graph_shows_opportunity', 'N/A')}")
                st.write(f"**风险**: {d.get('key_risks', [])}")

        # Show simulation results
        final = result.get("final_report", {})
        sim_results = final.get("simulation_results", [])
        if sim_results:
            st.header("模拟结果")
            chart_data = [
                {"产品": r.get("product_name", "?")[:20], "存活分数": r.get("survival_score", 0), "付费用户": r.get("purchasers", 0)}
                for r in sim_results
            ]
            st.bar_chart(chart_data, x="产品", y="存活分数")

        # Show synthesis
        synthesis = final.get("synthesis", {})
        if synthesis:
            st.header("综合判断")
            st.info(synthesis.get("executive_summary", ""))
            st.metric("置信度", f"{synthesis.get('confidence_level', 0):.0%}")

            top = synthesis.get("top_product_direction", {})
            if top:
                st.success(f"**首选方向**: {top.get('name')} (分数: {top.get('survival_score')})")
                st.write(top.get("why", ""))

            action = synthesis.get("actionable_recommendation", "")
            if action:
                st.header("行动建议")
                st.write(action)

    else:
        st.error(f"流水线失败: {result.get('error', 'Unknown')}")
        st.write(f"失败阶段: {result.get('failed_at_stage', 'Unknown')}")
