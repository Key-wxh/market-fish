"""Market Intelligence v3 — data extraction + AI analysis"""
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter
import urllib.request

TZ = timezone(timedelta(hours=8))
NOW = datetime.now(TZ)
TODAY = NOW.strftime('%Y/%m/%d')
ROOT = Path('/home/ubuntu/apps/market-fish')
BRONZE = ROOT / 'data_lake' / 'bronze'
GOLD = ROOT / 'data_lake' / 'gold'
DS_KEY = 'sk-c1c48141f70c4e9b9d5542c9fff3b10f'

def load(prefix, date_dir=True):
    d = BRONZE / TODAY if date_dir else BRONZE
    if not d.exists(): return None
    files = sorted(d.glob(f'{prefix}_*.json'), reverse=True)
    if not files: return None
    try: return json.loads(files[0].read_text()).get('data',{})
    except: return None

def s(v, d='?'):
    if v is None: return d
    return str(v)

# ── Phase 1: Data extraction ──
facts = []

retail = load('retail_cn')
if retail:
    facts.append(f"社零: {retail.get('latest_month','?')} 同比{retail.get('latest_yoy_pct','?')}% 总额{retail.get('latest_value_yi','?')}亿元")

app = load('appstore')
if app:
    free = app.get('charts',{}).get('top_free',[]) or []
    paid = app.get('charts',{}).get('top_paid',[]) or []
    facts.append(f"App Store免费Top5: {', '.join(a.get('name','?')[:15] for a in free[:5])}")
    if paid:
        facts.append(f"App Store付费Top5: {', '.join(a.get('name','?')[:15] for a in paid[:5])}")

gh = load('github')
if gh:
    repos = gh.get('trending_repos',[]) or []
    topics = Counter()
    langs = Counter()
    for r in repos[:50]:
        if isinstance(r, dict):
            for t in r.get('topics',[])[:3]: topics[t] += 1
            if r.get('language'): langs[r.get('language')] += 1
    top3 = repos[:3]
    top_items = []
    for r in top3:
        if isinstance(r, dict):
            top_items.append(f'{r.get("full_name","?")[:25]} star:{r.get("stars","?")}')
    facts.append(f'GitHub热门: {len(repos)}仓库, 语言{langs.most_common(3)}, 主题{topics.most_common(5)}, Top: {"; ".join(top_items)}')

ph = load('producthunt')
if ph:
    facts.append(f"ProductHunt: {ph.get('total_launches','?')}新品 AI占比{ph.get('ai_ratio',0)*100:.0f}% 均票{ph.get('avg_votes','?')}")
    for l in (ph.get('top_launches',[]) or [])[:3]:
        if isinstance(l, dict):
            facts.append('PH热门: {} vote:{} -- {}'.format(l.get('name','?'), l.get('votes','?'), l.get('tagline','?')[:60]))

kr = load('36kr')
if kr:
    facts.append(f"36Kr: {kr.get('total_articles','?')}篇 AI占比{kr.get('ai_ratio',0)*100:.0f}% 赛道{sorted(kr.get('category_counts',{}).items(), key=lambda x:x[1], reverse=True)[:5]}")

hn = load('hackernews')
if hn:
    hn_hot = [t.get('topic','?') for t in (hn.get('hot_topics',[]) or [])[:5]]
    facts.append('HN: {}篇 AI帖{}% 均分{} 热点{}'.format(hn.get('stories_fetched','?'), int(hn.get('ai_story_ratio',0)*100), hn.get('avg_story_score','?'), hn_hot))

em = load('eastmoney')
if em:
    inds = []
    for ind in (em.get('industries',[]) or []):
        if isinstance(ind, dict):
            inds.append(f"{ind.get('icon','')}{ind.get('name','?')}(瓶颈{ind.get('bottlenecks','?')})")
    if inds:
        facts.append(f"产业链: {', '.join(inds[:6])}")

wb = load('weibo', False) or {}
bd = load('baidu', False) or {}
if bd:
    facts.append(f"百度热搜Top5: {', '.join(s(t.get('topic',''))[:15] for t in (bd.get('topics',[]) or [])[:5])}")
if wb:
    sents = Counter(t.get('sentiment','?') for t in (wb.get('topics',[]) or [])[:50])
    facts.append(f"微博情绪: 正面{sents.get('positive',0)} 中性{sents.get('neutral',0)} 负面{sents.get('negative',0)}")

# ── New sources ──
fred = load('fred')
if fred:
    indicators = []
    for ind in (fred.get('indicators',[]) or [])[:8]:
        if isinstance(ind, dict):
            indicators.append(f"{ind.get('name','?')}: {ind.get('latest_value','?')} ({ind.get('trend','?')})")
    if indicators:
        facts.append(f"全球经济指标: {'; '.join(indicators)}")

gt = load('google_trends')
if gt:
    trends = [t.get('topic','?') for t in (gt.get('trending',[]) or [])[:5]]
    if trends:
        facts.append(f"Google趋势: {', '.join(trends)}")

