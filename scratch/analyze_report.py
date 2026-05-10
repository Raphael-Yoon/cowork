import pandas as pd

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from audit_loader import get_latest_audit_report

try:
    df = get_latest_audit_report()
    print("Columns:", df.columns.tolist())
    print("\nShape:", df.shape)
    print("\nHead:\n", df.head())
    
    # 분석 포인트: 재무제표 상 주요 지표 요약
    if '종목명' in df.columns or 'Name' in df.columns:
        name_col = '종목명' if '종목명' in df.columns else 'Name'
        print(f"\nSample Stocks: {df[name_col].head().tolist()}")
        
except Exception as e:
    print(f"Error reading file: {e}")
