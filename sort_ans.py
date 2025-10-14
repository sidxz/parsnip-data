#!/usr/bin/env python3
"""
sort_answers.py — Sort questions[*].possibleAnswers by 'answer' (default).

Default behavior:
  • Sorts ascending, case-insensitive on the 'answer' field.
  • Missing/empty answer values are pushed to the end.
  • Writes in place and creates a .bak backup unless --no-backup is used.

Usage:
  # In-place (creates questions.json.bak)
  python sort_answers.py --path /mnt/data/questions.json

  # Write to a new file
  python sort_answers.py --path /mnt/data/questions.json --output /mnt/data/questions.sorted.json

  # Descending
  python sort_answers.py --path /mnt/data/questions.json --desc

  # Sort by a different key inside each answer object
  python sort_answers.py --path /mnt/data/questions.json --key label
"""

import argparse
import json
import sys
import shutil

def norm(val):
    """Normalize a value for case-insensitive sorting; handle None gracefully."""
    if val is None:
        return ""
    # stringify anything non-string
    s = str(val)
    # casefold for robust, case-insensitive ordering
    return s.casefold()

def main():
    ap = argparse.ArgumentParser(description="Sort each questions[*].possibleAnswers by a given field (default: 'answer').")
    ap.add_argument("--path", default="./data/questions.json", help="Path to questions.json")
    ap.add_argument("--key", default="answer", help="Field name inside each possibleAnswers item to sort by (default: 'answer')")
    ap.add_argument("--desc", action="store_true", help="Sort descending (default ascending)")
    ap.add_argument("--output", help="Write sorted JSON to this path instead of modifying the input file")
    ap.add_argument("--no-backup", action="store_true", help="When writing in place, do not create a .bak backup")
    args = ap.parse_args()

    # Load JSON
    try:
        with open(args.path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Failed to read JSON at {args.path}: {e}", file=sys.stderr)
        sys.exit(2)

    questions = data.get("questions", [])
    if not isinstance(questions, list):
        print("JSON does not contain a top-level 'questions' list.", file=sys.stderr)
        sys.exit(2)

    changed = 0
    total = 0

    for qi, q in enumerate(questions):
        pa = q.get("possibleAnswers")
        if not isinstance(pa, list):
            continue

        total += 1
        # Build a snapshot to detect changes after sort (stable & deterministic)
        before = json.dumps(pa, sort_keys=True)

        # Sort rule:
        #  - Items missing the key or with empty key go LAST
        #  - Otherwise sort by case-insensitive value of the key
        def sort_key(item):
            v = item.get(args.key, None)
            is_missing = v is None or (isinstance(v, str) and v.strip() == "")
            return (is_missing, norm(v))

        pa.sort(key=sort_key, reverse=args.desc)

        after = json.dumps(pa, sort_keys=True)
        if before != after:
            changed += 1

    out_path = args.output or args.path

    # Backup if writing in place without --output
    if args.output is None and not args.no_backup:
        bak_path = args.path + ".bak"
        try:
            shutil.copyfile(args.path, bak_path)
            print(f"🗂  Backup created: {bak_path}")
        except Exception as e:
            print(f"⚠️  Could not create backup {bak_path}: {e}", file=sys.stderr)

    # Write file
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"💾 Wrote sorted JSON to: {out_path}")
    except Exception as e:
        print(f"Failed to write JSON to {out_path}: {e}", file=sys.stderr)
        sys.exit(2)

    print(f"✅ Sorted possibleAnswers for {changed}/{total} questions "
          f"(key='{args.key}', order={'desc' if args.desc else 'asc'}).")

if __name__ == "__main__":
    main()
