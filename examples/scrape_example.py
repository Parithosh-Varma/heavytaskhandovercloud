#!/usr/bin/env python3
"""Tiny hth example job: fetch a few URLs and write results to ./output/.

Run locally:
    python3 examples/scrape_example.py

Run on Cloud Shell via hth:
    hth run examples/scrape_example.py
    hth logs <id> -f
    hth pull <id>          # -> ./results/<id>/

The job always writes to ./output/ relative to its cwd, which is
~/hth/jobs/<id>/ on Cloud Shell. `hth pull` copies that dir back.
Stdlib only.
"""
import json
import os
import sys
import time
import urllib.request

URLS = [
    "https://example.com",
    "https://example.org",
    "https://www.example.net",
]

TIMEOUT = 20


def fetch(url):
    started = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hth-example/0.1"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read()
            return {
                "url": url,
                "ok": True,
                "status": getattr(resp, "status", 200),
                "bytes": len(body),
                "seconds": round(time.time() - started, 3),
                "snippet": body[:500].decode("utf-8", "replace"),
            }
    except Exception as ex:  # noqa: BLE001 - example should never crash on one URL
        return {
            "url": url,
            "ok": False,
            "error": "%s: %s" % (type(ex).__name__, ex),
            "seconds": round(time.time() - started, 3),
        }


def main():
    outdir = os.path.join(os.getcwd(), "output")
    os.makedirs(outdir, exist_ok=True)
    print("[scrape] fetching %d urls -> %s" % (len(URLS), outdir), flush=True)

    results = []
    for i, url in enumerate(URLS):
        print("[scrape] (%d/%d) %s" % (i + 1, len(URLS), url), flush=True)
        r = fetch(url)
        results.append(r)
        if r["ok"]:
            print("[scrape]   ok %s bytes in %ss" % (r["bytes"], r["seconds"]), flush=True)
        else:
            print("[scrape]   FAIL %s" % r["error"], flush=True)

    with open(os.path.join(outdir, "results.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    # one small file per URL for easy `hth pull` inspection
    for idx, r in enumerate(results):
        name = "page_%d.txt" % idx
        with open(os.path.join(outdir, name), "w", encoding="utf-8") as fh:
            fh.write("url: %s\nok: %s\n\n" % (r["url"], r["ok"]))
            fh.write(r.get("snippet", r.get("error", "")))
    print("[scrape] done. wrote %s/results.json" % outdir, flush=True)


if __name__ == "__main__":
    sys.exit(main())