so = load('stackoverflow')
if so:
    so_tags = [t.get('tag','?') for t in (so.get('trending_tags',[]) or [])[:8]]
    if so_tags:
        facts.append(f"StackOverflow热门: {', '.join(so_tags)}")

ag_dir = ROOT / 'data_lake' / 'gold' / 'agents'
agent_count = len(list(ag_dir.glob('*.json'))) if ag_dir.exists() else 0

# ── FreeSearch: 151 topics, group by category ──
fs = load('freesearch')
if fs:
    topics = fs.get('topics', []) or []
    if topics:
        # Group by category prefix
        cats = {}
        for t in topics:
            topic_name = t.get('topic', '?')
            prefix = topic_name.split('_')[0] if '_' in topic_name else 'other'
            if prefix not in cats:
                cats[prefix] = []
            cats[prefix].append(t)

        # Show top categories by total results
        cat_summary = []
        for cat, tps in sorted(cats.items(), key=lambda x: sum(len(t.get('results',[])) for t in x[1]), reverse=True)[:8]:
            total = sum(len(t.get('results',[])) for t in tps)
            cat_summary.append(f"{cat}({total}篇/{len(tps)}主题)")
        facts.append(f"FreeSearch 151主题分布: {'; '.join(cat_summary)}")

        # Top 10 individual topics
        top = sorted(topics, key=lambda t: len(t.get('results', [])), reverse=True)[:10]
        facts.append('热点主题 Top10: ' + ' '.join('{} ({}篇)'.format(t['topic'], len(t.get('results',[]))) for t in top if t.get('results')))

facts.append(f"Agent池: {agent_count}个")

# Log sources used
used_sources = []
for prefix in ['retail_cn', 'appstore', 'github', 'producthunt', '36kr', 'hackernews',
               'eastmoney', 'weibo', 'baidu', 'freesearch', 'fred', 'google_trends', 'stackoverflow']:
    if load(prefix) or (prefix in ('weibo', 'baidu') and (wb or bd)):
        used_sources.append(prefix)
print(f"[INTEL v3] Sources loaded: {len(used_sources)} ({', '.join(used_sources[:8])}...)")

# ── Phase 2: AI Analysis ──
data_text = '\n'.join(f'- {f}' for f in facts)

prompt = f"""你是独立市场分析师。下面是从多个数据源采集的今日实时数据：

{data_text}

请基于这些数据做客观分析。注意：
- 只基于数据推理，不要编造数据中没有的信息
- 不要预设结论，让数据自己说话
- 如果你看到的数据和常见观点不一致，以数据为准
- 如果某个方向没有足够数据支撑，诚实说"数据不足"

请按以下结构输出：

## 周期雷达
基于消费、技术投资、资源价格、社会情绪四个维度，判断当前位置。给出置信度。用具体数据。

## 市场信号
从数据中提取 3-5 个信号。每个信号要：A) 在至少 2 个独立数据源中有体现 B) 说明这意味着什么。如果没有足够的交叉验证，就少写。

## 值得关注的方向
1-3 个被低估的趋势或机会。不限于任何行业，只要数据有支撑。

用中文大白话。不要写"原始数据"或"本周行动"段落。"""

body = json.dumps({
    "model": "deepseek-v4-flash",
    "messages": [{"role": "user", "content": prompt}],
    "max_tokens": 4000,
    "temperature": 0.3,
})

req = urllib.request.Request(
    'https://api.deepseek.com/v1/chat/completions',
    data=body.encode(),
    headers={'Authorization': f'Bearer {DS_KEY}', 'Content-Type': 'application/json'}
)

analysis = None
last_err = ''
for attempt in range(3):
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        result = json.loads(resp.read())
        analysis = result['choices'][0]['message']['content']
        break
    except Exception as e:
        last_err = str(e)
        if attempt < 2:
            import time as _time
            _time.sleep(5 * (attempt + 1))  # 5s, 10s backoff
if analysis is None:
    analysis = f'AI分析暂时不可用：{last_err}'

# ── Phase 3: Generate HTML ──
import re

def md2html(text):
    lines = text.split('\n')
    html = []
    buf = ''
    in_para = False

    for line in lines:
        line = line.strip()

        # Headers
        if line.startswith('### '):
            if buf: html.append('<p>' + buf + '</p>'); buf = ''
            html.append('<h4>' + line[4:] + '</h4>')
            continue
        if line.startswith('## '):
            if buf: html.append('<p>' + buf + '</p>'); buf = ''
            html.append('<h3>' + line[3:] + '</h3>')
            continue

        # Empty line = paragraph break
        if not line:
            if buf: html.append('<p>' + buf + '</p>'); buf = ''
            continue

        # Bullet points
        if line.startswith('- '):
            if buf: html.append('<p>' + buf + '</p>'); buf = ''
            html.append('<p style="padding-left:16px;margin:2px 0">• ' + line[2:] + '</p>')
            continue

        # Accumulate paragraph text
        if buf:
            buf += '<br>' + line
        else:
            buf = line

    if buf: html.append('<p>' + buf + '</p>')

    result = '\n'.join(html)
    # Bold
    result = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', result)
    return result

analysis_html = md2html(analysis)

raw_data_html = '<br>'.join(facts)

