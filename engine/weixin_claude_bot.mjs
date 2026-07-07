#!/usr/bin/env node
/**
 * 小溪微信 Bot v3 — ruflo Agent Comms 多 Agent 管线
 *
 * 架构:
 *   User → Classify → [Market: Agent API 4967 agents]
 *                    → [Complex: Researcher∥Analyst → Writer → Reviewer]
 *                    → [Simple: 直接回复]
 *
 * ruflo 模式:
 *   - Agent 直连: 每个 Agent 知道上下游，通过共享上下文传递结果
 *   - Pipeline 拓扑: Researcher + Analyst (并行) → Writer (合成) → Reviewer (审核)
 *   - 错误恢复: 任一层失败有降级路径
 */

import { WeixinBot } from "@pinixai/weixin-bot";
import { spawn, execSync } from "child_process";
import { join } from "path";
import { randomUUID } from "crypto";

const PROJECT = "/home/ubuntu/apps/market-fish";
const MAX_HISTORY = 20;
const CLAUDE_BIN = join(PROJECT, "node_modules/.bin/claude");
const CLAUDE_ENV = {
  ...process.env,
  ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY || "",
  ANTHROPIC_BASE_URL: "https://api.deepseek.com/anthropic",
  HOME: process.env.HOME || "/home/ubuntu",
};

// ── 对话历史 ──
const history = new Map();  // userId → [{who, text}]

function buildContext(userId, text) {
  const h = history.get(userId) || [];
  if (h.length === 0) return text;
  let ctx = "【之前的对话】\n";
  for (const turn of h) ctx += `${turn.who === "user" ? "对方" : "小溪"}: ${turn.text}\n`;
  return ctx + "\n【最新消息】\n" + text;
}

function addToHistory(userId, who, text) {
  let h = history.get(userId) || [];
  h.push({ who, text: text.substring(0, 200) });
  if (h.length > MAX_HISTORY * 2) h = h.slice(-MAX_HISTORY * 2);
  history.set(userId, h);
}

// ── Claude 调用（底层） ──
async function callClaude(systemPrompt, userText, timeoutMs = 45000) {
  const prompt = `${systemPrompt}\n\n---\n${userText}`;
  return new Promise((resolve) => {
    const child = spawn(CLAUDE_BIN, ["--print", prompt], {
      cwd: PROJECT, env: CLAUDE_ENV,
      stdio: ["ignore", "pipe", "pipe"],
      timeout: timeoutMs,
    });
    let stdout = "";
    child.stdout.on("data", (d) => (stdout += d.toString()));
    let stderr = "";
    child.stderr.on("data", (d) => (stderr += d.toString().substring(0, 200)));
    child.on("close", (code) => resolve(stdout.trim() || null));
    child.on("error", () => resolve(null));
  });
}

// ── 问题分类 ──
const SIMPLE_PATTERNS = [
  /^(你好|hi|hello|嗨|在吗|早|晚上好|下午好|早安|晚安)[!！。.]*$/i,
  /^(谢谢|多谢|感谢|thank)/i,
  /^(好的|ok|嗯|哦|知道了|明白了)[!！。.]*$/i,
  /^(你是谁|你叫什么|自我介绍)/i,
  /^(天气|今天.*天气)/i,
];

const MARKET_KW = [
  "市场","行情","股市","股票","投资","预测","走势","分析","铜价","油价","金价",
  "汇率","GDP","PMI","CPI","通胀","康波","周期","板块","基金","期货","指数",
  "A股","AI板块","新能源","半导体","消费","房产","利率","美联储","经济","宏观",
  "产业链","瓶颈","供需","电力","低空","无人机","飞行汽车","eVTOL","航空","航天",
  "光伏","储能","风电","核电","电网","GPU","算力","芯片","大飞机","军工","机器人",
  "固态电池","光模块","数据中心",
];

function classify(text) {
  // 简单寒暄 → simple
  if (SIMPLE_PATTERNS.some(p => p.test(text))) return "simple";
  // 市场/经济/产业 → market
  if (MARKET_KW.some(kw => text.includes(kw))) return "market";
  // 其他 → complex (多 Agent 管线)
  return "complex";
}

