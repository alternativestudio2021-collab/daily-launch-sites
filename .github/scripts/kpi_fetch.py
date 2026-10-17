#!/usr/bin/env python3
"""Cloudflare Web Analytics から事業ごとの訪問数を読み取り、JSON に書き出す。

読み取り専用(GraphQL Analytics API)。数字は標準出力に出さない
(公開リポジトリの Actions ログは誰でも見られるため)。

使い方: CF_API_TOKEN=... python3 kpi_fetch.py <出力先.json>
"""
import datetime as dt
import json
import os
import sys
import urllib.request

ACCOUNT_TAG = "325da2b63e5b32d897a5a87353dad067"
SITE_TAG = "9581a3c8e05b48b88f0cddf2c6ed869b"
PATH_PREFIX = "/daily-launch-sites/"
START = dt.datetime(2026, 10, 12, 15, 0, tzinfo=dt.timezone.utc)  # 2026-10-13 00:00 JST
CHUNK = dt.timedelta(days=7)
API = "https://api.cloudflare.com/client/v4/graphql"


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def query(token, since, until):
    q = (
        "query($a:String!,$f:AccountRumPageloadEventsAdaptiveGroupsFilter_InputObject!)"
        "{viewer{accounts(filter:{accountTag:$a}){rows:rumPageloadEventsAdaptiveGroups("
        "limit:1000,filter:$f){sum{visits} dimensions{requestPath}}}}}"
    )
    variables = {
        "a": ACCOUNT_TAG,
        "f": {"AND": [
            {"datetime_geq": iso(since), "datetime_lt": iso(until)},
            {"siteTag": SITE_TAG},
            {"bot": 0},
        ]},
    }
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": q, "variables": variables}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    if body.get("errors"):
        msgs = "; ".join(e.get("message", "?") for e in body["errors"])
        raise RuntimeError(f"GraphQL error: {msgs}")
    rows = body["data"]["viewer"]["accounts"][0]["rows"]
    out = {}
    for row in rows:
        path = row["dimensions"]["requestPath"] or ""
        if not path.startswith(PATH_PREFIX):
            continue
        out[path] = out.get(path, 0) + int(row["sum"]["visits"])
    return out


def main():
    token = os.environ.get("CF_API_TOKEN")
    if not token:
        sys.exit("CF_API_TOKEN が設定されていません")
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)

    total = {}
    t = START
    while t < now:
        u = min(t + CHUNK, now)
        for p, v in query(token, t, u).items():
            total[p] = total.get(p, 0) + v
        t = u
    last24 = query(token, now - dt.timedelta(hours=24), now)

    paths = {}
    for p in sorted(set(total) | set(last24)):
        paths[p] = {"visits": total.get(p, 0), "visits24h": last24.get(p, 0)}

    jst = dt.timezone(dt.timedelta(hours=9))
    result = {
        "measuredAt": now.astimezone(jst).isoformat(),
        "since": START.astimezone(jst).isoformat(),
        "filter": "bot=0 (ダッシュボードの「ボットを除外する」と同じ)",
        "paths": paths,
    }
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"ok: {len(paths)} paths")  # 件数だけ。訪問数は出さない


if __name__ == "__main__":
    main()
