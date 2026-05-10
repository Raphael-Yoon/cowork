
import sys
sys.path.append(r'c:\Python\cowork\scratch')
from recommend_10 import get_current_price

p1 = get_current_price('005930')
p2 = get_current_price('005935')

print(f"삼성전자(005930) 현재가: {p1:,}원")
print(f"삼성전자우(005935) 현재가: {p2:,}원")

target = 310800
print(f"목표가(공통): {target:,}원")
print(f"삼성전자 상승여력: {((target-p1)/p1*100):.1f}%")
print(f"삼성전자우 상승여력: {((target-p2)/p2*100):.1f}%")
