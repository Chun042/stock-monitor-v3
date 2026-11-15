#!/usr/bin/env python3
"""List and remove Stock Monitor profiles through the protected Worker admin API."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def request_json(base: str, token: str, path: str, method: str = "GET") -> dict:
    request = Request(
        base.rstrip("/") + path,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            details = json.loads(error.read().decode("utf-8"))
            message = details.get("error", str(error))
        except (json.JSONDecodeError, UnicodeDecodeError):
            message = str(error)
        raise RuntimeError(f"Worker 回應 {error.code}: {message}") from error
    except URLError as error:
        raise RuntimeError(f"無法連線到 Worker：{error.reason}") from error


def describe_watchlists(items: list[dict]) -> str:
    if not items:
        return "—"
    return ", ".join(
        f"{item.get('market', '?')}:{item.get('symbol', '?')}"
        + (f" {item['display_name']}" if item.get("display_name") else "")
        for item in items
    )


def describe_holdings(items: list[dict]) -> str:
    if not items:
        return "—"
    return ", ".join(
        f"{item.get('market', '?')}:{item.get('symbol', '?')} × {item.get('quantity', '?')}"
        for item in items
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="管理 Stock Monitor 的雲端使用者 profile")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="列出 profile、自選股、持倉與最後活動時間")
    delete_parser = commands.add_parser("delete", help="刪除 profile 的暱稱、自選股與持倉")
    delete_parser.add_argument("owner_id", help="要刪除的完整 owner_id")
    args = parser.parse_args()

    base = os.environ.get("PUSH_API_BASE", "").strip()
    if not base:
        parser.error("請先設定 PUSH_API_BASE（Cloudflare Worker URL）")
    token = os.environ.get("PUSH_ADMIN_TOKEN", "").strip()
    if not token:
        token = getpass.getpass("Worker ADMIN_TOKEN（不會顯示）: ").strip()
    if not token:
        parser.error("ADMIN_TOKEN 不可為空")

    try:
        if args.command == "list":
            result = request_json(base, token, "/admin/profiles")
            profiles = result.get("profiles", [])
            if not profiles:
                print("目前沒有 profile 資料。")
                return 0
            for profile in profiles:
                label = profile.get("display_name") or "（舊資料，未同步暱稱）"
                print(f"{label} | owner_id: {profile['owner_id']}")
                print(f"  自選股：{describe_watchlists(profile.get('watchlists', []))}")
                print(f"  持倉：{describe_holdings(profile.get('holdings', []))}")
                print(f"  最後活動：{profile.get('last_activity') or '—'}")
            return 0

        owner_id = args.owner_id
        print(f"即將刪除 profile {owner_id} 的暱稱、自選股與持倉資料。推播裝置不會刪除。")
        confirmation = input("請輸入完整 owner_id 確認刪除: ").strip()
        if confirmation != owner_id:
            print("確認文字不符，未刪除。")
            return 1
        path = "/admin/profiles?ownerId=" + quote(owner_id, safe="")
        result = request_json(base, token, path, method="DELETE")
        if not result.get("deleted"):
            print("找不到此 profile 的雲端資料，沒有任何資料被刪除。")
            return 1
        print(f"已刪除 profile {owner_id} 的雲端資料。")
        return 0
    except (RuntimeError, KeyError, json.JSONDecodeError) as error:
        print(f"錯誤：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
