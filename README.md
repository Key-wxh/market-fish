# MarketFish — Multi-Agent Market Simulation Engine

> "Don't guess what product to build. Simulate the market and find out."

MarketFish is a 5-stage pipeline that uses **hundreds of AI agents** to simulate market dynamics and predict which product directions will survive.

**Inspired by MiroFish (53K GitHub stars, $4.2M funding). Built on 16 academic papers from NeurIPS, ICLR, IJCAI, EACL.**

## How It Works

```
Seed Market Signals → Ontology → Knowledge Graph → Agent Generation → 30-Round Simulation → Report
```

1. **Ontology**: LLM extracts market participant types and decision factors from raw data
2. **Knowledge Graph**: Builds a temporal market map — who pays whom, where are the gaps
3. **Agents + Ideas**: Generates 100+ agents (consumers, SMBs, enterprises, competitors) AND novel product directions from pain-point spaces
4. **Simulation**: 30 rounds. BDI cognitive architecture. 3 markets at 3 speeds (B2C/SMB/Enterprise)
5. **Report**: Teacher-Student iteration + Wisdom-of-Crowds aggregation

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
| Agent Bazaar | arXiv 2026 | Economic alignment ≠ general capability |
| EconSimulacra | arXiv 2026 | Cross-domain coupling creates emergence |

## Why This Matters

In 2026, there are 16M+ one-person companies in China. 70% can't use AI effectively. Everyone is guessing what product to build.

MarketFish doesn't guess. It simulates.

Built by one person + AI. For one-person companies.
