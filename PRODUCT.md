# MarketFish — 市场预测引擎

> 不猜。模拟。
>
> 让 128 个 AI 消费者在上线之前，用钱包投票。

完整产品愿景 → [VISION.md](VISION.md)

---

## 当前版本：v5

v5 全管道跑通。128 agents × 30 rounds × 6 LLMs。中英双语。暗色仪表盘。26/26 测试。

### 真实运行（蜜洲翻译，2026-06-30）

```
Survival: 1.00 🟢     B2C 买家: 27/88 (31%)     SMB 买家: 3/43 (7%)
情绪: +0.25           流失率: 7%                  最适定价: ¥6

"蜜洲翻译价格低且能解决我的跨国沟通痛点，值得立即购买"
  — 高销售（销售经理，月预算 ¥400）

"复制即翻译功能解决了我阅读外文文献困难"
  — 蔡考研（考研学生，月预算 ¥50）
```

45 分钟 · ¥2.68 · 3180 条模拟日志 · 1737 次 LLM 调用

---

## 三种使用方式

| 模式 | 输入 | 输出 | 适合 |
|------|------|------|------|
| 🔍 **探索** | 市场数据 | AI 自动发现产品方向 | 找方向的创业者 |
| ✅ **验证** | 你的产品描述 | 能不能活 + 谁会买 + 定多少钱 | 有想法的产品经理 |
| ⚔️ **混合** | 你的产品 + 市场数据 | 你的 vs AI 竞品，同场 PK | 看竞争格局的团队 |

---

## v5 完整能力

| 能力 | 状态 |
|------|:--:|
| 异质多 LLM 架构（6 provider，12 model 槽位） | ✅ |
| 小世界社交网络（128 agents, β=0.1） | ✅ |
| 跨域耦合（情绪传播/FOMO/支付意愿联动） | ✅ |
| 经济对齐 RL（5维策略向量自适应） | ✅ |
| 回测因子过滤 | ✅ |
| **模型注册表**（换 LLM 改 JSON） | ✅ |
| **全部参数 YAML 外置**（20段300+参数） | ✅ |
| **三输入模式**（探索/验证/混合） | ✅ |
| **证据报告**（买家画像/购买动机/风险/假设） | ✅ |
| **校准框架**（20案例，关键词/随机基线） | ✅ |
| **价格弹性扫描**（多价格点对比寻优） | ✅ |
| **Plotly 交互图表**（S曲线/甜甜圈/雷达图） | ✅ |
| **中英双语**（侧边栏一键切换，300+翻译键） | ✅ |
| **暗色仪表盘**（Streamlit + 强制深色主题） | ✅ |
| **Agent 图谱**（社交网络/二分图） | ✅ |
| **Agent 对话**（用模拟身份聊天） | ✅ |
| **学术摄入**（6篇论文结构化提取） | ✅ |
| **种子数据可上传**（替换默认市场数据） | ✅ |
| 1000+ Agent 规模 | 📋 v6 |
| Agent 记忆模块 | 📋 v6 |
| Docker 部署 | 📋 v6 |
| 开源 + Product Hunt | 📋 v7 |

---

## 学术基础（6篇已摄入）

| 论文 | 出处 | ID | 落地模块 |
|------|------|:--:|------|
| Generative Agents | UIST 2023 | 2304.03442 | Memory (v6) |
| OASIS | 2025 | 2411.11581 | RecSys+TimeEngine (v6) |
| SMIF | ETASR 2026 | 10.48084/etasr.16536 | Calibration v2 (v6) |
| Agent Bazaar | Princeton 2026 | 2605.17698 | alignment_rl v2 (v6) |
| TwinMarket | NeurIPS 2025 | 2502.01506 | BDI认知架构 v2 (v6) |
| EconSimulacra | 2026 | 2606.26883 | coupling v2 (v6) |

---

## 技术栈

Python 3.12 · Streamlit · FastAPI · Plotly · PyYAML · pyvis · OpenAI SDK

6 家国内 LLM（DeepSeek/Qwen/Doubao/Zhipu/Baidu/Hunyuan）+ Anthropic/Google/Mistral/Meta 占位

---

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env
python run.py --mode validate --name "你的产品" --target consumer --pricing "¥10"
streamlit run streamlit_app.py
```

---

> Built by Keystart AI · 一人公司 · AI-Native
