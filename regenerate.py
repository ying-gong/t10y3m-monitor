"""
美债10Y-3M利差仪表盘 — 数据刷新 + HTML 重新生成
用于 GitHub Actions 定时任务，每次运行都会拉取最新数据并内嵌到 HTML 中。
"""
import json, urllib.request, os, time

BASE = os.path.dirname(os.path.abspath(__file__))
RANGES = {'3mo': '3mo', '1y': '1y', '5y': '5y', '10y': '10y', 'max': 'max'}

def fetch(symbol, rng):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={rng}'
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json'
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            result = data['chart']['result'][0]
            timestamps = result['timestamp']
            closes = result['indicators']['quote'][0]['close']
            valid = [(t, round(c, 4)) for t, c in zip(timestamps, closes) if c is not None]
            return valid
        except Exception as e:
            print(f'  Retry {attempt+1}: {e}')
            time.sleep(2)
    raise Exception(f'Failed to fetch {symbol} {rng}')

def fetch_shiller_pe():
    """Fetch Shiller PE data from datahub.io"""
    url = 'https://datahub.io/core/s-and-p-500/r/data.csv'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        lines = resp.read().decode('utf-8').strip().split('\n')
    import csv, io, datetime
    reader = csv.DictReader(io.StringIO('\n'.join(lines)))
    rows = []
    for r in reader:
        pe10 = float(r['PE10']) if r['PE10'] and r['PE10'].strip() else 0.0
        if pe10 > 0:
            dt = datetime.datetime.strptime(r['Date'], '%Y-%m-%d')
            ts = int((dt - datetime.datetime(1970, 1, 1)).total_seconds())
            rows.append({'t': ts, 'v': round(pe10, 2)})
    print(f'  Shiller PE: {len(rows)} monthly points, latest={rows[-1]["v"]} ({rows[-1]["t"]})')
    return rows

def main():
    print('Fetching all range data...')
    all_data = {}
    for label, rng in RANGES.items():
        for sym in ['^TNX', '^IRX']:
            key = f'{sym}_{label}'
            all_data[key] = fetch(sym, rng)
            print(f'  {sym} {label}: {len(all_data[key])} pts')

    # Live prices
    live = {}
    for sym in ['^TNX', '^IRX']:
        data = fetch(sym, '1d')
        url = f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            j = json.loads(resp.read())
        live[sym] = j['chart']['result'][0]['meta']['regularMarketPrice']

    spread = round(live['^TNX'] - live['^IRX'], 4)
    print(f'Live: TNX={live["^TNX"]}, IRX={live["^IRX"]}, Spread={spread}')

    # Build pre-computed spreads
    ranges_data = {}
    for label in RANGES:
        tnx_key = f'^TNX_{label}'
        irx_key = f'^IRX_{label}'
        irx_map = {t: v for t, v in all_data[irx_key]}
        points = []
        for t, tnx_v in all_data[tnx_key]:
            if t in irx_map:
                s = round(tnx_v - irx_map[t], 4)
                points.append({'t': t, 'tnx': tnx_v, 'irx': irx_map[t], 's': s})
        ranges_data[label] = points

    # Inline data into HTML
    ranges_js = json.dumps(ranges_data, separators=(',', ':'))
    live_js = json.dumps(live)

    # Also fetch Shiller PE data
    print('Fetching Shiller PE data...')
    shiller_rows = fetch_shiller_pe()
    shiller_js = json.dumps(shiller_rows, separators=(',', ':'))

    html_path = os.path.join(BASE, 't10y3m-dashboard.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    import re
    # Replace RANGES_DATA
    pattern = r'(const RANGES_DATA = )\{.*?\};(?=\s*\n\s*const SHILLER_DATA)'
    replacement = f'\\1{ranges_js};'
    html = re.sub(pattern, replacement, html, count=1, flags=re.DOTALL)

    # Replace SHILLER_DATA
    pattern_s = r'(const SHILLER_DATA = )\[.*?\];(?=\s*\n\s*const LIVE_PRICES)'
    replacement_s = f'\\1{shiller_js};'
    html = re.sub(pattern_s, replacement_s, html, count=1, flags=re.DOTALL)

    # Replace LIVE_PRICES
    pattern2 = r'(const LIVE_PRICES = )\{.*?\};'
    replacement2 = f'\\1{live_js};'
    html = re.sub(pattern2, replacement2, html, count=1)

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print('HTML updated with fresh data.')
    print(f'Output: {html_path} ({os.path.getsize(html_path)} bytes)')

if __name__ == '__main__':
    main()
