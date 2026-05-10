
import sys
sys.path.append(r'c:\Python\cowork\scratch')
from recommend_10 import get_current_price

codes = {'005930': '삼성전자', '000660': 'SK하이닉스', '005935': '삼성전자우'}
targets = {'005930': 310800, '000660': 1761200, '005935': 310800}

for c, name in codes.items():
    curr = get_current_price(c)
    target = targets[c]
    upside = ((target - curr) / curr * 100) if curr > 0 else 0
    print(f"{name}({c}): 현재가={curr:,}, 목표가={target:,}, 상승여력={upside:.1f}%")
