# MarketFish — 市场预测引擎

> 不猜。模拟。
>
> 让数百个 AI 消费者在上线之前，用钱包投票。

---

## 当前版本：v4

MarketFish v4 是一个多智能体市场模拟引擎。输入市场数据，输出产品方向的存活预测。

完整产品愿景 → [VISION.md](VISION.md)

---

## 现在能做什么

### 探索模式：给我找方向

```
输入：种子市场数据（趋势、供需、技术信号）
输出：5-8 个产品方向，按存活概率排名
```

### 实际运行一次的效果（128 agent, 63 分钟）

```
Top:     LocalBrain (一键私有 AI 沙盒)     — score 1.0, 18 买家, ¥7150 营收
#2:      Bill Killer (AI 账单杀手)        — score 0.79, 15 买家
#3:      Smart Bidder (AI 抢单助手)      — score 0.74, 9 买家, ¥0 营收

死了的:   4 个 B2B 方向 — 0 买家
关键发现:  SMB 市场情绪 -0.02，商家比消费者对 AI 悲观得多
```

---

## v4 里有什么

| 能力 | 状态 |
|------|:--:|
| 异质多 LLM 架构（6 个不同模型扮演不同角色） | ✅ |
| 小世界社交网络（128 agents, 618 条边, avg degree 12.0） | ✅ |
| 跨域耦合引擎（情绪传播、FOMO、支付意愿联动） | ✅ |
| 经济对齐 RL（63 个 agent 从模拟结果中学习调整策略） | ✅ |
| 回测过滤（4 因子快速评分） | ✅ |
| Streamlit 仪表盘（运行 + 查看结果） | ✅ |
| 批量 Agent 生成（8 并行 batch, 128 agents） | ✅ |
| **模型注册表**（换 LLM 改 JSON，不碰代码） | ✅ v5 |
| **全部参数外部化**（YAML 配置文件） | ✅ v5 |
| **验证模式**（注入自己的产品 → 预测） | 🔜 v5 |
| **校准**（已知产品验证准确率） | 🔜 v5 |
| **证据报告**（谁会买、为什么、竞品死因） | 🔜 v5 |
| Agent 图谱可视化 | 📋 v6 |
| Agent 对话 | 📋 v6 |
| Docker 一键部署 | 📋 v6 |

---

## 底层怎么工作

```
种子数据 → 市场本体 → 知识图谱 → Agent 生成(128个) → 30轮模拟 → 报告
                                          ↑
                                    每轮: 决策 → 情绪传播 → RL学习
```

**异质多模型：** 消费者用 DeepSeek（快），小商家用 Qwen（务实），分析师用豆包（细节），批评者用智谱（逆向思维）。

**跨域耦合：** 情绪沿社交网络传播。沮丧比兴奋传播快 2 倍。3 个朋友买了 → FOMO → 你也买。

**RL 自适应：** 买后悔 → 下次更谨慎。买满意 → 推荐给朋友。每个 agent 有自己的 5 维策略在进化。

---

## 技术栈

Python 3.12 · FastAPI · Streamlit · OpenAI SDK · 6 家 LLM 提供商

论文基础：MiroFish / TwinMarket / Machine Spirits / EconSimulacra / Agent Bazaar / UChicago Small-World 等 12 篇已落地

---

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env  # 填入 API keys
python main.py         # FastAPI :8000
streamlit run streamlit_app.py  # Dashboard :8501
```

---

## 路线

| 版本 | 交付 | 状态 |
|------|------|:--:|
| v4 | 全管道 + 异质 LLM + 耦合 + RL + Streamlit | ✅ |
| v5 | 配置外置 + 模型注册表 + 三输入 + 证据报告 + 校准 | 🔜 |
| v6 | 图谱 + 对话 + Docker + 公开 Demo | 📋 |
| v7 | 开源 + 英文版 | 📋 |

---

> Built by Keystart AI
