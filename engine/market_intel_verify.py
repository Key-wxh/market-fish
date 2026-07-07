#!/usr/bin/env python3
"""
Market Intel Quality Gate — ruflo Verification Gate 模式

在市场情报生成后、发布前运行。检查内容质量，低于阈值则阻断发布。

用法: python3 market_intel_verify.py [input_file] [--min-score 60]
cron: market_intel.py && market_intel_verify.py && wechat_publish.py
"""
import sys, re, json
from pathlib import Path
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
ROOT = Path(__file__).parent.parent
INTEL_PATH = ROOT / "data_lake" / "gold" / "market_intel.md"
LOG_PATH = ROOT / "data_lake" / "gold" / "intel_quality_log.json"


def load_log() -> list:
    if LOG_PATH.exists():
        try:
            return json.loads(LOG_PATH.read_text())
        except Exception:
            pass
    return []


def save_log(entries: list):
    # Keep last 90 days
    LOG_PATH.write_text(json.dumps(entries[-90:], ensure_ascii=False, indent=2))


def check_content(text: str) -> dict:
    """Run quality checks on market intel content. Returns {score, issues, passed}."""

    issues = []
    score = 100

    # 1. Length check (30 points)
    if len(text) < 300:
        issues.append("内容过短 (<300字)")
        score -= 30
    elif len(text) < 800:
        issues.append("内容偏短 (<800字)")
        score -= 10

    # 2. Required sections (30 points)
    required_sections = ["市场", "行业", "经济", "科技", "数据"]
    found_sections = [s for s in required_sections if s in text]
    missing = len(required_sections) - len(found_sections)
    if missing > 0:
        score -= missing * 6
        if missing >= 3:
            issues.append(f"缺少关键板块: {missing}个")

    # 3. Hallucination check (20 points) — detect suspicious patterns
    hallucination_patterns = [
        (r"\d{3,}%", "可疑百分比"),
        (r"\d+万亿", "可疑大数"),
        (r"突破.*万亿", "夸张表述"),
        (r"暴涨|暴跌|狂飙|雪崩", "情绪化标题"),
        (r"震惊|重磅|突发|刚刚", "标题党词汇"),
    ]
    for pattern, desc in hallucination_patterns:
        if re.search(pattern, text):
            score -= 4
            if score > 0:  # Don't double-report
                issues.append(f"疑似夸大: {desc}")

    # 4. Structure check (10 points)
    if not re.search(r"^#{1,3}\s", text, re.MULTILINE):
        issues.append("缺少标题结构")
        score -= 10

    # 5. Freshness check (10 points) — contains today's date or "今日"/"最新"
    today_cn = datetime.now(TZ).strftime("%m月%d日")
    if today_cn not in text and "今日" not in text and "最新" not in text:
        issues.append("缺少时效性标注")
        score -= 5

    score = max(0, min(100, score))
    passed = score >= 60

    return {"score": score, "passed": passed, "issues": issues}


def main(input_file: str = None, min_score: int = 60):
    path = Path(input_file) if input_file else INTEL_PATH
    if not path.exists():
        print(f"  ❌ 情报文件不存在: {path}")
        return False

    text = path.read_text(encoding="utf-8")
    result = check_content(text)

    # Log
    log = load_log()
    log.append({
        "date": datetime.now(TZ).strftime("%Y-%m-%d"),
        "time": datetime.now(TZ).strftime("%H:%M"),
        "file": str(path),
        **result,
    })
    save_log(log)

    # Report
    print(f"\n  📊 市场情报质量检查")
    print(f"  评分: {result['score']}/100 {'✅' if result['passed'] else '❌'}")
    if result["issues"]:
        for issue in result["issues"]:
            print(f"  ⚠️  {issue}")

    # Trend
    if len(log) >= 3:
        recent = [l["score"] for l in log[-7:]]
        avg = sum(recent) / len(recent)
        trend = "📈" if recent[-1] > avg else "📉" if recent[-1] < avg else "➡️"
        print(f"  7日均分: {avg:.0f} {trend}")

    if not result["passed"]:
        print(f"\n  ⛔ 质量不达标 ({result['score']} < {min_score})，阻断发布")
        return False

    return True


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("input_file", nargs="?", default=None)
    p.add_argument("--min-score", type=int, default=60)
    args = p.parse_args()
    ok = main(args.input_file, args.min_score)
    sys.exit(0 if ok else 1)
