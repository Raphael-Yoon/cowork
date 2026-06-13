# -*- coding: utf-8 -*-
"""
STEP 2 데이터 수집 및 1차 필터링/최종 스코어링 도구 (IT 감사팀 전용)
기준 문서: cowork/Report/audit_logic.md

역할: stock_pool 종목의 시장 데이터·뉴스·공시를 수집하고, AI 분석용 콘텍스트를 도출하거나
      AI가 평가한 뉴스/공시 스코어를 입력받아 최종 스코어링 및 정렬을 수행합니다.

사용법:
    python cowork/select_top_10.py
"""
import sys
import os
import json
import psycopg2
import psycopg2.extras
import OpenDartReader
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

COWORK_DIR = Path(__file__).resolve().parent
TRADE_DIR = COWORK_DIR.parent / 'trade'

if os.name == 'nt':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# get_all_naver_data.py는 현재 cowork/ 내부에 있으므로 직접 임포트합니다.
try:
    from get_all_naver_data import get_all_naver_data
except ImportError:
    print("[오류] cowork/get_all_naver_data.py 모듈을 찾을 수 없습니다.")
    sys.exit(1)



def collect_candidate(cand, pool, dart_key):
    """종목 1개의 시장 데이터·뉴스·공시를 수집하여 반환."""
    code = cand['code']
    name = cand['name']

    if name.endswith(('우', '우B', '우C', '우(전환)', '3우B')):
        return None

    try:
        naver_data = get_all_naver_data(code)
    except Exception as e:
        print(f"  [수집 오류] {name}({code}): {e}", file=sys.stderr)
        return None

    current_price = naver_data.get('current_price', 0)
    target_price = naver_data.get('target_price', 0)
    roe = naver_data.get('roe', 0.0)
    debt = naver_data.get('debt_ratio', 0.0)

    if target_price <= 0 or current_price <= 0:
        return None

    upside = round(((target_price - current_price) / current_price) * 100.0, 1)
    if upside <= 0:
        return None

    ma5_diff  = naver_data.get('ma5_diff', 0.0)
    ma20_diff = naver_data.get('ma20_diff', 0.0)

    # DART 공시 수집 (최근 30일)
    disclosures = []
    if dart_key:
        try:
            dart = OpenDartReader(dart_key)
            end_dt   = datetime.now()
            start_dt = end_dt - timedelta(days=30)
            df = dart.list(code, start=start_dt.strftime('%Y%m%d'), end=end_dt.strftime('%Y%m%d'))
            if df is not None and len(df) > 0:
                for _, row in df.iterrows():
                    raw_dt   = str(row.get('rcept_dt', ''))
                    rcept_dt = f"{raw_dt[:4]}-{raw_dt[4:6]}-{raw_dt[6:]}" if len(raw_dt) == 8 else raw_dt
                    disclosures.append({
                        'report_nm': row.get('report_nm', ''),
                        'rcept_dt':  rcept_dt,
                        'rcept_no':  row.get('rcept_no', ''),
                        'flr_nm':    row.get('flr_nm', ''),
                        'corp_cls':  row.get('corp_cls', ''),
                        'rm':        row.get('rm', ''),
                    })
        except Exception:
            pass

    # Hard Filter: 중대 공시 (감사의견 비적정, 배임·횡령)
    for d in disclosures:
        if any(t in d['report_nm'] for t in ['감사의견', '의견거절', '부적정', '한정', '내부회계', '배임', '횡령']):
            return None

    # 뉴스 수집
    news = [
        {'title': n.get('title', ''), 'link': n.get('link', ''),
         'source': n.get('source', '네이버 금융'), 'date': n.get('date', '')}
        for n in naver_data.get('news', [])[:10]
    ]

    return {
        'code':          code,
        'name':          name,
        'sector':        naver_data.get('industry_name', '기타'),
        'current_price': current_price,
        'target_price':  target_price,
        'upside':        upside,
        'roe':           roe,
        'debt':          debt,
        'ma5_diff':      round(ma5_diff, 2),
        'ma20_diff':     round(ma20_diff, 2),
        'foreign_5d_net': naver_data.get('foreign_5d_net', 0),
        'inst_5d_net':    naver_data.get('inst_5d_net', 0),
        'price_position_52w': naver_data.get('price_position_52w', 50.0),
        'pbr':           naver_data.get('pbr', 0.0),
        'dividend_yield': naver_data.get('dividend_yield', 0.0),
        'news':          news,
        'disclosures':   disclosures,
    }


def run_collection():
    from dotenv import load_dotenv
    load_dotenv(TRADE_DIR / '.env')
    database_url = os.getenv('DATABASE_URL')
    dart_key     = os.getenv('DART_API_KEY')

    conn   = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.DictCursor)
    cursor = conn.cursor()
    cursor.execute("SELECT code, name, roe, debt_ratio FROM stock_pool")
    rows = cursor.fetchall()
    conn.close()

    pool       = [{'code': r['code'], 'name': r['name'],
                   'roe': r['roe'] or 0.0, 'debt': r['debt_ratio'] or 0.0} for r in rows]
    candidates = [{'code': r['code'], 'name': r['name']} for r in rows]

    # 중복 제거
    seen = set()
    unique = []
    for c in candidates:
        if c['code'] not in seen:
            seen.add(c['code'])
            unique.append(c)
    candidates = unique
    
    print(f"수집 대상: {len(candidates)}개 종목\n")

    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(collect_candidate, c, pool, dart_key): c for c in candidates}
        done = 0
        for future in as_completed(futures):
            done += 1
            res = future.result()
            if res:
                results.append(res)
            if done % 20 == 0 or done == len(candidates):
                print(f"  진행: {done}/{len(candidates)}", file=sys.stderr)

    # 상승여력 기준 정렬 (AI 검토 편의)
    results.sort(key=lambda x: x['upside'], reverse=True)

    print(f"\n{'='*60}")
    print(f"STEP 2 수집 완료 — {len(results)}개 후보 (Hard Filter 통과)")
    print(f"{'='*60}\n")

    for i, r in enumerate(results, 1):
        f_net = r['foreign_5d_net']
        i_net = r['inst_5d_net']
        trend = "역배열" if r['ma5_diff'] <= 0 and r['ma20_diff'] <= 0 else "정배열"
        print(f"[{i:>3}] {r['name']} ({r['code']}) | {r['sector']}")
        print(f"       현재가 {r['current_price']:,} | 목표가 {r['target_price']:,} | 상승여력 {r['upside']}%")
        print(f"       ROE {r['roe']:.1f}% | 부채 {r['debt']:.1f}% | PBR {r['pbr']:.2f} | 배당 {r['dividend_yield']:.1f}%")
        print(f"       수급 외인 {'▲' if f_net > 0 else '▼'}{abs(f_net):,} / 기관 {'▲' if i_net > 0 else '▼'}{abs(i_net):,} | 추세 {trend}")
        if r['news']:
            print(f"       뉴스:")
            for n in r['news']:
                print(f"         - [{n['source']}] {n['title']} ({n['date']})")
        if r['disclosures']:
            print(f"       공시 (최근 30일):")
            for d in r['disclosures']:
                print(f"         - [{d['rcept_dt']}] {d['report_nm']}")
        print()

    return results


if __name__ == '__main__':
    run_collection()
