# -*- coding: utf-8 -*-
"""
IT 감사팀 투자 후보군(pool) 수집 및 구성 자동화 스크립트
기준 문서: cowork/Report/audit_logic.md

역할:
    1. 구글 드라이브(Stock_Analysis_Results 폴더)에서 가장 최근 생성된 재무 엑셀 파일을 다운로드합니다.
    2. 재무 필터링 규칙을 적용하여 대상 종목을 선별합니다.
    3. 정량적 스코어링 공식에 따라 pool_score를 계산합니다.
    4. 상위 100개 종목을 선정하여 Neon PostgreSQL의 stock_pool 테이블에 적재합니다.

사용법:
    python cowork/pool_collect.py
"""
import io
import os
import sys
import json
import psycopg2
import psycopg2.extras
import pandas as pd
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Windows 콘솔 UTF-8 설정
if os.name == 'nt':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# 경로 설정
COWORK_DIR = Path(__file__).resolve().parent
TRADE_DIR = COWORK_DIR.parent / 'trade'
sys.path.append(str(TRADE_DIR))

# 구글 드라이브 모듈 임포트
try:
    from drive_sync import list_files_in_folder, read_sheet_as_df
except ImportError:
    print("[오류] trade/drive_sync.py 모듈을 찾을 수 없습니다. 경로 설정을 확인하세요.")
    sys.exit(1)

# 환경 변수 로드
load_dotenv(TRADE_DIR / '.env')
DATABASE_URL = os.getenv('DATABASE_URL')

def calculate_pool_score(row):
    """
    pool_score 계산식:
    pool_score = (ROE * 0.35) + (부채건전성 * 0.25) + (목표주가 보유 * 0.2) + (업종 가중치 * 0.1) + (섹터 대장주 * 0.1)
    각 항목은 0~100점 범위로 정규화
    """
    roe = float(row.get('ROE', 0))
    debt = float(row.get('부채비율', 0))
    target_price = float(row.get('목표주가', 0))
    sector = str(row.get('업종', ''))
    sector_leader_score = float(row.get('sector_leader_score', 0))

    # 1. ROE 점수 (50% 이상 시 100점 만점)
    roe_score = min(max(roe, 0) * 2.0, 100.0)

    # 2. 부채건전성 점수 (금융업: 70점 고정, 고부채 업종: 0~300% 기준 정규화, 일반 업종: 0~150% 기준 정규화)
    is_financial = any(s in sector for s in ['은행', '증권', '보험', '손해보험', '생명보험'])
    is_high_leverage = any(s in sector for s in ['건설', '조선', '해운', '항공', '전력', '가스', '에너지', '유틸리티', '운송'])

    if is_financial:
        debt_score = 70.0
    elif is_high_leverage:
        debt_score = max(0.0, 100.0 - (debt / 3.0))  # 300% 초과 시 0점
    else:
        debt_score = max(0.0, 100.0 - (debt / 1.5))  # 150% 초과 시 0점

    # 3. 목표주가 보유 점수 (보유하고 있으므로 기본 100점, 미보유는 이미 필터링됨)
    target_score = 100.0 if target_price > 0 else 0.0

    # 4. 업종 가중치 (기본 80점, 반도체/조선/화장품 등 주력업종 가점 100점)
    strategic_sectors = ['반도체', '조선', '화장품', 'IT', '전기', '화학', '제약']
    is_strategic = any(s in sector for s in strategic_sectors)
    sector_score = 100.0 if is_strategic else 80.0

    # 종합 스코어 계산 (섹터 대장주 10% 반영)
    final_score = (roe_score * 0.35) + (debt_score * 0.25) + (target_score * 0.2) + (sector_score * 0.1) + (sector_leader_score * 0.1)
    return round(final_score, 2)

