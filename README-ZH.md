<p align="center">
  <img src="https://img.shields.io/badge/版本-v6.0-blue" alt="v6.0">
  <img src="https://img.shields.io/badge/许可-MIT-green" alt="MIT">
  <img src="https://img.shields.io/badge/Python-3.12+-blue" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/测试-26%2F26-brightgreen" alt="26/26 tests">
  <img src="https://img.shields.io/badge/LLM-11%20家-purple" alt="11 providers">
</p>

<h1 align="center">🐟 MarketFish · 市场预测引擎</h1>
<p align="center"><strong>不猜市场。模拟市场。</strong></p>
<p align="center">在上线之前，让数百个 AI 消费者用钱包投票。</p>

---

MarketFish 是一个**多智能体市场模拟引擎**。不是问一个大模型"这个产品能行吗"，而是建造一个由 128+ 个 AI 消费者组成的数字市场——每个人都有独立的身份、预算、情绪和偏见——让他们在 30 轮中自由买卖。他们的购买决策、流失模式、社交影响，揭示真实用户会怎么做。

基于 6 篇学术论文，支持 11 家国内外大模型。

[English README](README.md)

## 快速开始

```bash
git clone https://github.com/Key-wxh/market-fish.git
cd market-fish
cp .env.example .env
# 编辑 .env — 至少填一个 LLM API key（DeepSeek 最便宜）
pip install -r requirements.txt
streamlit run streamlit_app.py
```

浏览器打开 `http://localhost:8501` → 选模式 → 点运行。

## 原理

```
种子数据（静态 JSON）
    │
    ▼
五阶段管道：
  1. 本体生成 — 从种子数据提取市场结构
  2. 知识图谱 — 实体、关系、痛点空间
  3. Agent 工厂 — 128 个异构 AI 消费者（6 家大模型并行生成）
  4. 市场模拟 — 30 轮决策 + 情绪传播 + RL 自适应 + 记忆
  5. 证据报告 — 谁会买、为什么买、竞品死因、可验证假设
```

### V6 六大模块（全部实现）

| 模块 | 论文 | 做什么 |
|------|------|------|
| **Memory 记忆** | Generative Agents (UIST 2023) | Agent 记住购买、后悔、反思，跨任务累积 |
| **TimeEngine 时间** | OASIS (2025) | 按 24h 概率激活，不是每轮所有人都醒着 |
| **RecSys 推荐** | OASIS (2025) | 个性化推荐替代随机展示 |
| **BDI v2 认知** | TwinMarket (NeurIPS 2025) | 六步认知循环 + 过度自信/损失厌恶/羊群效应 |
| **Stress 压力** | EconSimulacra (2026) | 财务压力、社交比较 → 压力调节支付意愿 |
| **Grounding 校验** | SMIF (ETASR 2026) | RAG 检索 + 规则约束，防止 Agent 胡编 |

### 三种模式

| 模式 | 输入 | 输出 |
|------|------|------|
| 🔍 **探索** | 种子数据 | AI 自动发现产品方向，按存活概率排名 |
| ✅ **验证** | 你的产品想法 | 能不能活、谁会买、定多少钱最优 |
| ⚔️ **混合** | 你的产品 + 数据 | 你的 vs AI 竞品，同一沙盘 PK |

### 支持的大模型

11 家。填一个就能跑，越多 Agent 越多样化。

| 🇨🇳 国内 | DeepSeek、通义千问、豆包、智谱、百度、混元 |
| 🌍 国外 | OpenAI、Anthropic、Google、Mistral、Meta |

## CLI

```bash
python run.py --mode explore                           # 探索产品方向
python run.py --mode validate --name "我的产品" --pricing "¥10"  # 验证想法
python run.py --mode explore --reuse-agents            # 复用 Agent（省钱）
```

## 项目结构

```
market-fish/
├── engine/         # 核心引擎（20+ 模块）
│   ├── simulator.py, agent_factory.py    # 模拟核心
│   ├── agent_store.py, memory.py         # V6: 持久化 + 记忆
│   ├── temporal.py, recsys.py            # V6: 时间引擎 + 推荐
│   ├── bdi_v2.py, stress.py, grounding.py # V6: 认知 + 压力 + 校验
├── config/         # 模型注册表 + 全部参数
├── locales/        # 中英双语（300+ 翻译键）
├── tests/          # 26/26 测试
├── streamlit_app.py  # Web 仪表盘
├── run.py          # 命令行入口
└── .env.example    # API Key 模板
```

## 与 MiroFish 的区别

[MiroFish](https://github.com/666ghj/MiroFish)（5500+ ⭐）是目前最知名的多智能体模拟引擎。两者都用 AI Agent 模拟社会/市场行为，但侧重不同：

| | MiroFish | MarketFish |
|------|------|------|
| 定位 | 通用社会模拟 | 产品市场预测 |
| 架构 | Flask + Node.js + Docker | Streamlit 单文件 |
| 记忆 | Zep Cloud（外部服务） | 内置（本地 JSON，零外部依赖） |
| 大模型 | 仅 OpenAI 兼容 | 11 家（国内 + 国外） |
| 数据 | 用户上传文档 | 8 源实时抓取管线 |
| 语言 | 中/英 | 中/英 |
| 许可 | AGPL-3.0 | MIT |

## 许可证

MIT — 个人和商用均免费。

---

Keystart AI · 一人公司 · AI-Native
