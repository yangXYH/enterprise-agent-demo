#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
聚水潭凭证刷新脚本(在 8.163.241.83 服务器上执行)
- 用旧凭证(access_token / refresh_token)调用旧版刷新接口 refresh.token
- 签名:MD5(method + partnerid + token + ts + partnerkey)
- 刷新成功后 access_token 值不变,有效期顺延一年(data.expired_date)
用法: python3 jst_refresh_token.py
"""
import hashlib
import json
import sys
import time

import requests

# ===== 从服务器 .env 读取(或直接填) =====
APP_KEY = "28391c24d101431287e4b614f4eb1068"      # partnerid
APP_SECRET = "9179612e9b24442dba2692f67cc80afb"   # partnerkey
ACCESS_TOKEN = "bdd2903e0eeb413a84def89174a30b8f"
REFRESH_TOKEN = "5297771ba3bb48ab9b0645bd9e6a98e8"
REFRESH_URL = "https://open.erp321.com/api/open/query.aspx"


def refresh(token: str, label: str) -> None:
    ts = str(int(time.time()))
    source = "refresh.token" + APP_KEY + "token" + token + "ts" + ts + APP_SECRET
    sign = hashlib.md5(source.encode("utf-8")).hexdigest()
    url = (f"{REFRESH_URL}?method=refresh.token&partnerid={APP_KEY}"
           f"&token={token}&ts={ts}&sign={sign}")
    try:
        r = requests.post(url, data=b"{}",
                          headers={"Content-Type": "application/json"}, timeout=25)
        print(f"[{label}] HTTP {r.status_code}")
        print(f"[{label}] {r.text[:800]}")
    except Exception as exc:  # noqa: BLE001
        print(f"[{label}] ERROR {exc!r}")


def main() -> None:
    print(">>> 用 access_token 刷新(官方推荐,刷新后 token 不变仅顺延):")
    refresh(ACCESS_TOKEN, "access_token")
    print(">>> 用 refresh_token 刷新(如 access_token 已彻底失效时尝试):")
    refresh(REFRESH_TOKEN, "refresh_token")


if __name__ == "__main__":
    sys.exit(main())