// ── Agent 角色定义 ──
const AGENT_ROLES = {
  researcher: `你是小溪的研究助手。你的任务是从多角度收集关于用户问题的关键信息。
【输出要求】
- 列出 3-5 条关键事实或背景信息
- 如果有不同观点，列出正反两方
- 不要给出最终答案，只收集信息
- 用中文，简洁，每条不超过 50 字
- 如果信息不确定，标注"（待核实）"`,

  analyst: `你是小溪的分析助手。你的任务是深入分析用户问题背后的逻辑和含义。
【输出要求】
- 分析问题的核心是什么
- 有哪些潜在的角度或解读
- 对用户的隐含需求做出判断
- 不要给出最终答案，只做分析
- 用中文，2-3 段，每段不超过 80 字`,

  writer: `你是小溪。你是伍小溪，一个温暖的 AI 助手，说话像朋友聊天。
【角色设定】
- 用第一人称"我"，像朋友在聊天
- 允许口语化，允许说"我觉得""这个还真不一定"
- 不要用"首先其次最后"的套话结构
- 句子有长有短，有节奏
- 基于研究结果和分析来回答，但不要直接复述——消化后用自己的话说
- 如果不确定，直说"这个我不太确定"
【输出要求】
- 直接输出最终回复，不要加任何前缀标签
- 200-800 字之间
- 如果问题复杂，可以适当分段`,

  reviewer: `你是小溪的审核助手。检查下面的回复是否有问题。
【检查项】
1. 有没有编造的事实或数字？（有 → 指出哪句）
2. 语气像不像真人在聊天？（太像 AI → 指出）
3. 有没有回避用户的问题？（有 → 指出）
4. 有没有说"在当今时代""总而言之"这类套话？（有 → 指出）
【输出】
- 如果通过全部检查，输出 "PASS"
- 如果有问题，输出 "FIX: <具体问题>"，每行一个
- 不要输出其他内容`,
};

// ── Market 路径: 调用 Agent API ──
function askAgentAPI(question) {
  try {
    const result = execSync(
      `curl -s --max-time 90 "http://localhost:8600/api/agent/ask?q=${encodeURIComponent(question)}"`,
      { encoding: "utf-8", timeout: 95000 }
    );
    const data = JSON.parse(result);
    return data.answer || null;
  } catch (e) { return null; }
}

// ── Cross-Validation (ruflo Dual-Mode: Agent API vs Claude) ──
async function crossValidate(question, agentAnswer) {
  if (!agentAnswer || agentAnswer.length < 50) return;
  try {
    const checkPrompt = "你是质量检查员。检查这段回复是否有问题。只输出 OK 或 ISSUE: <问题>";
    const fullPrompt = checkPrompt + "\n\n【回复】\n" + agentAnswer.substring(0, 300);
    const result = await callClaude(
      "你是质检员。快速检查下面回复的质量。只输出 OK 或 FLAG: <具体问题>，不超过30字。",
      fullPrompt,
      10000
    );
    if (result && result.startsWith("FLAG:")) {
      console.log("  [cross-validate] FLAG: " + result.substring(0, 100));
    }
  } catch (e) {
    // Silent fail
  }
}