html_report = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>市场情报 · {NOW.strftime("%m月%d日")}</title>
<style>
:root {{--bg:#0f172a;--card:#1e293b;--text:#e2e8f0;--muted:#94a3b8;--accent:#3B82F6;--border:rgba(148,163,184,0.15);--green:#22c55e;--red:#ef4444}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:var(--bg);color:var(--text);max-width:800px;margin:0 auto;padding:2rem 1.5rem;line-height:1.7}}
h1{{font-size:1.8rem;font-weight:800;margin-bottom:1.5rem;padding-bottom:0.8rem;border-bottom:2px solid var(--accent)}}
h2{{font-size:1.3rem;font-weight:700;margin:1.5rem 0 0.8rem}}
h3{{font-size:1.1rem;font-weight:600;margin:1.2rem 0 0.5rem;color:var(--accent)}}
h4{{font-size:1rem;font-weight:600;margin:1rem 0 0.4rem}}
p{{margin:0.5rem 0;color:var(--text)}}
strong{{color:#fff}}
.analysis-block{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:1.5rem;margin:1rem 0}}
.data-toggle{{cursor:pointer;color:var(--accent);font-size:0.9rem;margin:1rem 0;user-select:none}}
.data-block{{display:none;background:var(--card);border:1px solid var(--border);border-radius:8px;padding:1rem;font-size:0.85rem;color:var(--muted);line-height:1.8;max-height:400px;overflow-y:auto}}
.data-block.show{{display:block}}
.footer-bar{{text-align:center;color:var(--muted);font-size:0.75rem;margin-top:2rem;padding-top:1rem;border-top:1px solid var(--border)}}
.refresh-btn,.share-btn{{padding:8px 20px;border-radius:8px;font-size:0.85rem;cursor:pointer;transition:all 0.2s}}
.refresh-btn{{background:var(--card);color:var(--text);border:1px solid var(--border)}}
.refresh-btn:hover{{background:var(--border)}}
.share-btn{{background:var(--accent);color:#fff;border:none}}
.share-btn:hover{{opacity:0.9}}
</style></head><body>
<a href="/app/overview.html" style="display:inline-flex;align-items:center;gap:4px;color:var(--muted);text-decoration:none;font-size:0.85rem;margin-bottom:1rem;padding:6px 12px;border-radius:6px;border:1px solid var(--border)" onmouseover="this.style.color='#fff'" onmouseout="this.style.color='var(--muted)'">← 返回总览</a>
<h1>市场情报 · {NOW.strftime("%m月%d日")}</h1>

<h2>🧠 AI 分析</h2>
<div class="analysis-block">
{analysis_html}
</div>

<div class="data-toggle" onclick="this.nextElementSibling.classList.toggle('show')">📋 查看原始数据 ▼</div>
<div class="data-block">{raw_data_html}</div>

<div class="footer-bar">156源 · DeepSeek分析 · 每日08:00自动更新</div>
<div style="display:flex;gap:8px;justify-content:center;margin-top:12px">
  <button class="refresh-btn" onclick="location.reload()">刷新</button>
  <button class="share-btn" onclick="shareIntel()">📤 分享</button>
</div>
<script>
function shareIntel(){{var t=document.querySelector('.analysis-block');t=t?t.innerText:'';t=t.replace(/\\n\\n\\n+/g,'\\n\\n').trim();var h=document.querySelector('h1');h=h?h.innerText:'市场情报';if(navigator.share){{navigator.share({{title:h,text:t.substring(0,500)+'...'}})}}else{{var a=document.createElement('textarea');a.value=h+'\\n\\n'+t;document.body.appendChild(a);a.select();document.execCommand('copy');document.body.removeChild(a);alert('已复制到剪贴板，去微信/朋友圈粘贴')}}}}
</script>
</body></html>"""

# Save raw markdown for API
md_report = f"""# 市场情报 · {NOW.strftime("%m月%d日")}

{analysis}
"""

# Save current (live page)
(GOLD / 'market_intel.md').write_text(md_report)
(GOLD / 'market_intel.html').write_text(html_report)

# Save dated archive (永久存储)
date_str = NOW.strftime('%Y-%m-%d')
archive_dir = GOLD / 'intel_archive'
archive_dir.mkdir(exist_ok=True)
(archive_dir / f'market_intel_{date_str}.md').write_text(md_report)
(archive_dir / f'market_intel_{date_str}.html').write_text(html_report)

# Keep last 90 days
files = sorted(archive_dir.glob('*.md'))
for f in files[:-90]:
    f.unlink()
    html_f = archive_dir / (f.stem + '.html')
    if html_f.exists(): html_f.unlink()

count = len(list(archive_dir.glob('*.md')))
print(f'[INTEL v3] OK — {len(md_report)} chars | archive: {count} reports')

# Add share image to html report  
if (GOLD / 'intel_share.png').exists():
    share_url = '\n<div style="text-align:center;margin-top:12px"><a href="/api/market-intel/share.png" style="color:var(--accent);font-size:12px;text-decoration:none">📸 下载分享图</a></div>'
    html_report = html_report.replace('</body>', share_url + '\n</body>')
