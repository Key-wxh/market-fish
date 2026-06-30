# MarketFish — Multi-Agent Market Simulation Engine

> "Don't guess what product to build. Simulate the market and find out."

MarketFish is a 5-stage pipeline that uses **hundreds of AI agents** to simulate market dynamics and predict which product directions will survive.

**Inspired by MiroFish (53K GitHub stars, $4.2M funding). Built on 16 academic papers from NeurIPS, ICLR, IJCAI, EACL.**

## How It Works

```
Seed Market Signals → Ontology → Knowledge Graph → Agent Generation → 30-Round Simulation → Report
                                                           ↑                    ↑
                                                    [Backtest Filter]    [Coupling + RL]
```

1. **Ontology**: LLM extracts market participant types and decision factors from raw data
2. **Knowledge Graph**: Builds a temporal market map — who pays whom, where are the gaps
3. **Agents + Ideas**: Generates 100+ agents (consumers, SMBs, enterprises, competitors) AND novel product directions from pain-point spaces. Filtered through **backtest-validated 4-factor scoring**.
4. **Simulation**: 30 rounds. BDI cognitive architecture. **Cross-domain coupling** (消费↔社交↔情绪) after each round. **Economic alignment RL** adapts agent strategies from market outcomes.
5. **Report**: Teacher-Student iteration + Wisdom-of-Crowds aggregation

### v4 Pipeline Features (June 2026)

| Component | Paper | Status |
|-----------|-------|--------|
| 6-LLM Heterogeneous Agents | Machine Spirits 2026 | ✅ v3 |
| Small-World Network Topology | UChicago 2025 | ✅ v3 |
| Backtest Factor Filter (4-factor) | 5-case validation | ✅ v3 |
| **Cross-Domain Coupling** | EconSimulacra 2026 | ✅ v4 |
| **Economic Alignment RL** | Agent Bazaar 2026 | ✅ v4 |

**Cross-Domain Coupling**: Emotions propagate through social network (negativity bias 2x). FOMO triggers at 3+ peer purchases. Market sentiment affects all agents (macro→micro). Willingness-to-pay adjusted by emotional state.

**Economic Alignment RL**: 5-axis strategy vector per agent (price_sensitivity, early_adopter, social_susceptibility, loyalty, risk_tolerance). EMA-based adaptation from market outcomes. Personality-bounded — impulse buyers stay impulsive but learn which categories to avoid.

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env  # add your DEEPSEEK_API_KEY
python main.py         # FastAPI on :8000
streamlit run streamlit_app.py  # Dashboard
```

## Academic Foundation

| Paper | Venue | Key Insight Used |
|-------|-------|-----------------|
| MiroFish | GitHub 53K⭐ | 5-stage pipeline + 8-layer JSON enforcement |
| SMIF | ETASR 2026 | 0.893 correlation vs real markets (150 cases) |
| TwinMarket | NeurIPS 2025 | BDI cognitive architecture |
| Machine Spirits | arXiv 2026 | Heterogeneous agents > homogeneous |
| UChicago Innovation | 2025 | Small-world network optimal for diffusion |
| MENTOR | FITEE 2025 | Teacher-Student iterative reasoning |
| Social Agents | ICLR 2025 | Wisdom-of-crowds 67% better than single LLM |
| Agent Bazaar | arXiv 2026 | Economic alignment ≠ general capability ✅ implemented |
| EconSimulacra | arXiv 2026 | Cross-domain coupling creates emergence ✅ implemented |

## Why This Matters

In 2026, there are 16M+ one-person companies in China. 70% can't use AI effectively. Everyone is guessing what product to build.

MarketFish doesn't guess. It simulates.

Built by one person + AI. For one-person companies.