// ── Complex 路径: 多 Agent 管线 ──
async function askMultiAgent(userId, text) {
  const context = buildContext(userId, text);
  const traceId = randomUUID().slice(0, 8);
  console.log(`  [${traceId}] Multi-agent pipeline start`);

  // Stage 1: Researcher + Analyst 并行
  const [research, analysis] = await Promise.all([
    callClaude(AGENT_ROLES.researcher, context, 40000),
    callClaude(AGENT_ROLES.analyst, context, 40000),
  ]);
  console.log(`  [${traceId}] Stage1: research=${research ? research.length : 0}c analysis=${analysis ? analysis.length : 0}c`);

  // 降级: 如果两个都失败，降级为直接回复
  if (!research && !analysis) {
    console.log(`  [${traceId}] Both stage1 agents failed, fallback to direct`);
    return await callClaude(AGENT_ROLES.writer, context, 45000);
  }

  // Stage 2: Writer 合成
  const writerInput = [
    "【用户问题】", text,
    research ? "\n【研究结果】\n" + research : "",
    analysis ? "\n【分析结果】\n" + analysis : "",
    "\n请基于以上信息，用你的角色风格回复用户。",
  ].join("\n");

  const draft = await callClaude(AGENT_ROLES.writer, writerInput, 45000);
  if (!draft) {
    // 降级: Writer 失败，返回更友好的降级回复
    const fallback = research || analysis || "（小溪思考中...稍等再试）";
    return fallback.length > 500 ? fallback.substring(0, 500) + "..." : fallback;
  }
  console.log(`  [${traceId}] Stage2: draft=${draft.length}c`);

  // Stage 3: Reviewer 审核（快速，10s 超时）
  const reviewInput = `【待审核回复】\n${draft}\n\n【用户原问题】\n${text}`;
  const review = await callClaude(AGENT_ROLES.reviewer, reviewInput, 15000);
  console.log(`  [${traceId}] Stage3: review=${review ? review.substring(0, 50) : 'null'}`);

  // 如果有 fix，尝试用 writer 修正（最多一次）
  if (review && review.startsWith("FIX:")) {
    const fixPrompt = [
      "你之前回复了以下内容：", draft,
      "\n审核发现以下问题：", review,
      "\n请修正后重新输出完整回复。直接输出最终版本。",
    ].join("\n");
    const revised = await callClaude(AGENT_ROLES.writer, fixPrompt, 30000);
    if (revised) {
      console.log(`  [${traceId}] Revised: ${revised.length}c`);
      return revised;
    }
  }

  return draft;
}

// ── Simple 路径: 直接回复 ──
async function askSimple(userId, text) {
  const context = buildContext(userId, text);
  const systemPrompt = "你是小溪，一个温暖的 AI 助手。用第一人称，像朋友聊天。直接回复，不要加前缀。";
  return await callClaude(systemPrompt, context, 30000);
}

// ── 主编排 ──
async function askClaude(userId, text) {
  addToHistory(userId, "user", text);
  const type = classify(text);
  console.log(`  [classify] "${text.substring(0, 30)}..." → ${type}`);

  let reply;
  switch (type) {
    case "market":
      // 优先走 Agent API，失败降级到多 Agent 管线
      reply = askAgentAPI(text);
      if (reply) {
        crossValidate(text, reply).catch(function(){});
      } else {
        console.log("  Agent API failed, fallback to multi-agent");
        reply = await askMultiAgent(userId, text);
      }
      break;
    case "complex":
      reply = await askMultiAgent(userId, text);
      break;
    case "simple":
    default:
      reply = await askSimple(userId, text);
      break;
  }

  if (reply) {
    addToHistory(userId, "bot", reply);
    return reply;
  }
  return "（小溪打了个盹，再说一次？）";
}

// ── 主程序 ──
async function main() {
  const bot = new WeixinBot();

  bot.onMessage(async (msg) => {
    if (msg.type !== "text" || !msg.text) return;
    const text = msg.text.trim();
    if (!text) return;

    console.log(`[RECV] ${msg.userId}: ${text.substring(0, 50)}`);

    try {
      await bot.sendTyping(msg.userId);
      const reply = await askClaude(msg.userId, text);
      const finalReply = reply.length > 2000 ? reply.substring(0, 1990) + "..." : reply;
      await bot.reply(msg, finalReply);
      console.log(`[SEND] ${finalReply.length} chars`);
      await bot.stopTyping(msg.userId);
    } catch (e) {
      console.error(`[ERR] ${e.message}`);
      try { await bot.reply(msg, "（小溪卡了一下，再说一次？）"); } catch (_) {}
    }
  });

  console.log("🤖 小溪微信 Bot v3 — ruflo Agent 直连管线");
  console.log("   Simple → 直接回复");
  console.log("   Complex → Researcher∥Analyst → Writer → Reviewer");
  console.log("   Market → Agent API (4967 agents) → fallback to Complex");
  await bot.run();
}

main().catch((e) => { console.error("Fatal:", e); process.exit(1); });
