import re, sys, pathlib
p = pathlib.Path(r'C:\demo-project\frontend\public\ecommerce-dashboard.html')
html = p.read_text(encoding='utf-8')
m = re.search(r'let MENUS=\[(.*?)\];\s*\n\s*const ROUTE_TO_MAIN', html, re.S)
if not m:
    print('NOT FOUND')
else:
    print(m.group(0))
