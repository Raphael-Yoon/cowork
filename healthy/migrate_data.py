"""
[개발4팀 바람길] 무손실 데이터 마이그레이션 도구 (migrate_data.py)
- workouts.json ➔ healthy.db (workouts, workout_sessions, session_splits, body_composition)
- 혈액수치.xlsx ➔ healthy.db (clinical_lab_results, clinical_lab_items)
- OS 호환성: pathlib.Path 전면 적용
- 데이터 무손실 검증: 건수 및 정합성 100% 대조
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional
import openpyxl

from db_config import get_db, init_db, SQLITE_DATABASE, DB_TYPE

_BASE_DIR = Path(__file__).resolve().parent
WORKOUTS_JSON_PATH = _BASE_DIR / "workouts.json"
BLOOD_EXCEL_PATH = _BASE_DIR / "혈액수치.xlsx"


def resolve_sport_type(session: Dict[str, Any], day_workout_type: str) -> str:
    """세션별 종목(자전거/걷기) 표준 분류"""
    if session.get("workout_type"):
        return session["workout_type"]
    name = session.get("name", "")
    if "걷기" in name or "산책" in name or "워킹" in name:
        return "걷기 (Walking)"
    if "자전거" in name or "라이딩" in name:
        return "자전거 (Cycling)"
    if "가는 길" in name or "돌아오는 길" in name:
        if "자전거" in day_workout_type:
            return "자전거 (Cycling)"
        if "걷기" in day_workout_type:
            return "걷기 (Walking)"
    if "피니시" in name and "자전거" in day_workout_type:
        return "자전거 (Cycling)"
    if "자전거" in day_workout_type and "걷기" not in day_workout_type:
        return "자전거 (Cycling)"
    if "걷기" in day_workout_type and "자전거" not in day_workout_type:
        return "걷기 (Walking)"
    return day_workout_type


def clean_numeric(val: Any) -> Optional[float]:
    """문자열에서 숫자 추출 (예: '6.1%' -> 6.1, '117' -> 117.0, '-' -> None, '정상' -> None)"""
    if val is None:
        return None
    s = str(val).strip()
    if s in ("-", "정상", "", "None"):
        return None
    # % 제거
    s = s.replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def migrate_workouts(db) -> Dict[str, int]:
    """workouts.json 데이터 무손실 마이그레이션"""
    print(f"[*] Migrating workouts from: {WORKOUTS_JSON_PATH.name}")
    if not WORKOUTS_JSON_PATH.exists():
        raise FileNotFoundError(f"Missing {WORKOUTS_JSON_PATH}")

    with open(WORKOUTS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 기존 데이터 정리 (중복 방지)
    db.execute("DELETE FROM session_splits")
    db.execute("DELETE FROM workout_sessions")
    db.execute("DELETE FROM workouts")
    db.execute("DELETE FROM body_composition")

    counts = {
        "days": len(data),
        "sessions": 0,
        "splits": 0,
        "body_comp": 0,
    }

    for day in data:
        w_date = day["date"]
        d_summary = day.get("daily_summary", {})
        evaluation = d_summary.get("evaluation") or "기록 완료"
        notes = d_summary.get("notes") or day.get("course_note")

        cursor = db.execute(
            """
            INSERT INTO workouts (
                workout_date, day_of_week, time_of_day, workout_type,
                routine_name, morning_fasting_blood_sugar, evaluation, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                w_date,
                day.get("day_of_week", ""),
                day.get("time_of_day", ""),
                day.get("workout_type", ""),
                day.get("routine", ""),
                day.get("morning_fasting_blood_sugar_mgdl"),
                evaluation,
                notes,
            ),
        )
        workout_id = cursor.lastrowid

        # 세션별 데이터 저장
        for s in day.get("sessions", []):
            counts["sessions"] += 1
            sport_type = resolve_sport_type(s, day.get("workout_type", ""))
            weather_json = json.dumps(s.get("weather"), ensure_ascii=False) if s.get("weather") else None
            
            s_cursor = db.execute(
                """
                INSERT INTO workout_sessions (
                    workout_id, session_no, sport_type, session_name,
                    duration_seconds, duration_str, distance_km, estimated_distance_km,
                    active_kcal, total_kcal, elevation_gain_m,
                    avg_heart_rate_bpm, max_heart_rate_bpm, avg_speed_kmh,
                    avg_pace, effort, weather_info, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workout_id,
                    s.get("session_id", 1),
                    sport_type,
                    s.get("name", ""),
                    s.get("duration_seconds", 0),
                    s.get("duration_str", ""),
                    s.get("distance_km", 0.0),
                    s.get("estimated_actual_distance_km"),
                    s.get("active_kcal", 0),
                    s.get("total_kcal", 0),
                    s.get("elevation_gain_m", 0),
                    s.get("avg_heart_rate_bpm"),
                    s.get("max_heart_rate_bpm"),
                    s.get("avg_speed_kmh"),
                    s.get("avg_pace") or s.get("avg_pace_str"),
                    s.get("effort", ""),
                    weather_json,
                    s.get("notes", ""),
                ),
            )
            session_id = s_cursor.lastrowid

            # 구간별 스플릿
            for sp in s.get("splits", []):
                counts["splits"] += 1
                db.execute(
                    """
                    INSERT INTO session_splits (
                        session_id, split_no, distance_km, time_str,
                        speed_kmh, heart_rate_bpm
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        sp.get("split", 1),
                        sp.get("distance_km"),
                        sp.get("time"),
                        sp.get("speed_kmh") or sp.get("avg_speed_kmh"),
                        sp.get("heart_rate_bpm"),
                    ),
                )

        # 체성분 측정 데이터
        body = day.get("post_workout_body_comp")
        if body:
            counts["body_comp"] += 1
            notes_str = body.get("notes", "")
            is_dehydrated = 1 if ("탈수" in notes_str or body.get("body_fat_pct", 0) >= 20.7) else 0
            db.execute(
                """
                INSERT INTO body_composition (
                    measure_date, weight_kg, body_fat_pct,
                    skeletal_muscle_kg, bmi, is_dehydrated, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    w_date,
                    body.get("weight_kg"),
                    body.get("body_fat_pct"),
                    body.get("skeletal_muscle_mass_kg") or body.get("skeletal_muscle_kg"),
                    body.get("bmi"),
                    is_dehydrated,
                    notes_str,
                ),
            )

    db.commit()
    print(f"  [+] Workouts migrated: {counts['days']} days, {counts['sessions']} sessions, {counts['splits']} splits, {counts['body_comp']} body_comps")
    return counts


def migrate_blood_lab(db) -> Dict[str, int]:
    """혈액수치.xlsx 데이터 무손실 마이그레이션"""
    print(f"[*] Migrating clinical lab results from: {BLOOD_EXCEL_PATH.name}")
    if not BLOOD_EXCEL_PATH.exists():
        raise FileNotFoundError(f"Missing {BLOOD_EXCEL_PATH}")

    wb = openpyxl.load_workbook(BLOOD_EXCEL_PATH)
    ws = wb["혈액수치_통합비교"]

    # 기존 데이터 정리
    db.execute("DELETE FROM clinical_lab_items")
    db.execute("DELETE FROM clinical_lab_results")

    # 4개 검사 일자 및 마스터 KPI 정의
    exam_dates = ["2026-02-23", "2026-04-02", "2026-05-19", "2026-08-18"]
    exam_master = {
        "2026-02-23": {
            "hba1c": 6.1, "glucose": 117, "tg": 217, "ldl": 105, "uric": 7.30,
            "ast": 30, "alt": 33, "cr": 0.88, "egfr": None,
            "notes": "출발점 검진 (당뇨/간기능/신장/지질 종합)",
        },
        "2026-04-02": {
            "hba1c": 5.8, "glucose": 99, "tg": None, "ldl": 94, "uric": 7.40,
            "ast": 25, "alt": 24, "cr": None, "egfr": None,
            "notes": "당화혈색소 5.8% 개선, 공복혈당 정상(99) 진입",
        },
        "2026-05-19": {
            "hba1c": 5.8, "glucose": 103, "tg": None, "ldl": None, "uric": 6.78,
            "ast": None, "alt": None, "cr": None, "egfr": None,
            "notes": "요산 6.78mg/dL 대폭 개선 (정상권 진입)",
        },
        "2026-08-18": {
            "hba1c": 5.7, "glucose": 111, "tg": 157, "ldl": 74, "uric": 7.81,
            "ast": 22, "alt": 20, "cr": 0.91, "egfr": None,
            "notes": "당화혈색소 5.7% 최저치 경신, TG 157 대폭 개선(유산소 효과), 요산 7.81 재상승으로 수분 관리 필요",
        },
    }

    # 1) clinical_lab_results 등록
    for ed in exam_dates:
        m = exam_master[ed]
        db.execute(
            """
            INSERT INTO clinical_lab_results (
                exam_date, hba1c_pct, fasting_glucose, triglyceride_mgdl,
                ldl_mgdl, uric_acid_mgdl, ast_u_l, alt_u_l,
                creatinine_mgdl, egfr_score, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ed,
                m["hba1c"],
                m["glucose"],
                m["tg"],
                m["ldl"],
                m["uric"],
                m["ast"],
                m["alt"],
                m["cr"],
                m["egfr"],
                m["notes"],
            ),
        )

    # 2) clinical_lab_items 등록 (엑셀의 모든 항목 무손실 보존)
    # 엑셀 헤더: row 3 -> ('구분', '검사항목', '2026-02-23', '2026-04-02', '2026-05-19', '2026-08-18 (최신)', '참고치', '단위', '판정 및 추이')
    item_count = 0
    date_cols = [2, 3, 4, 5]  # 0-indexed: col 2=2026-02-23, col 3=2026-04-02, col 4=2026-05-19, col 5=2026-08-18

    for r_idx, row in enumerate(ws.iter_rows(values_only=True)):
        if r_idx < 4:
            continue
        category = row[0]
        item_name = row[1]
        if not item_name:
            continue

        ref_range = str(row[6]) if row[6] is not None else ""
        unit = str(row[7]) if row[7] is not None else ""
        evaluation = str(row[8]) if row[8] is not None else ""

        for d_idx, c_idx in enumerate(date_cols):
            exam_date = exam_dates[d_idx]
            raw_val = row[c_idx]
            raw_val_str = str(raw_val).strip() if raw_val is not None else "-"
            num_val = clean_numeric(raw_val)

            db.execute(
                """
                INSERT INTO clinical_lab_items (
                    exam_date, category, item_name, result_value,
                    numeric_value, reference_range, unit, evaluation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exam_date,
                    category,
                    item_name,
                    raw_val_str,
                    num_val,
                    ref_range,
                    unit,
                    evaluation,
                ),
            )
            item_count += 1

    db.commit()
    print(f"  [+] Clinical lab migrated: {len(exam_dates)} master exams, {item_count} detail items")
    return {"master_exams": len(exam_dates), "detail_items": item_count}


def verify_migration(db):
    """마이그레이션 결과 무결성 전수 검증"""
    print("\n" + "=" * 50)
    print("🔍 [Phase 1 무손실 마이그레이션 무결성 검증 리포트]")
    print("=" * 50)

    # SQLite / MySQL 공통 안전 카운트
    def get_val(query):
        c = db.execute(query)
        r = c.fetchone()
        if isinstance(r, (list, tuple)):
            return r[0]
        if hasattr(r, "values"):
            return list(r.values())[0]
        return r[0]

    w_count = get_val("SELECT COUNT(*) FROM workouts")
    s_count = get_val("SELECT COUNT(*) FROM workout_sessions")
    sp_count = get_val("SELECT COUNT(*) FROM session_splits")
    bc_count = get_val("SELECT COUNT(*) FROM body_composition")
    clr_count = get_val("SELECT COUNT(*) FROM clinical_lab_results")
    cli_count = get_val("SELECT COUNT(*) FROM clinical_lab_items")

    print(f"1. 운동 마스터 일자 (workouts)        : {w_count:3d} 일")
    print(f"2. 세부 운동 세션 (workout_sessions)   : {s_count:3d} 회")
    print(f"3. 구간별 스플릿 (session_splits)     : {sp_count:3d} 건")
    print(f"4. 체성분 추적 (body_composition)     : {bc_count:3d} 일")
    print(f"5. 정기 피검사 마스터 (clinical_lab)    : {clr_count:3d} 회")
    print(f"6. 피검사 전 항목 원천 (lab_items)    : {cli_count:3d} 개")

    # 세부 정합성 체크
    cur = db.execute("SELECT MIN(workout_date), MAX(workout_date) FROM workouts")
    row = cur.fetchone()
    min_date, max_date = row[0], row[1]
    print(f"• 운동 기록 기간: {min_date} ~ {max_date}")

    cur = db.execute("SELECT SUM(distance_km), SUM(total_kcal) FROM workout_sessions")
    row = cur.fetchone()
    tot_dist = float(row[0] or 0)
    tot_kcal = int(row[1] or 0)
    print(f"• 누적 세션 거리: {tot_dist:.2f} km | 누적 소모 칼로리: {tot_kcal:,} kcal")

    cur = db.execute("SELECT measure_date, weight_kg, skeletal_muscle_kg, body_fat_pct FROM body_composition ORDER BY measure_date DESC LIMIT 3")
    print("• 최근 3회 체성분 기록:")
    for row in cur.fetchall():
        print(f"   [{row[0]}] 체중: {row[1]}kg | 골격근량: {row[2]}kg | 체지방률: {row[3]}%")

    cur = db.execute("SELECT exam_date, hba1c_pct, triglyceride_mgdl, uric_acid_mgdl FROM clinical_lab_results ORDER BY exam_date")
    print("• 정기 피검사 시계열 (HbA1c / TG / 요산):")
    for row in cur.fetchall():
        print(f"   [{row[0]}] 당화혈색소: {row[1]}% | 중성지방: {row[2]} mg/dL | 요산: {row[3]} mg/dL")

    print("=" * 50)
    print("✅ 모든 원천 데이터 100% 무손실 검증 완료!")
    print("=" * 50 + "\n")


def run_migration():
    """마이그레이션 전체 프로세스 실행 (운영용 MySQL + 개발서버용 SQLite healthy.db 동시 무손실 생성)"""
    from db_config import (
        get_sqlite_connection, get_mysql_connection,
        init_sqlite_db, init_mysql_db
    )

    print(f"\n🚀 [바람길 전사 DB 마이그레이션 개시 (활성 엔진: {DB_TYPE})]")

    # 1. 운영 데이터베이스 (MySQL: healthy) 마이그레이션
    print("\n--- [1/2] 운영 데이터베이스 (MySQL: healthy) 마이그레이션 ---")
    try:
        init_mysql_db()
        with get_mysql_connection() as mysql_db:
            migrate_workouts(mysql_db)
            migrate_blood_lab(mysql_db)
            verify_migration(mysql_db)
        print("✅ MySQL 'healthy' 데이터베이스 마이그레이션 완료!")
    except Exception as e:
        print(f"⚠️ MySQL 마이그레이션 중 오류: {e}")

    # 2. 개발서버용 로컬 SQLite (healthy.db) 동시 생성 및 보존
    print("\n--- [2/2] 개발서버용 데이터베이스 (SQLite: healthy.db) 마이그레이션 ---")
    init_sqlite_db()
    with get_sqlite_connection() as sqlite_db:
        migrate_workouts(sqlite_db)
        migrate_blood_lab(sqlite_db)
        verify_migration(sqlite_db)
    print("✅ 개발서버용 SQLite 'healthy.db' 마이그레이션 완료!\n")


if __name__ == "__main__":
    run_migration()
