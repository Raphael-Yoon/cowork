"""
[개발4팀 바람길] 데이터베이스 설정 및 연결 관리 모듈 (db_config.py)
- 운영서버 (IS_PROD=true): MySQL 전용 DB 스페이스('healthy') 사용
- 개발환경 (IS_PROD=false): SQLite ('healthy.db') 사용 (로컬 개발 및 관제 전용)
- OS 호환성: pathlib.Path 전면 적용 (Linux/Ubuntu/Windows 완벽 호환)
"""

import os
import sqlite3
import urllib.parse
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Dict, Optional

# 디렉토리 경로 (pathlib.Path 적용)
_BASE_DIR = Path(__file__).resolve().parent
_WORKSPACE_DIR = _BASE_DIR.parent.parent
DEFAULT_SQLITE_PATH = str(_BASE_DIR / 'healthy.db')

# .env 파일 자동 탐색 및 로드 (현재 디렉토리 .env 우선 로드)
try:
    from dotenv import load_dotenv
    for env_candidate in [_BASE_DIR / '.env', _WORKSPACE_DIR / '.env', _WORKSPACE_DIR / 'snowball' / '.env']:
        if env_candidate.exists():
            load_dotenv(env_candidate, override=False)
            # 현재 healthy/.env를 찾았으면 바로 종료
            if env_candidate == _BASE_DIR / '.env':
                break
except Exception:
    pass

# 환경 판별: HEALTHY_DB_TYPE -> IS_PROD 환경변수 기준
# 운영서버 기본 원칙: MySQL 'healthy' DB를 우선 사용합니다.
# IS_PROD=false 또는 HEALTHY_DB_TYPE=sqlite로 명시된 경우에만 로컬 개발용 SQLite를 사용합니다.
_is_prod_env = os.getenv("IS_PROD", "").strip().lower()
_db_type_env = os.getenv("HEALTHY_DB_TYPE") or os.getenv("DB_TYPE", "")

if _db_type_env.lower() in ("mysql", "sqlite"):
    DB_TYPE = _db_type_env.lower()
elif _is_prod_env in ("false", "0", "no"):
    DB_TYPE = "sqlite"
else:
    DB_TYPE = "mysql"

# SQLite 설정
SQLITE_DATABASE = os.getenv('HEALTHY_DB_PATH', DEFAULT_SQLITE_PATH)

# MySQL 설정 (운영서버 전용 DB: healthy)
DEFAULT_MYSQL_URL = "mysql://root:150606@127.0.0.1:3306/healthy"
DATABASE_URL = os.getenv("HEALTHY_DATABASE_URL") or os.getenv("DATABASE_URL") or DEFAULT_MYSQL_URL


def _parse_mysql_url(url_str: str) -> Dict[str, Any]:
    parsed = urllib.parse.urlparse(url_str)
    healthy_db_name = os.getenv("HEALTHY_DATABASE")
    if not healthy_db_name:
        if os.getenv("HEALTHY_DATABASE_URL"):
            healthy_db_name = urllib.parse.urlparse(os.getenv("HEALTHY_DATABASE_URL")).path.lstrip("/")
        elif parsed.path and parsed.path.lstrip("/"):
            healthy_db_name = parsed.path.lstrip("/")
        else:
            healthy_db_name = "healthy"

    return {
        "host": parsed.hostname or os.getenv("MYSQL_HOST", "127.0.0.1"),
        "user": parsed.username or os.getenv("MYSQL_USER", "root"),
        "password": parsed.password or os.getenv("MYSQL_PASSWORD", ""),
        "database": healthy_db_name,
        "port": parsed.port or int(os.getenv("MYSQL_PORT", "3306")),
        "charset": "utf8mb4",
        "connect_timeout": 10,
    }


def get_sqlite_connection(db_path: Optional[str] = None):
    """SQLite 단독 연결 객체 반환"""
    target_path = db_path or SQLITE_DATABASE
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return SQLiteConnection(conn)


