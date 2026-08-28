from __future__ import annotations

import argparse
import json
import sys

from .job import run_job_file


def main() -> int:
    parser = argparse.ArgumentParser(description="重庆市政 DXF 道路、管网、挡护确定性算量（本地 MVP）")
    parser.add_argument("--input", required=True, help="算量输入 JSON")
    parser.add_argument("--output", required=True, help="结果 JSON")
    args = parser.parse_args()
    try:
        result = run_job_file(args.input, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"算量未完成：{exc}", file=sys.stderr)
        return 2
    print(json.dumps({"job_id": result["job_id"], "status": result["status"], "total_lines": len(result["calculation"]["quantities"]), "warnings": len(result["calculation"]["warnings"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
