# -*- coding: utf-8 -*-
"""
IT 감사팀 Top 10 추천 종목 저장 유틸리티
기준 문서: cowork/Report/audit_logic.md

AI가 분석·결정한 추천 종목을 recommendations.json에 저장하는 역할만 담당.
(DB 저장 없음 — Top 10은 세션성 데이터로 JSON 파일로만 관리)

사용법:
    python cowork/audit_save.py recommendations.json
    python cowork/audit_save.py recommendations.json --date 2026-05-10
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

OUTPUT_PATH = Path(__file__).resolve().parent / 'recommendations.json'


def save(records: list[dict], data_date: str):
    """
    records 형식:
    [
        {
            "code":          "005930",
            "name":          "삼성전자",
            "current_price": 268500,
            "target_price":  310800,
            "upside":        15.8,
            "roe":           63.0,
            "debt":          29.9,
            "score":         78.5,
            "reason":        "[반도체] 뉴스:실적·최고 | ROE 63.0% | 수급 외인+/기관-",
            "news_summary":  "..."
        },
        ...
    ]
    """
    if not records:
        print("[오류] 저장할 데이터가 없습니다.")
        return

    output = {
        "data_date": data_date,
        "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "stocks": records
    }

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[완료] {len(records)}개 종목 저장 완료 → {OUTPUT_PATH}")
    for r in records:
        print(f"   [{r['code']}] {r['name']}  상승여력 {r['upside']:.1f}%")


def main():
    parser = argparse.ArgumentParser(description='IT 감사팀 Top 10 추천 종목 저장')
    parser.add_argument('json_file', help='추천 종목 JSON 파일 경로')
    parser.add_argument('--date', default=datetime.now().strftime('%Y-%m-%d'),
                        help='기준일 (기본값: 오늘, 형식: YYYY-MM-DD)')
    args = parser.parse_args()

    json_path = Path(args.json_file)
    if not json_path.exists():
        print(f"[오류] 파일을 찾을 수 없습니다: {json_path}")
        return

    with open(json_path, encoding='utf-8') as f:
        records = json.load(f)

    if isinstance(records, dict) and 'stocks' in records:
        records = records['stocks']

    save(records, args.date)


if __name__ == '__main__':
    main()
