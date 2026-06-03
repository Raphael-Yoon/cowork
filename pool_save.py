# -*- coding: utf-8 -*-
"""
IT 감사팀 투자 후보군(pool) Neon DB 저장 유틸리티
기준 문서: cowork/Report/audit_logic.md

AI가 결정한 100개 pool을 Neon PostgreSQL stock_pool 테이블에 저장.

사용법:
    python cowork/pool_save.py pool.json
    python cowork/pool_save.py pool.json --date 2026-06-03
"""
import argparse
import json
import os
import sys
import psycopg2
import psycopg2.extras
from datetime import datetime
from pathlib import Path

# trade/.env 로드
env_path = Path(__file__).resolve().parents[1] / 'trade' / '.env'
from dotenv import load_dotenv
load_dotenv(env_path)

DATABASE_URL = os.getenv('DATABASE_URL')


def save(records: list[dict], data_date: str):
    """
    records 형식:
    [
        {
            "code":             "005930",
            "name":             "삼성전자",
            "sector":           "반도체와반도체장비",
            "roe":              63.0,
            "pbr":              1.2,
            "per":              10.5,
            "debt_ratio":       29.9,
            "operating_margin": 25.3,
            "target_price":     310800,
            "foreign_net_buy":  1234567890,
            "inst_net_buy":     987654321,
            "pool_score":       85.5
        },
        ...
    ]
    """
    if not records:
        print("[오류] 저장할 데이터가 없습니다.")
        return

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)
    cur = conn.cursor()

    # 기존 데이터 전체 교체
    cur.execute("TRUNCATE TABLE stock_pool")

    for r in records:
        cur.execute("""
            INSERT INTO stock_pool
                (code, name, sector, roe, pbr, per, debt_ratio, operating_margin,
                 target_price, foreign_net_buy, inst_net_buy, pool_score, data_date, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (code) DO UPDATE SET
                name=EXCLUDED.name, sector=EXCLUDED.sector,
                roe=EXCLUDED.roe, pbr=EXCLUDED.pbr, per=EXCLUDED.per,
                debt_ratio=EXCLUDED.debt_ratio, operating_margin=EXCLUDED.operating_margin,
                target_price=EXCLUDED.target_price,
                foreign_net_buy=EXCLUDED.foreign_net_buy, inst_net_buy=EXCLUDED.inst_net_buy,
                pool_score=EXCLUDED.pool_score, data_date=EXCLUDED.data_date,
                updated_at=EXCLUDED.updated_at
        """, (
            r['code'], r['name'], r.get('sector', ''),
            float(r.get('roe', 0)), float(r.get('pbr', 0)), float(r.get('per', 0)),
            float(r.get('debt_ratio', 0)), float(r.get('operating_margin', 0)),
            float(r.get('target_price', 0)),
            float(r.get('foreign_net_buy', 0)), float(r.get('inst_net_buy', 0)),
            float(r.get('pool_score', 0)),
            data_date, now_str
        ))

    conn.commit()
    conn.close()

    print(f"[완료] {len(records)}개 종목 stock_pool 저장 완료 (data_date={data_date})")
    for r in records[:5]:
        print(f"   [{r['code']}] {r['name']}  pool_score={r.get('pool_score', 0):.1f}")
    if len(records) > 5:
        print(f"   ... 외 {len(records) - 5}개")


def main():
    parser = argparse.ArgumentParser(description='IT 감사팀 pool Neon DB 저장')
    parser.add_argument('json_file', help='pool JSON 파일 경로')
    parser.add_argument('--date', default=datetime.now().strftime('%Y-%m-%d'),
                        help='기준일 (기본값: 오늘, 형식: YYYY-MM-DD)')
    args = parser.parse_args()

    json_path = Path(args.json_file)
    if not json_path.exists():
        print(f"[오류] 파일을 찾을 수 없습니다: {json_path}")
        sys.exit(1)

    with open(json_path, encoding='utf-8') as f:
        records = json.load(f)

    if isinstance(records, dict) and 'stocks' in records:
        records = records['stocks']

    save(records, args.date)


if __name__ == '__main__':
    main()
