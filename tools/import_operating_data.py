"""Run: .venv/Scripts/python tools/import_operating_data.py <report folder>"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from utils.operating_analysis_service import import_excel,metadata

if __name__=='__main__':
    for path in sorted(Path(sys.argv[1]).glob('*.xlsx')):
        print(import_excel(path),flush=True)
    m=metadata()
    print({'files':len(m['batches']),'days':len(m['dates']),'start':m['dates'][0],'end':m['dates'][-1]},flush=True)
