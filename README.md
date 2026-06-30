# MarketFish  &middot; Multi-Agent Market Simulation Engine

> *"Don't guess what product to build. Simulate the market and find out."*
> *「不猜市场。模拟市场。」*

[![Tests](https://img.shields.io/badge/tests-26%2F26%20pass-brightgreen)](tests/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-00d4ff)](https://python.org)
[![i18n](https://img.shields.io/badge/i18n-EN%20%7C%20ZH-00ff88)](locales/)

MarketFish puts your product idea into a **digital marketplace** with 128 AI consumers, competitors, and businesses. They have budgets, beliefs, emotions, and social networks. Over 30 rounds, they vote with their wallets — and you get a complete evidence report showing *who will buy, why, and at what price*.

**Inspired by MiroFish (53K ⭐, $4.2M). Built on 6 ingested academic papers from NeurIPS, UIST, Princeton. 26/26 tests passing.**

---

##  Quick Demo

We tested **蜜洲翻译** (a minimalist translation mini-program: ¥3-6 one-time purchase, copy-to-translate):

```
 Survival Score: 1.00    | 27 B2C buyers (31%)  | 3 SMB buyers (7%)
 Avg WTP: ¥6.2            | Sentiment: +0.25      | Churn: 7%

 "蜜洲翻译价格低且能解决我的跨国沟通和翻译痛点" — 高销售 (Sales Manager, ¥400/mo)
 "复制即翻译功能解决了我阅读外文文献困难" — 蔡考研 (Grad Student, ¥50/mo)
 "价格低且解决我的简历翻译需求" — 姚求职 (Fresh Graduate, ¥100/mo)
```

*128 agents × 30 rounds × 6 LLMs. Cost: ¥2.68 ($0.37). Time: 45 minutes.*

---

##  Architecture

```
User Input (market data or product description)
       │
  ┌────▼────┐   ┌──────────┐   ┌────────────┐
  │ Ontology │ → │ Knowledge │ → │ 128 Agents │  ← Small-World Network (β=0.1)
  └─────────┘   │   Graph   │   │ + Ideas    │  ← Backtest Factor Filter
                └──────────┘   └─────┬──────┘
                                     │
  ┌──────────────────────────────────▼──────────────────────────────┐
  │                    30-Round Market Simulation                    │
  │  BDI Cognition · Cross-Domain Coupling · Economic Alignment RL  │
  │  6 Heterogeneous LLMs · Plotly Interactive Charts               │
  └──────────────────────────────────┬──────────────────────────────┘
                                     │
  ┌──────────────────────────────────▼──────────────────────────────┐
  │  Evidence Report · Agent Graph · Price Elasticity · Calibration │
  │  Streamlit Dashboard · EN/ZH i18n · Docker Ready                │
  └─────────────────────────────────────────────────────────────────┘
```

---

##  Key Features (v5)

| Feature | Description |
|---------|-------------|
| **6 Heterogeneous LLMs** | DeepSeek, Qwen, Doubao, Zhipu, Baidu, Hunyuan — each agent type gets the optimal model |
| **Small-World Network** | β=0.1 Watts-Strogatz — optimal balance of diversity + diffusion speed |
| **BDI Cognition** | Belief-Desire-Intention architecture per agent (TwinMarket, NeurIPS 2025) |
| **Cross-Domain Coupling** | Emotions propagate through social network. Negativity bias 2x. FOMO at 3+ peer purchases |
| **Economic Alignment RL** | 5-axis strategy vectors. EMA adaptation. REINFORCE++ training |
| **3 Input Modes** | Explore (LLM generates directions) / Validate (test your product) / Hybrid (both) |
| **Evidence Report** | Who will buy, buyer profiles, real agent quotes, risk signals, testable hypotheses |
| **Price Elasticity Scanner** | Multi-price-point simulation → optimal pricing curve |
| **Plotly Interactive Charts** | S-curve adoption, donut segments, radar RL, sentiment timeline |
| **Full i18n** | English & Chinese. 300+ translation keys. JSON-based (MiroFish architecture) |
| **Model Registry** | Swap LLMs by editing one JSON file. 12 providers supported |
| **YAML Config** | All parameters externalized. User overridable. 20 config sections |

---

##  Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env          # Add your API keys
python run.py --mode validate --name "Your Product" --target consumer --pricing "$10"
streamlit run streamlit_app.py # Dashboard at http://localhost:8501
```

Or with Docker:
```bash
docker-compose up  # FastAPI :8000 + Streamlit :8501
```

---

##  Academic Foundation

| Paper | Venue | ID | Core Contribution | v6 Module |
|-------|-------|:--:|-------------------|:--:|
| **Generative Agents** | UIST 2023 | `2304.03442` | Memory stream + reflection + planning | Memory |
| **OASIS** | 2025 | `2411.11581` | 1M agents + RecSys + temporal activation | RecSys |
| **SMIF** | ETASR 2026 | `10.48084/etasr.16536` | r=0.893 calibration + grounding (150 cases) | Calibration |
| **Agent Bazaar** | Princeton 2026 | `2605.17698` | Economic Alignment RL + EAS 4-dim score | RL v2 |
| **TwinMarket** | **NeurIPS 2025** | `2502.01506` | BDI 6-step loop + dynamic social network | Cognition |
| **EconSimulacra** | 2026 | `2606.26883` | Cross-domain coupling + shared stress state | Coupling |

>  ⚠️ MENTOR (FITEE 2025) was removed from our reference list — it addresses financial narrative prediction, not report generation. Our report module's teacher-student design is original.

---

##  Project Structure

```
market-fish/
├── streamlit_app.py       # Dashboard (i18n complete, dark theme)
├── run.py                 # CLI runner
├── main.py                # FastAPI server
├── config/
│   ├── defaults.yaml      # All parameters (20 sections, 300+ keys)
│   └── models_registry.json
├── engine/                # 19 modules
│   ├── pipeline.py        # 5-stage orchestrator
│   ├── simulator.py       # 30-round market simulation
│   ├── coupling.py        # Cross-domain coupling
│   ├── alignment_rl.py    # Economic alignment RL
│   ├── evidence_report.py # Evidence chain generator
│   ├── dashboard_viz.py   # Plotly interactive charts
│   ├── price_scanner.py   # Price elasticity scanner
│   └── i18n.py            # JSON-based i18n (MiroFish architecture)
├── locales/
│   ├── en.json / zh.json  # 300+ translation keys
├── data/
│   ├── seed_*.json        # 5 market data sources (with bias declarations)
│   └── ingested_papers/   # 6 structured paper extractions
└── tests/                 # 26 smoke tests (no LLM needed)
```

---

##  Why "MarketFish"?

Market(市场) + Fish(鱼). Like a fish navigating the market ocean, our agents swim through waves of competition, emotion contagion, and social influence. The name echoes **MiroFish** (social opinion simulation, 53K ⭐) — different domain, same philosophy: simulate, don't guess.

---

##  Roadmap

| Version | Status | Deliverables |
|---------|:--:|--------------|
| **v5** | ✅ Done | Model registry, YAML config, 3 input modes, evidence report, calibration, Plotly charts, i18n, dark theme |
| **v6** | 📋 Planned | Memory module, RecSys filtering, BDI v2, stress coupling, 10K+ agents (OASIS architecture) |
| **v7** | 📋 Planned | Open source launch, English release, Product Hunt |

---

> *MarketFish doesn't guess the market. It simulates it.*
> *Let 128 AI consumers tell you — before you launch — whether they will buy.*
>
> **Built by Keystart AI · One-person company · AI-Native**

---

# MarketFish  · 多智能体市场模拟引擎

> *「不猜市场。模拟市场。」*

把你的产品扔进一个由 **128 个 AI 消费者、商家、竞品** 组成的数字市场。他们有预算、有信念、有情绪、有社交网络。30 轮模拟后，他们会用钱包投票——你得到一份完整的证据报告：**谁会买、为什么买、多少钱买**。

---

##  五分钟看懂

| 问题 | 传统做法 | MarketFish |
|------|---------|------------|
| 我的产品能活吗？ | 问一个 AI → 一段文字 | **128 个异质 AI 模拟 30 轮市场** |
| 谁会买？ | 猜 | **32 个买家画像：价格敏感 12.5% / 冲动 37.5% / 理性 50%** |
| 定多少钱？ | 拍脑袋 | **价格弹性扫描：1-30 元，最优 ¥6** |
| 准不准？ | 无法验证 | **20 个已知产品校准 + SMIF r=0.893 对标** |

---

##  快速开始

```bash
pip install -r requirements.txt
python run.py --mode validate --name "你的产品" --target consumer --pricing "¥10"
streamlit run streamlit_app.py  # http://localhost:8501
```

三种模式：**探索**（AI 帮你找方向） / **验证**（测你的产品） / **混合**（你的产品 vs AI 竞品）。

---

> *MarketFish 不猜市场。它模拟市场。*
> *在上线之前，让 128 个 AI 消费者告诉你：买不买，为什么。*
>
> **Keystart AI 出品 · 一人公司 · AI-Native**
