#!/usr/bin/env python3
"""
Cost Anomaly Detection — ruflo Circuit Breaker 模式

每日成本聚合后运行。检测异常波动（日环比 ±50%），发现异常则通过小溪 API 告警。

用法: python3 cost_anomaly.py [--threshold 0.5]
cron: cost_aggregator.py && cost_anomaly.py
"""
import sys, json, urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
ROOT = Path(__file__).parent.parent
COST_DIR = ROOT / "data_lake" / "gold"
ALERT_URL = "http://localhost:8600/send"

# Cost categories to track
CATEGORIES = ["deepseek_api", "supabase", "server", "other"]


def get_cost_history(days: int = 14) -> list:
    """Load recent cost records from JSON files."""
    records = []
    cost_files = sorted(COST_DIR.glob("cost_*.json"))
    for cf in cost_files[-days:]:
        try:
            data = json.loads(cf.read_text())
            records.append(data)
        except Exception:
            pass
    return records


def detect_anomaly(records: list, threshold: float = 0.5) -> dict:
    """Compare today vs yesterday. Returns {anomaly: bool, details: [...]}."""
    if len(records) < 2:
        return {"anomaly": False, "details": [], "today_total": 0, "yesterday_total": 0}

    today = records[-1]
    yesterday = records[-2]

    today_total = today.get("total_cny", 0)
    yesterday_total = yesterday.get("total_cny", 0)

    if yesterday_total <= 0:
        return {"anomaly": False, "details": [], "today_total": today_total, "yesterday_total": yesterday_total}

    change = (today_total - yesterday_total) / yesterday_total
    details = []

    # Overall anomaly
    if abs(change) > threshold:
        direction = "上升" if change > 0 else "下降"
        details.append({
            "type": "总成本",
            "today": today_total,
            "yesterday": yesterday_total,
            "change_pct": round(change * 100, 1),
            "direction": direction,
        })

    # Per-category anomaly
    for cat in CATEGORIES:
        t_val = today.get(cat, 0)
        y_val = yesterday.get(cat, 0)
        if y_val > 0:
            cat_change = (t_val - y_val) / y_val
            if abs(cat_change) > threshold:
                direction = "上升" if cat_change > 0 else "下降"
                details.append({
                    "type": cat,
                    "today": t_val,
                    "yesterday": y_val,
                    "change_pct": round(cat_change * 100, 1),
                    "direction": direction,
                })

    return {
        "anomaly": len(details) > 0,
        "details": details,
        "today_total": today_total,
        "yesterday_total": yesterday_total,
        "overall_change_pct": round(change * 100, 1),
    }


def send_alert(result: dict):
    """Send alert via xiaoxi API."""
    details = result["details"]
    if not details:
        return

    lines = [f"⚠️ 成本异常告警"]
    lines.append(f"今日 ¥{result['today_total']:.2f} vs 昨日 ¥{result['yesterday_total']:.2f} ({result['overall_change_pct']:+.1f}%)")
    lines.append("")
    for d in details[:3]:  # Max 3 items
        lines.append(f"• {d['type']}: ¥{d['today']:.2f} ({d['change_pct']:+.1f}%)")

    msg = "\n".join(lines)
    try:
        encoded = urllib.parse.quote(msg)
        req = urllib.request.Request(
            f"{ALERT_URL}?text={encoded}",
            headers={"Authorization": "Bearer xiaoxi-internal"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                print(f"  ✅ 告警已发送")
    except Exception as e:
        print(f"  ⚠️ 告警发送失败: {e}")


def main(threshold: float = 0.5):
    print(f"\n  💰 成本异常检测 (阈值: ±{threshold:.0%})")

    records = get_cost_history()
    if len(records) < 2:
        print("  数据不足 (需要至少2天记录)")
        return True

    result = detect_anomaly(records, threshold)

    print(f"  今日: ¥{result['today_total']:.2f}")
    print(f"  昨日: ¥{result['yesterday_total']:.2f}")
    print(f"  变化: {result['overall_change_pct']:+.1f}%")

    if result["anomaly"]:
        print(f"\n  🚨 检测到 {len(result['details'])} 项异常:")
        for d in result["details"]:
            print(f"  • {d['type']}: ¥{d['yesterday']:.2f} → ¥{d['today']:.2f} ({d['change_pct']:+.1f}%)")
        send_alert(result)
    else:
        print(f"  ✅ 无异常")

    return True


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--threshold", type=float, default=0.5)
    args = p.parse_args()
    main(args.threshold)
