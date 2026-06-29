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
import sqlite3
import OpenDartReader
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

COWORK_DIR = Path(__file__).resolve().parent
TRADE_DIR = COWORK_DIR.parent / 'trade'

# 최종 추천에서 제외할 업종 키워드 (바이오·제약·헬스케어)
EXCLUDED_SECTORS = ['제약', '바이오', '건강관리', '헬스케어']

def is_excluded_sector(sector: str) -> bool:
    return any(k in (sector or '') for k in EXCLUDED_SECTORS)

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



def parse_market_cap(cap_str):
    if not cap_str or cap_str == 'N/A':
        return 0.0
    import re
    s = str(cap_str).replace(',', '').strip()
    val = 0.0
    m_cho = re.search(r'(\d+)조', s)
    m_uk = re.search(r'(\d+)억', s)
    if m_cho:
        val += float(m_cho.group(1)) * 1000000000000
    if m_uk:
        val += float(m_uk.group(1)) * 100000000
    if not m_cho and not m_uk:
        nums = re.findall(r'\d+', s)
        if nums:
            val = float(nums[0])
    return val


def collect_candidate(cand, pool, dart_key, sector_avg_pbr=None):
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

    if current_price <= 0:
        return None

    is_estimated_tp = False
    if target_price <= 0:
        # 자체 목표주가 추정: BPS × min(섹터 평균 PBR, 3.0)
        bps = naver_data.get('bps', 0)
        sector = cand.get('sector', '기타')
        avg_pbr = (sector_avg_pbr or {}).get(sector, 0.0)
        if bps > 0 and avg_pbr > 0:
            target_price = int(bps * min(avg_pbr, 3.0))
            is_estimated_tp = True
        if target_price <= 0:
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
        'is_estimated_tp': is_estimated_tp,
        'roe':           roe,
        'debt':          debt,
        'ma5_diff':      round(ma5_diff, 2),
        'ma20_diff':     round(ma20_diff, 2),
        'foreign_5d_net': naver_data.get('foreign_5d_net', 0),
        'inst_5d_net':    naver_data.get('inst_5d_net', 0),
        'foreign_5d_weighted': naver_data.get('foreign_5d_weighted', 0.0),
        'inst_5d_weighted':    naver_data.get('inst_5d_weighted', 0.0),
        'foreign_today_net':   naver_data.get('foreign_today_net', 0),
        'inst_today_net':      naver_data.get('inst_today_net', 0),
        'price_position_52w': naver_data.get('price_position_52w', 50.0),
        'pbr':           naver_data.get('pbr', 0.0),
        'dividend_yield': naver_data.get('dividend_yield', 0.0),
        'news':          news,
        'disclosures':   disclosures,
        'is_sector_leader': cand.get('is_sector_leader', False),
        'market_cap':    parse_market_cap(naver_data.get('market_cap', 'N/A')),
        'data_date':     cand.get('data_date'),
        'source_file':   cand.get('source_file'),
    }


def _enrich_items(items: list, evals: list, key: str) -> list:
    """
    items(공시 또는 뉴스 목록)의 각 항목에 sentiment/reason을 주입한다.
    evals는 ai_evaluations.json의 disc_evals 또는 news_evals 배열.
    keyword가 items[key] 필드에 포함될 경우 매칭으로 판단.
    """
    if not evals:
        return items
    enriched = []
    for item in items:
        text = item.get(key, '')
        matched = next((e for e in evals if e.get('keyword', '') in text), None)
        if matched:
            item = dict(item)
            item['sentiment'] = matched['sentiment']
            item['reason'] = matched['reason']
        enriched.append(item)
    return enriched


