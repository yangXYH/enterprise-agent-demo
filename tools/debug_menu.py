import re, pathlib

html = pathlib.Path(r'C:\demo-project\frontend\public\ecommerce-dashboard.html').read_text(encoding='utf-8')
m = re.search(r'let MENUS=\[(.*?)\];\s*\n\s*const ROUTE_TO_MAIN', html, re.S)
print(m.group(0).encode('utf-8', errors='replace').decode('utf-8'))