def get_mysql_connection():
    """MySQL 단독 연결 객체 반환"""
    import pymysql
    import pymysql.cursors

    cfg = _parse_mysql_url(DATABASE_URL)
    conn = pymysql.connect(
        host=cfg["host"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        port=cfg["port"],
        charset=cfg["charset"],
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=cfg["connect_timeout"],
        autocommit=False,
    )
    return MySQLConnection(conn)


def get_db_connection():
    """
    환경 설정(DB_TYPE)에 따라 SQLite 또는 MySQL 연결 객체 반환
    """
    if DB_TYPE == "mysql":
        return get_mysql_connection()
    else:
        return get_sqlite_connection()


class SQLiteConnection:
    """SQLite 연결 래퍼"""
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def execute(self, query: str, params: Optional[Any] = None):
        return self.conn.execute(query, params or ())

    def executemany(self, query: str, seq_of_params: Any):
        return self.conn.executemany(query, seq_of_params)

    def cursor(self):
        return self.conn.cursor()

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        self.close()


class DictRow(dict):
    """딕셔너리를 SQLite Row 인터페이스처럼 키/인덱스 모두 지원하도록 래핑"""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class MySQLCursor:
    """MySQL 커서 래퍼 (SQLite Row 호환 인터페이스)"""
    def __init__(self, cursor):
        self.cursor = cursor
        self.lastrowid = cursor.lastrowid
        self.rowcount = cursor.rowcount

    def fetchone(self):
        row = self.cursor.fetchone()
        return DictRow(row) if row else None

    def fetchall(self):
        rows = self.cursor.fetchall()
        return [DictRow(row) for row in rows]

    def __iter__(self):
        for row in self.cursor:
            yield DictRow(row)


class MySQLConnection:
    """MySQL 연결 래퍼 (SQLite 문법 호환성 제공)"""
    def __init__(self, conn):
        self.conn = conn
        self._cursor = None

    def execute(self, query: str, params: Optional[Any] = None):
        cursor = self.conn.cursor()
        if params is not None and len(params) > 0:
            if "?" in query:
                token = "__SQL_PARAM_TOKEN__"
                query = query.replace("?", token).replace("%", "%%").replace(token, "%s")
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        self._cursor = cursor
        return MySQLCursor(cursor)

    def executemany(self, query: str, seq_of_params: Any):
        cursor = self.conn.cursor()
        if seq_of_params is not None and len(seq_of_params) > 0:
            token = "__SQL_PARAM_TOKEN__"
            query = query.replace("?", token).replace("%", "%%").replace(token, "%s")
            cursor.executemany(query, seq_of_params)
        else:
            cursor.executemany(query, ())
        self._cursor = cursor
        return MySQLCursor(cursor)

    def cursor(self):
        return self.conn.cursor()

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        if self._cursor:
            self._cursor.close()
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        self.close()


@contextmanager
def get_db():
    """
    컨텍스트 매니저로 데이터베이스 연결 제공
    with get_db() as db:
        ...
    """
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()


def get_db_type() -> str:
    """현재 활성화된 데이터베이스 엔진 반환 ('sqlite' or 'mysql')"""
    return DB_TYPE


def is_mysql() -> bool:
    return DB_TYPE == "mysql"


def is_sqlite() -> bool:
    return DB_TYPE == "sqlite"


def init_sqlite_db(db_path: Optional[str] = None):
    """SQLite 데이터베이스 테이블 초기화"""
    target_path = db_path or SQLITE_DATABASE
    with get_sqlite_connection(target_path) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS workouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workout_date DATE NOT NULL UNIQUE,
                day_of_week VARCHAR(10) NOT NULL,
                time_of_day VARCHAR(20),
                workout_type VARCHAR(100),
                routine_name VARCHAR(150),
                morning_fasting_blood_sugar INTEGER NULL,
                evaluation VARCHAR(100) NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS workout_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workout_id INTEGER NOT NULL,
                session_no INTEGER NOT NULL,
                sport_type VARCHAR(50) NOT NULL,
                session_name VARCHAR(100),
                duration_seconds INTEGER NOT NULL,
                duration_str VARCHAR(20),
                distance_km REAL DEFAULT 0.00,
                estimated_distance_km REAL NULL,
                active_kcal INTEGER NOT NULL,
                total_kcal INTEGER NOT NULL,
                elevation_gain_m INTEGER DEFAULT 0,
                avg_heart_rate_bpm INTEGER,
                max_heart_rate_bpm INTEGER,
                avg_speed_kmh REAL,
                avg_pace VARCHAR(20),
                effort VARCHAR(50),
                weather_info TEXT,
                notes TEXT,
                FOREIGN KEY (workout_id) REFERENCES workouts(id) ON DELETE CASCADE
            );
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS session_splits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                split_no INTEGER NOT NULL,
                distance_km REAL,
                time_str VARCHAR(20),
                speed_kmh REAL,
                heart_rate_bpm INTEGER,
                FOREIGN KEY (session_id) REFERENCES workout_sessions(id) ON DELETE CASCADE
            );
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS body_composition (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                measure_date DATE NOT NULL UNIQUE,
                weight_kg REAL NOT NULL,
                body_fat_pct REAL NOT NULL,
                skeletal_muscle_kg REAL NOT NULL,
                bmi REAL NOT NULL,
                is_dehydrated INTEGER DEFAULT 0,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS clinical_lab_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_date DATE NOT NULL UNIQUE,
                hba1c_pct REAL NOT NULL,
                fasting_glucose INTEGER,
                triglyceride_mgdl INTEGER,
                ldl_mgdl INTEGER,
                uric_acid_mgdl REAL NOT NULL,
                ast_u_l INTEGER,
                alt_u_l INTEGER,
                creatinine_mgdl REAL,
                egfr_score REAL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS clinical_lab_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_date DATE NOT NULL,
                category VARCHAR(50),
                item_name VARCHAR(100),
                result_value VARCHAR(50),
                numeric_value REAL NULL,
                reference_range VARCHAR(50),
                unit VARCHAR(20),
                evaluation TEXT,
                FOREIGN KEY (exam_date) REFERENCES clinical_lab_results(exam_date) ON DELETE CASCADE
            );
        """)
        db.commit()


def init_mysql_db():
    """MySQL 데이터베이스 및 테이블 초기화"""
    import pymysql
    cfg = _parse_mysql_url(DATABASE_URL)
    db_name = cfg["database"]

    server_cfg = cfg.copy()
    server_cfg.pop("database", None)
    conn = pymysql.connect(**server_cfg, autocommit=True)
    with conn.cursor() as cur:
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
    conn.close()

    conn = pymysql.connect(**cfg, autocommit=True)
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS workouts (
                id INT AUTO_INCREMENT PRIMARY KEY,
                workout_date DATE NOT NULL UNIQUE,
                day_of_week VARCHAR(10) NOT NULL,
                time_of_day VARCHAR(20),
                workout_type VARCHAR(100),
                routine_name VARCHAR(150),
                morning_fasting_blood_sugar INT NULL,
                evaluation VARCHAR(100) NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS workout_sessions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                workout_id INT NOT NULL,
                session_no INT NOT NULL,
                sport_type VARCHAR(50) NOT NULL,
                session_name VARCHAR(100),
                duration_seconds INT NOT NULL,
                duration_str VARCHAR(20),
                distance_km DOUBLE DEFAULT 0.00,
                estimated_distance_km DOUBLE NULL,
                active_kcal INT NOT NULL,
                total_kcal INT NOT NULL,
                elevation_gain_m INT DEFAULT 0,
                avg_heart_rate_bpm INT,
                max_heart_rate_bpm INT,
                avg_speed_kmh DOUBLE,
                avg_pace VARCHAR(20),
                effort VARCHAR(50),
                weather_info TEXT,
                notes TEXT,
                FOREIGN KEY (workout_id) REFERENCES workouts(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS session_splits (
                id INT AUTO_INCREMENT PRIMARY KEY,
                session_id INT NOT NULL,
                split_no INT NOT NULL,
                distance_km DOUBLE,
                time_str VARCHAR(20),
                speed_kmh DOUBLE,
                heart_rate_bpm INT,
                FOREIGN KEY (session_id) REFERENCES workout_sessions(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS body_composition (
                id INT AUTO_INCREMENT PRIMARY KEY,
                measure_date DATE NOT NULL UNIQUE,
                weight_kg DOUBLE NOT NULL,
                body_fat_pct DOUBLE NOT NULL,
                skeletal_muscle_kg DOUBLE NOT NULL,
                bmi DOUBLE NOT NULL,
                is_dehydrated INT DEFAULT 0,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS clinical_lab_results (
                id INT AUTO_INCREMENT PRIMARY KEY,
                exam_date DATE NOT NULL UNIQUE,
                hba1c_pct DOUBLE NOT NULL,
                fasting_glucose INT,
                triglyceride_mgdl INT,
                ldl_mgdl INT,
                uric_acid_mgdl DOUBLE NOT NULL,
                ast_u_l INT,
                alt_u_l INT,
                creatinine_mgdl DOUBLE,
                egfr_score DOUBLE,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS clinical_lab_items (
                id INT AUTO_INCREMENT PRIMARY KEY,
                exam_date DATE NOT NULL,
                category VARCHAR(50),
                item_name VARCHAR(100),
                result_value VARCHAR(50),
                numeric_value DOUBLE NULL,
                reference_range VARCHAR(50),
                unit VARCHAR(20),
                evaluation TEXT,
                INDEX idx_exam_date (exam_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
    conn.close()


def init_db(engine: Optional[str] = None):
    """
    바람길 시스템 테이블 초기화
    - engine이 지정되지 않으면 DB_TYPE에 따라 자동 초기화
    """
    target = (engine or DB_TYPE).lower()
    if target == "mysql":
        init_mysql_db()
    else:
        init_sqlite_db()


if __name__ == "__main__":
    print(f"[*] Initializing database (Configured Engine: {DB_TYPE})...")
    init_db()
    print(f"[+] {DB_TYPE.upper()} Database initialized successfully.")
    # 로컬 개발 환경용 SQLite도 항상 동시 확인
    if DB_TYPE != "sqlite":
        init_sqlite_db()
        print("[+] SQLite healthy.db also initialized successfully.")
