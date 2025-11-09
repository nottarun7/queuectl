#!/usr/bin/env python
"""Helper to enqueue a job from a JSON file to avoid shell quoting issues on Windows.

Usage:
  python enqueue_job.py [path-to-json]

If no path is provided, it defaults to ./job.json
"""
import sys
import json
from queuectl.queue import Queue


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "job.json"
    with open(path, "r", encoding="utf-8") as fh:
        job_json = fh.read()
    try:
        job_data = json.loads(job_json)
    except json.JSONDecodeError as exc:
        print(f"invalid JSON in {path}: {exc}")
        return

    q = Queue()
    res = q.enqueue(job_data)
    print(res.get('message', res))


if __name__ == "__main__":
    main()
