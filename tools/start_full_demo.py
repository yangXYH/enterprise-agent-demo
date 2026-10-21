"""Launch the original FastAPI application and its original compiled Vue interface."""
from __future__ import annotations

import os
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))


def main():
    from full_demo_seed import seed
    seed()
    bundle = ROOT / "demo" / "frontend"
    if not (bundle / "index.html").exists():
        bundle = ROOT / "frontend" / "dist"
    if not (bundle / "index.html").exists():
        raise SystemExit("Vue bundle missing. Run npm ci && npm run build in frontend, or use docker compose up --build.")
    os.environ["FRONTEND_DIST"] = str(bundle)
    import uvicorn
    port = int(os.getenv("DEMO_PORT", "4173"))
    host = os.getenv("DEMO_HOST", "127.0.0.1")
    print(f"Original Vue + FastAPI application: http://127.0.0.1:{port}")
    print("No login required: opens as the synthetic demo administrator.")
    if "--open-browser" in sys.argv:
        threading.Timer(2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    uvicorn.run("main:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
