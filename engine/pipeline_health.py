#!/usr/bin/env python3
"""
Pipeline Health Dashboard — ruflo MetaHarness 模式

一句话输出全部管线状态。每个管线阶段独立检查，汇总为健康评分 (0-100)。

用法: python3 pipeline_health.py [--json] [--alert]
cron: 适合放在 23:00 evening_brief 之前运行
"""
import sys, json, os
from pathlib import Path
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
ROOT = Path(__file__).parent.parent
GOLD = ROOT / "data_lake" / "gold"
BRONZE = ROOT / "data_lake" / "bronze"
HEALTH_FILE = GOLD / "pipeline_health.json"


def check_stage(name: str, check_fn) -> dict:
    """Run a health check. Returns {name, status, score, detail}."""
    try:
        result = check_fn()
        return {"name": name, **result}
    except Exception as e:
        return {"name": name, "status": "error", "score": 0, "detail": str(e)[:100]}


def check_market_intel() -> dict:
    """Check if today's market intel exists and is valid."""
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    md_file = GOLD / "market_intel.md"
    html_file = GOLD / "market_intel.html"

    if not md_file.exists():
        return {"status": "missing", "score": 0, "detail": "情报文件不存在"}

    mtime = datetime.fromtimestamp(md_file.stat().st_mtime, tz=TZ)
    hours_ago = (datetime.now(TZ) - mtime).total_seconds() / 3600

    if hours_ago > 24:
        return {"status": "stale", "score": 30, "detail": f"情报过期 ({hours_ago:.0f}h前)"}

    content = md_file.read_text(encoding="utf-8")
    size = len(content)

    if size < 500:
        return {"status": "incomplete", "score": 40, "detail": f"内容过短 ({size}字)"}

    html_ok = html_file.exists()
    return {
        "status": "healthy",
        "score": 100 if html_ok else 85,
        "detail": f"{size}字 {'+HTML' if html_ok else '(HTML缺失)'}",
    }


def check_agent_pipeline() -> dict:
    """Check if today's agent pipeline completed."""
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    log_file = ROOT / "data_lake" / "agent_learn.log"

    if not log_file.exists():
        return {"status": "missing", "score": 0, "detail": "Agent日志不存在"}

    log_text = log_file.read_text(encoding="utf-8")

    # Check for today's completion markers
    has_debate = "Agent Debate" in log_text and today in log_text
    has_trend = "Agent Trend" in log_text and today in log_text
    has_complete = "Pipeline complete" in log_text

    if has_complete:
        return {"status": "healthy", "score": 100, "detail": "全部完成 (学习+共识+辩论+趋势)"}
    elif has_debate and has_trend:
        return {"status": "healthy", "score": 90, "detail": "辩论+趋势完成"}
    elif has_debate:
        return {"status": "partial", "score": 60, "detail": "仅辩论完成"}
    else:
        return {"status": "pending", "score": 20, "detail": "未开始或不完整"}


def check_data_ingestion() -> dict:
    """Check if today's data ingestion ran."""
    today = datetime.now(TZ)
    today_dir = BRONZE / today.strftime("%Y/%m/%d")

    if not today_dir.exists():
        return {"status": "missing", "score": 20, "detail": "今日数据目录不存在"}

    files = list(today_dir.glob("*.json"))
    n_files = len(files)
    total_size = sum(f.stat().st_size for f in files)

    if n_files >= 10:
        return {"status": "healthy", "score": 100, "detail": f"{n_files}文件 {total_size//1024}KB"}
    elif n_files >= 5:
        return {"status": "partial", "score": 70, "detail": f"{n_files}文件 {total_size//1024}KB"}
    elif n_files > 0:
        return {"status": "incomplete", "score": 40, "detail": f"仅{n_files}文件"}
    else:
        return {"status": "empty", "score": 10, "detail": "目录为空"}


def check_services() -> dict:
    """Check if critical services are running."""
    import subprocess
    try:
        result = subprocess.run(
            ["pm2", "jlist"], capture_output=True, text=True, timeout=5
        )
        processes = json.loads(result.stdout)
        critical = ["xiaoxi-server", "marketfish-streamlit", "weixin-bot"]
        statuses = {}
        for p in processes:
            name = p.get("name", "")
            if name in critical:
                statuses[name] = p.get("pm2_env", {}).get("status") == "online"

        all_ok = all(statuses.get(c, False) for c in critical)
        missing = [c for c in critical if not statuses.get(c)]
        if all_ok:
            return {"status": "healthy", "score": 100, "detail": f"{len(critical)}服务全在线"}
        else:
            return {"status": "degraded", "score": 40, "detail": f"离线: {', '.join(missing)}"}
    except Exception as e:
        return {"status": "error", "score": 0, "detail": f"PM2查询失败: {e}"}


def check_costs() -> dict:
    """Check if cost tracking is up to date."""
    cost_files = sorted(GOLD.glob("cost_*.json"))
    if not cost_files:
        return {"status": "missing", "score": 0, "detail": "无成本记录"}

    latest = cost_files[-1]
    mtime = datetime.fromtimestamp(latest.stat().st_mtime, tz=TZ)
    hours_ago = (datetime.now(TZ) - mtime).total_seconds() / 3600

    if hours_ago < 6:
        return {"status": "healthy", "score": 100, "detail": f"成本已更新 ({hours_ago:.0f}h前)"}
    elif hours_ago < 24:
        return {"status": "stale", "score": 70, "detail": f"成本{hours_ago:.0f}h未更新"}
    else:
        return {"status": "stale", "score": 30, "detail": f"成本超24h未更新"}


def main(output_json: bool = False, send_alert: bool = False):
    """Run all health checks and output summary."""
    stages = [
        check_stage("市场情报", check_market_intel),
        check_stage("Agent管线", check_agent_pipeline),
        check_stage("数据采集", check_data_ingestion),
        check_stage("服务运行", check_services),
        check_stage("成本追踪", check_costs),
    ]

    # Calculate overall health
    total_score = sum(s["score"] for s in stages)
    overall = round(total_score / len(stages))
    issues = [s for s in stages if s["score"] < 60]

    # Determine status emoji
    if overall >= 90:
        emoji, status = "🟢", "健康"
    elif overall >= 60:
        emoji, status = "🟡", "部分异常"
    else:
        emoji, status = "🔴", "需要关注"

    now = datetime.now(TZ).strftime("%H:%M")

    # One-line summary
    summary = f"{emoji} [{now}] 管线健康度 {overall}/100"
    if issues:
        summary += f" | {len(issues)}项异常: {', '.join(s['name'] for s in issues[:3])}"

    print(f"\n  {summary}")
    print(f"  {'─' * 50}")
    for s in stages:
        icon = "✅" if s["score"] >= 80 else "⚠️" if s["score"] >= 40 else "❌"
        print(f"  {icon} {s['name']:8s} {s['score']:3d}分  {s['detail']}")

    # Save to file
    report = {
        "timestamp": datetime.now(TZ).isoformat(),
        "overall_score": overall,
        "status": status,
        "stages": stages,
        "summary": summary,
    }
    HEALTH_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    # Alert if degraded
    if send_alert and overall < 60:
        import urllib.request
        alert_text = urllib.parse.quote(f"🔴 管线健康度 {overall}/100 — {len(issues)}项异常")
        try:
            urllib.request.urlopen(
                f"http://localhost:8600/send?text={alert_text}",
                timeout=5,
            )
        except Exception:
            pass

    if output_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    return overall


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    p.add_argument("--alert", action="store_true")
    args = p.parse_args()
    score = main(args.json, args.alert)
    sys.exit(0 if score >= 60 else 1)
