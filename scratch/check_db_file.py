
import sqlite3
db_path = r'c:\Python\trade\trade.db'
try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM analysis_results WHERE filename LIKE '%20260505%'")
    rows = cursor.fetchall()
    for row in rows:
        print(row)
    conn.close()
except Exception as e:
    print(f"Error: {e}")
