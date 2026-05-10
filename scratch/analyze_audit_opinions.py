import pandas as pd

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from audit_loader import get_latest_audit_report

df = get_latest_audit_report()

try:
    if df is not None:
    
    # 1. 감사 의견 통계
    audit_stats = df['회계감사의견'].value_counts(dropna=False)
    internal_stats = df['내부통제의견'].value_counts(dropna=False)
    
    print("--- Audit Opinions Summary ---")
    print(audit_stats)
    print("\n--- Internal Control Opinions Summary ---")
    print(internal_stats)
    
    # 2. '비적정' 혹은 특이사항이 있는 종목 추출
    non_proper = df[~df['회계감사의견'].isin(['적정', '적정의견']) & df['회계감사의견'].notna()]
    if not non_proper.empty:
        print("\n--- Non-Proper Audit Opinions ---")
        print(non_proper[['종목코드', '종목명', '회계감사의견']].head(10))
    
    # 3. 내부통제 비적정 종목
    non_internal = df[~df['내부통제의견'].isin(['적정', '적정의견']) & df['내부통제의견'].notna()]
    if not non_internal.empty:
        print("\n--- Non-Proper Internal Control ---")
        print(non_internal[['종목코드', '종목명', '내부통제의견']].head(10))

except Exception as e:
    print(f"Error: {e}")