def run_collection(source_file=None):
    from dotenv import load_dotenv
    load_dotenv(TRADE_DIR / '.env')
    database_url = os.getenv('DATABASE_URL')
    dart_key     = os.getenv('DART_API_KEY')

    db_type = 'sqlite'
    if database_url and database_url.startswith('postgresql'):
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.DictCursor)
        cursor = conn.cursor()
        db_type = 'postgres'
    elif database_url and database_url.startswith('mysql'):
        import pymysql
        from urllib.parse import urlparse
        parsed = urlparse(database_url)
        conn = pymysql.connect(
            host=parsed.hostname or '127.0.0.1',
            port=parsed.port or 3306,
            user=parsed.username or 'root',
            password=parsed.password or '',
            database=parsed.path.lstrip('/') if parsed.path else 'trade',
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        cursor = conn.cursor()
        db_type = 'mysql'
    else:
        import sqlite3
        SQLITE_PATH = TRADE_DIR / 'trade.db'
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        db_type = 'sqlite'

    if not source_file:
        import argparse
        parser = argparse.ArgumentParser(description="Top 10 추천종목 선정")
        parser.add_argument('--source_file', help='특정 소스 파일명 기준 Pool 조회')
        args, unknown = parser.parse_known_args()
        source_file = args.source_file

    if not source_file:
        cursor.execute("""
            SELECT DISTINCT source_file, data_date FROM tr_stock_pool 
            ORDER BY data_date DESC
        """)
        pools = cursor.fetchall()
        if pools:
            print("\n=== 사용 가능한 Pool 목록 ===")
            for idx, p in enumerate(pools, 1):
                print(f"[{idx}] 파일명: {p['source_file']} (기준일: {p['data_date']})")

            try:
                if sys.stdin.isatty():
                    print(f"\n작업할 Pool의 번호를 입력하세요 (기본값 [1]): ", end="")
                    sys.stdout.flush()
                    sel = sys.stdin.readline().strip()
                    if sel:
                        choice = int(sel) - 1
                        if 0 <= choice < len(pools):
                            source_file = pools[choice]['source_file']
                        else:
                            print("잘못된 번호입니다. 최신 Pool을 사용합니다.")
                            source_file = pools[0]['source_file']
                    else:
                        source_file = pools[0]['source_file']
                else:
                    source_file = pools[0]['source_file']
            except Exception:
                source_file = pools[0]['source_file']
        else:
            print("최근 적재된 소스 파일이 없어 전체 조회합니다...")

    placeholder = '?' if db_type == 'sqlite' else '%s'
    if source_file:
        print(f"\n[선택된 Pool] 소스 파일({source_file}) 기준 tr_stock_pool 조회 중...")
        cursor.execute(f"""
            SELECT code, name, sector, roe, debt_ratio, pbr, is_sector_leader, market_cap, data_date, source_file
            FROM tr_stock_pool
            WHERE source_file = {placeholder}
        """, (source_file,))
    else:
        cursor.execute("SELECT code, name, sector, roe, debt_ratio, pbr, is_sector_leader, market_cap, data_date, source_file FROM tr_stock_pool")

    rows = cursor.fetchall()
    conn.close()

    # 섹터별 평균 PBR 계산 (자체 목표주가 추정용)
    from collections import defaultdict
    sector_pbr_map = defaultdict(list)
    for r in rows:
        pbr_val = r['pbr'] if r['pbr'] else 0.0
        if pbr_val > 0:
            sector_pbr_map[r['sector'] or '기타'].append(float(pbr_val))
    sector_avg_pbr = {s: sum(vals) / len(vals) for s, vals in sector_pbr_map.items() if vals}

    pool       = [{'code': r['code'], 'name': r['name'],
                   'roe': r['roe'] or 0.0, 'debt': r['debt_ratio'] or 0.0,
                   'is_sector_leader': bool(r['is_sector_leader']),
                   'market_cap': r['market_cap'] or 0.0,
                   'data_date': r['data_date'],
                   'source_file': r['source_file']} for r in rows]
    candidates = [{'code': r['code'], 'name': r['name'],
                   'sector': r['sector'] or '기타',
                   'is_sector_leader': bool(r['is_sector_leader']),
                   'market_cap': r['market_cap'] or 0.0,
                   'data_date': r['data_date'],
                   'source_file': r['source_file']} for r in rows]

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
        futures = {executor.submit(collect_candidate, c, pool, dart_key, sector_avg_pbr): c for c in candidates}
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


def generate_fallback_oneliner(r):
    is_leader = r.get("is_sector_leader", False)
    roe = r.get("roe", 0.0)
    upside = r.get("upside", 0.0)
    sector = r.get("sector", "기타")
    debt = r.get("debt", 0.0)
    
    if is_leader:
        if roe >= 30:
            return f"ROE {roe:.1f}%의 압도적인 자본효율성을 자랑하는 {sector} 업종 대표 대장주"
        else:
            return f"안정적인 수급 흐름과 높은 업종 대표성을 지닌 {sector} 섹터 대장주"
    else:
        if upside >= 50:
            return f"목표주가 대비 {upside}%의 우수한 상승 여력(마진)을 보유한 {sector} 저평가주"
        elif roe >= 25:
            return f"자기자본이익률(ROE) {roe:.1f}%로 강력한 수익성을 입증한 {sector} 알짜 우량주"
        else:
            return f"부채비율 {debt:.1f}% 수준의 우수한 재무 건전성을 유지하고 있는 {sector} 우량 기업"


if __name__ == '__main__':
    results = run_collection()
    
    # ai_evaluations.json 로드 시도
    ai_eval_path = COWORK_DIR / "ai_evaluations.json"
    ai_evals = {}
    if ai_eval_path.exists():
        try:
            with open(ai_eval_path, encoding='utf-8') as f:
                data = json.load(f)
                # 배열 형식인 경우 딕셔너리로 변환
                if isinstance(data, list):
                    ai_evals = {item["code"]: item for item in data}
                else:
                    ai_evals = data
            print(f"  [안내] {ai_eval_path.name} 로드 완료. AI 정성 점수를 계산에 반영합니다.")
        except Exception as e:
            print(f"  [경고] AI 평가 파일 로드 실패: {e}")
    else:
        print(f"  [안내] {ai_eval_path.name} 파일이 존재하지 않아 기본값(뉴스 60점, 공시 중립)을 적용합니다.")

    value_list = []
    momentum_list = []
    dividend_list = []

    for r in results:
        code = r["code"]
        ae = ai_evals.get(code, {
            "news_sentiment_score": 60,
            "disclosure_sentiment": "중립/없음",
            "one_liner": generate_fallback_oneliner(r)
        })

        # 정규화 항목 계산
        roe_score = min(max(r["roe"], 0) * 2.0, 100.0)
        price_mom_score = r["price_position_52w"]

        # 수급 점수 계산 (흐름 기반: 5일 가중합이 양수이거나 최신일 순매수가 양수인 경우 매수 흐름으로 판정)
        f_weighted = r.get("foreign_5d_weighted", 0.0)
        i_weighted = r.get("inst_5d_weighted", 0.0)
        f_today = r.get("foreign_today_net", 0)
        i_today = r.get("inst_today_net", 0)

        f_flow = (f_weighted > 0) or (f_today > 0)
        i_flow = (i_weighted > 0) or (i_today > 0)

        if f_flow and i_flow:
            supply_score = 100.0
            supply_text = "외인+/기관+ (흐름)"
        elif f_flow and not i_flow:
            supply_score = 70.0
            supply_text = "외인+/기관- (흐름)"
        elif not f_flow and i_flow:
            supply_score = 40.0
            supply_text = "외인-/기관+ (흐름)"
        else:
            supply_score = 10.0
            supply_text = "외인-/기관- (흐름)"

        news_score = ae.get("news_sentiment_score", 60)

        # 공시 모멘텀 가감점 및 점수
        disc_sent = ae.get("disclosure_sentiment", "중립/없음")
        if disc_sent == "호재":
            value_disc_adj = 5.0
            mom_disc_score = 100.0
        elif disc_sent == "악재":
            value_disc_adj = -5.0
            mom_disc_score = 0.0
        else:
            value_disc_adj = 0.0
            mom_disc_score = 50.0

        # A. Value 스코어 계산 (배당 제외, 정의서 공식 준수)
        val_score = (roe_score * 0.50) + (supply_score * 0.30) + (news_score * 0.20) + value_disc_adj
        if r.get("is_sector_leader", False):
            # 동일 업종 내에서 실시간 시가총액 기준으로 1위인 종목은 +20점, 2~3위는 +15점 가산
            same_sector_caps = [x.get('market_cap', 0.0) for x in results if x['sector'] == r['sector']]
            same_sector_caps.sort(reverse=True)
            try:
                rank_in_pool = same_sector_caps.index(r.get('market_cap', 0.0)) + 1
            except ValueError:
                rank_in_pool = 999
            
            if rank_in_pool == 1:
                val_score += 20.0
            else:
                val_score += 15.0
        val_score = round(min(val_score, 100.0), 2)

        # B. Momentum 스코어 계산
        mom_score = (price_mom_score * 0.30) + (supply_score * 0.30) + (news_score * 0.25) + (mom_disc_score * 0.10) + (roe_score * 0.05)
        mom_score = round(mom_score, 2)

        # C. Dividend 스코어 계산 (배당수익률 반영)
        div_yield = r.get("dividend_yield", 0.0)
        div_yield_score = min(div_yield * 15.0, 100.0)
        div_score = (div_yield_score * 0.50) + (roe_score * 0.20) + (supply_score * 0.20) + (news_score * 0.10) + value_disc_adj
        div_score = round(div_score, 2)

        reason = f"[{r['sector']}] 뉴스:{news_score}점 | ROE {r['roe']:.1f}% | 수급 {supply_text} | 상승여력 {r['upside']}%"
        if r.get("is_sector_leader", False):
            reason += " | [섹터대장주]"

        record_base = {
            "code": r["code"],
            "name": r["name"],
            "current_price": r["current_price"],
            "target_price": r["target_price"],
            "upside": r["upside"],
            "roe": r["roe"],
            "debt": r["debt"],
            "pbr": r["pbr"],
            "market_cap": r["market_cap"],
            "one_liner": ae.get("one_liner", generate_fallback_oneliner(r)),
            "reason": reason,
            "news_summary": json.dumps(_enrich_items(r.get("news", []), ae.get("news_evals", []), key="title"), ensure_ascii=False),
            "disc_json": json.dumps(_enrich_items(r.get("disclosures", []), ae.get("disc_evals", []), key="report_nm"), ensure_ascii=False),
            "data_date": r.get("data_date"),
            "source_file": r.get("source_file"),
            "dividend_yield": r.get("dividend_yield", 0.0)
        }

        is_est = r.get("is_estimated_tp", False)
        est_tag = "[추정목표가] " if is_est else ""

        # Value: 추정목표가 종목은 Upside 허들 강화 (5% → 10%)
        value_upside_min = 10.0 if is_est else 5.0
        if r["upside"] >= value_upside_min and 0 < r["pbr"] <= 12.0 and r["market_cap"] >= 500000000000.0:
            rec_val = record_base.copy()
            rec_val["score"] = val_score
            rec_val["rec_type"] = "value"
            rec_val["reason"] = est_tag + rec_val["reason"]
            value_list.append(rec_val)

        # Momentum: 추정목표가 종목은 Upside 허들 강화 (15% → 20%)
        momentum_upside_min = 20.0 if is_est else 15.0
        is_downtrend = (r["ma5_diff"] <= 0 or r["ma20_diff"] <= 0)
        if r["upside"] >= momentum_upside_min and not is_downtrend:
            rec_mom = record_base.copy()
            rec_mom["score"] = mom_score
            rec_mom["rec_type"] = "momentum"
            rec_mom["reason"] = est_tag + rec_mom["reason"]
            momentum_list.append(rec_mom)

        # Dividend: 배당수익률 3% 이상, 부채비율 150% 이하 (금융업 예외)
        _is_fin = any(k in r.get("sector", "") for k in ['은행', '증권', '보험', '손해보험', '생명보험'])
        _debt_ok = _is_fin or r["debt"] <= 150.0
        if r.get("dividend_yield", 0.0) >= 3.0 and _debt_ok:
            rec_div = record_base.copy()
            rec_div["score"] = div_score
            rec_div["rec_type"] = "dividend"
            rec_div["reason"] = est_tag + rec_div["reason"]
            dividend_list.append(rec_div)

    # Value 추천 리스트는 PBR이 낮을수록 저평가로 우선 선정하므로, 동일 점수 내 PBR 오름차순 정렬 적용
    value_list.sort(key=lambda x: (x["score"], -x["pbr"]), reverse=True)
    momentum_list.sort(key=lambda x: x["score"], reverse=True)
    dividend_list.sort(key=lambda x: (x["score"], x["dividend_yield"]), reverse=True)

    # 바이오·제약·헬스케어 업종 제외 — 1차 차단은 pool_collect.py 필터 5번에서 수행.
    # 이 블록은 Pool 외부 데이터 유입 등 예외 상황에 대한 안전망(safety net)임.
    def _is_excluded(rec):
        reason = rec.get("reason", "")
        return any(k in reason for k in EXCLUDED_SECTORS)

    value_list_filtered    = [r for r in value_list    if not _is_excluded(r)]
    momentum_list_filtered = [r for r in momentum_list if not _is_excluded(r)]
    dividend_list_filtered = [r for r in dividend_list if not _is_excluded(r)]

    excluded_v = [r["name"] for r in value_list    if _is_excluded(r)]
    excluded_m = [r["name"] for r in momentum_list if _is_excluded(r)]
    if excluded_v:
        print(f"  [안전망-바이오제외-Value] {', '.join(excluded_v[:5])}")
    if excluded_m:
        print(f"  [안전망-바이오제외-Momentum] {', '.join(excluded_m[:5])}")

    top_value    = value_list_filtered[:10]
    top_momentum = momentum_list_filtered[:10]
    top_dividend = dividend_list_filtered[:10]

    # JSON 저장
    with open(COWORK_DIR / "value_recommendations.json", "w", encoding="utf-8") as f:
        json.dump(top_value, f, ensure_ascii=False, indent=2)

    with open(COWORK_DIR / "momentum_recommendations.json", "w", encoding="utf-8") as f:
        json.dump(top_momentum, f, ensure_ascii=False, indent=2)

    with open(COWORK_DIR / "dividend_recommendations.json", "w", encoding="utf-8") as f:
        json.dump(top_dividend, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print("최종 추천 리스트 산출 완료!")
    print(f"  - Value: {len(top_value)}개 종목 value_recommendations.json 저장 완료")
    print(f"  - Momentum: {len(top_momentum)}개 종목 momentum_recommendations.json 저장 완료")
    print(f"  - Dividend: {len(top_dividend)}개 종목 dividend_recommendations.json 저장 완료")
    print(f"{'='*60}\n")
