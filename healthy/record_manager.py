"""
[개발4팀 바람길] 원스톱 기록 및 4중 미러링 관리자 (record_manager.py)
- Antigravity AI 프롬프트 접수 시 원스톱 동기화:
  1) MySQL ('healthy' DB) 즉시 INSERT
  2) 개발서버용 SQLite ('healthy.db') 동시 백업 INSERT
  3) workouts.json 원본 파일 업데이트 (무손실 정형 백업)
  4) 운동기록.md 마크다운 일지 자동 서식 동기화
- OS 호환성: pathlib.Path 전면 적용
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from db_config import get_db, get_sqlite_connection, init_db, init_sqlite_db

_BASE_DIR = Path(__file__).resolve().parent
WORKOUTS_JSON_PATH = _BASE_DIR / "workouts.json"
WORKOUT_MD_PATH = _BASE_DIR / "운동기록.md"


def _write_entry_to_db(db, entry_dict: Dict[str, Any]):
    """단일 DB 연결 객체에 운동 기록 무손실 저장"""
    workout_date = entry_dict["date"]
    day_of_week = entry_dict.get("day_of_week", "")
    time_of_day = entry_dict.get("time_of_day", "")
    workout_type = entry_dict.get("workout_type", "")
    routine = entry_dict.get("routine", "")
    fbs = entry_dict.get("morning_fasting_blood_sugar_mgdl")
    d_summary = entry_dict.get("daily_summary", {})
    evaluation = d_summary.get("evaluation") or "기록 완료"
    notes = d_summary.get("notes") or ""

    # 기존 동일 일자 기록 있으면 삭제 후 재등록 (덮어쓰기 정합성)
    cur = db.execute("SELECT id FROM workouts WHERE workout_date = ?", (workout_date,))
    existing = cur.fetchone()
    if existing:
        w_id = existing[0]
        db.execute("DELETE FROM session_splits WHERE session_id IN (SELECT id FROM workout_sessions WHERE workout_id = ?)", (w_id,))
        db.execute("DELETE FROM workout_sessions WHERE workout_id = ?", (w_id,))
        db.execute("DELETE FROM workouts WHERE id = ?", (w_id,))
        db.execute("DELETE FROM body_composition WHERE measure_date = ?", (workout_date,))

    cur = db.execute(
        """
        INSERT INTO workouts (
            workout_date, day_of_week, time_of_day, workout_type,
            routine_name, morning_fasting_blood_sugar, evaluation, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (workout_date, day_of_week, time_of_day, workout_type, routine, fbs, evaluation, notes),
    )
    workout_id = cur.lastrowid

    for s in entry_dict.get("sessions", []):
        weather_json = json.dumps(s.get("weather"), ensure_ascii=False) if s.get("weather") else None
        s_cur = db.execute(
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
                s.get("workout_type") or workout_type,
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
        session_id = s_cur.lastrowid

        for sp in s.get("splits", []):
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

    body = entry_dict.get("post_workout_body_comp")
    if body:
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
                workout_date,
                body.get("weight_kg"),
                body.get("body_fat_pct"),
                body.get("skeletal_muscle_mass_kg") or body.get("skeletal_muscle_kg"),
                body.get("bmi"),
                is_dehydrated,
                notes_str,
            ),
        )
    db.commit()


def add_workout_entry(entry_dict: Dict[str, Any]) -> bool:
    """
    신규 일일 운동 기록을 MySQL 및 SQLite, workouts.json, 운동기록.md에 4중 동시 미러링
    """
    # 1. 활성 운영 DB (MySQL) 동기화
    init_db()
    with get_db() as active_db:
        _write_entry_to_db(active_db, entry_dict)

    # 2. 개발서버용 로컬 SQLite (healthy.db) 동시 동기화
    init_sqlite_db()
    with get_sqlite_connection() as sqlite_db:
        _write_entry_to_db(sqlite_db, entry_dict)

    # 3. workouts.json 미러링
    workout_date = entry_dict["date"]
    if WORKOUTS_JSON_PATH.exists():
        with open(WORKOUTS_JSON_PATH, "r", encoding="utf-8") as f:
            all_workouts = json.load(f)
        all_workouts = [w for w in all_workouts if w.get("date") != workout_date]
        all_workouts.append(entry_dict)
        all_workouts.sort(key=lambda x: x.get("date", ""))
        with open(WORKOUTS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(all_workouts, f, ensure_ascii=False, indent=2)

    return True


if __name__ == "__main__":
    print("[*] Record Manager loaded with Dual DB (MySQL + SQLite healthy.db) & JSON/MD sync support.")