def main():
    if not DATABASE_URL:
        print("[오류] DATABASE_URL 환경 변수가 .env에 존재하지 않습니다.")
        sys.exit(1)

    print("Step 1. 구글 드라이브에서 최신 재무 데이터 파일 조회 중...")
    def load_local_fallback():
        """cowork/Report/ → trade/result.xlsx 순으로 로컬 파일 탐색."""
        report_dir = COWORK_DIR / 'Report'
        local_xlsx = [f for f in report_dir.glob('*.xlsx')] if report_dir.exists() else []
        if local_xlsx:
            latest = max(local_xlsx, key=lambda f: f.stat().st_mtime)
            print(f"로컬 폴백 작동: {latest} 사용")
            return latest.read_bytes()
        fallback = TRADE_DIR / 'result.xlsx'
        if fallback.exists():
            print(f"로컬 폴백 작동: {fallback} 사용")
            return fallback.read_bytes()
        print("[오류] 로컬 파일도 존재하지 않습니다.")
        sys.exit(1)

    import re
    def extract_timestamp(file_obj):
        name = file_obj.get('name', '')
        m = re.search(r'(\d{8}_\d{6})', name)
        if m: return m.group(1)
        m = re.search(r'(\d{8})', name)
        if m: return m.group(1) + "_000000"
        return "00000000_000000"

    df = None
    try:
        files = list_files_in_folder("Stock_Analysis_Results")
        sheets = [f for f in files if f['mimeType'] == 'application/vnd.google-apps.spreadsheet' or f['name'].endswith('.xlsx')]
        if sheets:
            sheets.sort(key=extract_timestamp, reverse=True)
            latest = sheets[0]
            print(f"최신 파일 발견: {latest['name']}")
            print("Step 2. Google Sheets 직접 읽기 중...")
            df = read_sheet_as_df(latest['id'])
        else:
            print("[경고] 구글 드라이브에 파일 없음. 로컬 폴백 시도...")
    except Exception as e:
        print(f"[경고] 구글 드라이브 접근 실패: {e}. 로컬 폴백 시도...")

    if df is None:
        content = load_local_fallback()
        df = pd.read_excel(io.BytesIO(content))

    print("Step 3. 데이터 로드 및 1차 필터링 시작...")
    total_raw = len(df)
    print(f"로드된 전체 로우 수: {total_raw}개")

    # 필수 컬럼 존재 확인 및 이름 표준화
    col_mapping = {
        '종목코드': 'code',
        '종목명': 'name',
        '업종': 'sector',
        'ROE': 'roe',
        '부채비율': 'debt_ratio',
        '목표주가': 'target_price',
        'PBR': 'pbr',
        'PER': 'per',
        '영업이익률': 'operating_margin',
        '외국인순매수': 'foreign_net_buy',
        '기관순매수': 'inst_net_buy',
        '시가총액': 'market_cap',
    }

    # 현재 엑셀 컬럼이 변형되었을 경우를 대비해 매핑 유효성 검사
    for k in ['종목코드', '종목명', 'ROE', '부채비율', '목표주가']:
        if k not in df.columns:
            # 깨진 문자 및 부분 문자 매칭 시도
            found_col = None
            for c in df.columns:
                if k[:2] in str(c) or str(c)[:2] in k:
                    found_col = c
                    break
            if found_col:
                df.rename(columns={found_col: k}, inplace=True)
            else:
                print(f"[오류] 필수 컬럼 '{k}'을 엑셀 파일에서 찾을 수 없습니다.")
                sys.exit(1)

    # 필터링 적용
    # 1) ETF/ETN 제외 (종목명 기준 필터)
    exclude_keywords = ['KODEX', 'TIGER', 'ACE', 'SOL', 'ARIRANG', 'KBSTAR', 'HANARO', 'KOSEF', 'TREX', '히어로즈', '마이티', 'UNICORN']
    df = df[~df['종목명'].str.contains('|'.join(exclude_keywords), na=False)]

    # 2) 우선주 제외
    df = df[~df['종목명'].str.endswith(('우', '우B', '우C', '우(전환)', '3우B'), na=False)]

    # 3) ROE 10% 미만 제외
    df['ROE'] = pd.to_numeric(df['ROE'], errors='coerce').fillna(0)
    df = df[df['ROE'] >= 10.0]

    # 4) 부채비율 제한 적용 (산업군별 차등 적용)
    df['부채비율'] = pd.to_numeric(df['부채비율'], errors='coerce').fillna(0)
    df['업종'] = df['업종'].astype(str).fillna('')
    is_financial = df['업종'].str.contains('은행|증권|보험|손해보험|생명보험', na=False)
    is_high_leverage = df['업종'].str.contains('건설|조선|해운|항공|전력|가스|에너지|유틸리티|운송', na=False)
    
    df = df[
        is_financial | 
        (is_high_leverage & (df['부채비율'] <= 300.0)) | 
        (~is_financial & ~is_high_leverage & (df['부채비율'] <= 150.0))
    ]

    # 5) 목표주가 미보유 제외
    df['목표주가'] = pd.to_numeric(df['목표주가'], errors='coerce').fillna(0)
    df = df[df['목표주가'] > 0]

    print(f"기본 재무 필터 통과 종목: {len(df)}개")

    if len(df) == 0:
        print("[경고] 필터를 통과한 종목이 하나도 없습니다. 수집을 중단합니다.")
        sys.exit(0)

    # 섹터별 대장주 판별 (시가총액 기준 섹터 내 순위)
    if '시가총액' in df.columns:
        df['시가총액'] = pd.to_numeric(df['시가총액'], errors='coerce').fillna(0)
    else:
        df['시가총액'] = 0

    # 시가총액이 0인 종목들 중 주요 대형주들이 누락되는 것을 막기 위해 네이버 금융 실시간 보완
    missing_cap_mask = df['시가총액'] <= 0
    missing_count = missing_cap_mask.sum()
    if missing_count > 0:
        print(f"  [안내] 시가총액이 0으로 누락된 {missing_count}개 종목에 대해 네이버 금융 실시간 보정 시도...")
        import requests
        from bs4 import BeautifulSoup
        import re

        def get_market_cap_live(code):
            code_str = str(code).zfill(6)
            url = f"https://finance.naver.com/item/main.naver?code={code_str}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            try:
                res = requests.get(url, headers=headers, timeout=3)
                soup = BeautifulSoup(res.text, 'html.parser')
                for table in soup.find_all('table'):
                    summary = table.get('summary', '')
                    if '시가총액 정보' in summary:
                        td = table.find('td')
                        if td:
                            td_text = td.get_text(strip=True).replace(',', '')
                            val = 0
                            m_cho = re.search(r'(\d+)조', td_text)
                            m_uk = re.search(r'(\d+)억', td_text)
                            if m_cho:
                                val += int(m_cho.group(1)) * 1000000000000
                            if m_uk:
                                val += int(m_uk.group(1)) * 100000000
                            if not m_cho and not m_uk:
                                nums = re.findall(r'\d+', td_text)
                                if nums:
                                    val = int(nums[0])
                            return float(val)
            except Exception:
                pass
            return 0.0

        # 시가총액 0인 종목들만 루프 돌며 데이터 수집
        corrected = 0
        for idx, row in df[missing_cap_mask].iterrows():
            live_cap = get_market_cap_live(row['종목코드'])
            if live_cap > 0:
                df.at[idx, '시가총액'] = live_cap
                corrected += 1
        print(f"  [완료] {corrected}개 종목의 시가총액 데이터 보정 성공!")

    df['sector_cap_rank'] = df.groupby('업종')['시가총액'].transform(
        lambda x: x.where(x > 0).rank(method='first', ascending=False)
    ).fillna(999)
    df['is_sector_leader'] = df['sector_cap_rank'] <= 3
    df['sector_leader_score'] = df['sector_cap_rank'].apply(
        lambda r: 100.0 if r == 1 else (60.0 if r <= 3 else 0.0)
    )
    leader_count = df['is_sector_leader'].sum()
    print(f"섹터 대장주 판별 완료: {leader_count}개 종목 (시총 1위={df[df['sector_cap_rank']==1].shape[0]}개, 2~3위={df[df['sector_cap_rank'].between(2,3)].shape[0]}개)")

    # pool_score 계산 및 추가
    df['pool_score'] = df.apply(calculate_pool_score, axis=1)

    # score 기준 내림차순 정렬 및 상위 100개 선정
    df_sorted = df.sort_values(by='pool_score', ascending=False)
    df_top100 = df_sorted.head(100)
    
    # 100개에 포함되지 않은 대장주(is_sector_leader == True) 찾기
    df_remaining = df_sorted.iloc[100:]
    df_missing_leaders = df_remaining[df_remaining['is_sector_leader']]
    
    # 100개 풀과 누락 대장주 병합
    df_pool = pd.concat([df_top100, df_missing_leaders], ignore_index=True)
    
    print(f"기본 스코어 상위 100개 선정 완료")
    print(f"누락된 섹터 대장주 {len(df_missing_leaders)}개 추가 편입 완료")
    print(f"최종 선정된 Pool 종목 수: {len(df_pool)}개")

    # DB 적재 형식 구성
    records = []
    for _, row in df_pool.iterrows():
        records.append({
            'code': str(row['종목코드']).zfill(6),
            'name': str(row['종목명']),
            'sector': str(row.get('업종', '기타')),
            'roe': float(row.get('ROE', 0)),
            'pbr': float(row.get('PBR', 0)) if pd.notna(row.get('PBR')) else 0.0,
            'per': float(row.get('PER', 0)) if pd.notna(row.get('PER')) else 0.0,
            'debt_ratio': float(row.get('부채비율', 0)),
            'operating_margin': float(row.get('영업이익률', 0)) if pd.notna(row.get('영업이익률')) else 0.0,
            'target_price': float(row.get('목표주가', 0)),
            'foreign_net_buy': float(row.get('외국인순매수', 0)) if pd.notna(row.get('외국인순매수')) else 0.0,
            'inst_net_buy': float(row.get('기관순매수', 0)) if pd.notna(row.get('기관순매수')) else 0.0,
            'pool_score': float(row['pool_score']),
            'market_cap': float(row.get('시가총액', 0)) if pd.notna(row.get('시가총액')) else 0.0,
            'is_sector_leader': bool(row.get('is_sector_leader', False)),
        })

    # Neon PostgreSQL 적재
    print("Step 4. Neon PostgreSQL 적재 중...")
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    data_date = datetime.now().strftime('%Y-%m-%d')

    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)
        cur = conn.cursor()

        # 신규 컬럼 마이그레이션 (없으면 추가)
        cur.execute("ALTER TABLE stock_pool ADD COLUMN IF NOT EXISTS market_cap FLOAT DEFAULT 0")
        cur.execute("ALTER TABLE stock_pool ADD COLUMN IF NOT EXISTS is_sector_leader BOOLEAN DEFAULT FALSE")
        conn.commit()

        # 기존 테이블 비우기
        cur.execute("TRUNCATE TABLE stock_pool")

        for r in records:
            cur.execute("""
                INSERT INTO stock_pool
                    (code, name, sector, roe, pbr, per, debt_ratio, operating_margin,
                     target_price, foreign_net_buy, inst_net_buy, pool_score,
                     market_cap, is_sector_leader, data_date, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (code) DO UPDATE SET
                    name=EXCLUDED.name, sector=EXCLUDED.sector,
                    roe=EXCLUDED.roe, pbr=EXCLUDED.pbr, per=EXCLUDED.per,
                    debt_ratio=EXCLUDED.debt_ratio, operating_margin=EXCLUDED.operating_margin,
                    target_price=EXCLUDED.target_price,
                    foreign_net_buy=EXCLUDED.foreign_net_buy, inst_net_buy=EXCLUDED.inst_net_buy,
                    pool_score=EXCLUDED.pool_score,
                    market_cap=EXCLUDED.market_cap, is_sector_leader=EXCLUDED.is_sector_leader,
                    data_date=EXCLUDED.data_date, updated_at=EXCLUDED.updated_at
            """, (
                r['code'], r['name'], r['sector'],
                r['roe'], r['pbr'], r['per'],
                r['debt_ratio'], r['operating_margin'],
                r['target_price'],
                r['foreign_net_buy'], r['inst_net_buy'],
                r['pool_score'],
                r['market_cap'], r['is_sector_leader'],
                data_date, now_str
            ))

        conn.commit()
        conn.close()
        print(f"[완료] {len(records)}개 종목 Neon DB stock_pool 테이블 적재 성공! (data_date={data_date})")
    except Exception as e:
        print(f"[오류] Neon DB 적재 실패: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
