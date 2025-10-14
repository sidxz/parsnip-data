#!/usr/bin/env python3
"""
find_dupe_ids.py — Scan a questionnaire JSON for duplicate GUIDs and (optionally) fix them.

Checks:
  1) Question GUIDs:            questions[*].id
  2) Possible-answer GUIDs:     questions[*].possibleAnswers[*].id
  (We do NOT touch 'identification' codes.)

Fix mode:
  - Use --fix to generate fresh UUID4s for ONLY those IDs that are duplicated.
  - By default, writes changes back to the same file with a .bak backup (unless --no-backup).
  - Or write to a different file via --output <path>.
  - Prints an old->new mapping for every replaced ID.

Usage:
  # Detect only
  python find_dupe_ids.py --path /mnt/data/questions.json

  # Detect and fix in place (creates /mnt/data/questions.json.bak)
  python find_dupe_ids.py --path /mnt/data/questions.json --fix

  # Fix but write to a new file (no backup needed)
  python find_dupe_ids.py --path /mnt/data/questions.json --fix --output fixed.json

  # Fix without creating a backup (in-place)
  python find_dupe_ids.py --path /mnt/data/questions.json --fix --no-backup
"""

import argparse
import json
import sys
import uuid
import shutil
from collections import defaultdict

def add_occurrence(index_map, key, where):
    index_map[key].append(where)

def find_duplicates(occ_map):
    return {k: v for k, v in occ_map.items() if len(v) > 1}

def print_dupes(kind, occ_map) -> int:
    dupes = find_duplicates(occ_map)
    if not dupes:
        print(f"✅ No duplicates found for {kind}.")
        return 0
    print(f"\n❌ Duplicates found for {kind}:")
    for k, locs in dupes.items():
        print(f"  {k}  (count={len(locs)})")
        for where in locs:
            print(f"    - {where}")
    return len(dupes)

def generate_unique_uuid(existing_ids: set) -> str:
    # Keep generating until it's unique across all IDs
    while True:
        new_id = str(uuid.uuid4())
        if new_id not in existing_ids:
            existing_ids.add(new_id)
            return new_id

def main():
    ap = argparse.ArgumentParser(description="Identify (and optionally fix) duplicate GUIDs in questionnaire JSON.")
    ap.add_argument("--path", default="./data/questions.json", help="Path to questions.json")
    ap.add_argument("--fix", action="store_true", help="Generate fresh GUIDs for duplicates and write output")
    ap.add_argument("--output", help="Write fixed JSON to this path instead of modifying the input file")
    ap.add_argument("--no-backup", action="store_true", help="When fixing in place, do not create a .bak backup")
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

    # Collect occurrences + a global set of all IDs for uniqueness checks
    qid_occ = defaultdict(list)     # questions[*].id
    ansid_occ = defaultdict(list)   # questions[*].possibleAnswers[*].id
    all_ids = set()

    for qi, q in enumerate(questions):
        qid = q.get("id")
        if qid:
            add_occurrence(qid_occ, qid, f"question[{qi}] id")
            all_ids.add(qid)
        else:
            print(f"⚠️  Missing questions[{qi}].id")

        for ai, ans in enumerate(q.get("possibleAnswers", []) or []):
            aid = ans.get("id")
            if aid:
                add_occurrence(ansid_occ, aid, f"question[{qi}].possibleAnswers[{ai}] id")
                all_ids.add(aid)
            else:
                print(f"⚠️  Missing questions[{qi}].possibleAnswers[{ai}].id")

    # Report duplicates
    print(f"Scanned {len(questions)} questions from {args.path}")
    dup_count = 0
    dup_count += print_dupes("Question GUIDs (questions[*].id)", qid_occ)
    dup_count += print_dupes("Answer GUIDs (possibleAnswers[*].id)", ansid_occ)

    if not args.fix:
        # Exit codes: 0 = clean, 1 = duplicates found, 2 = file/format error
        if dup_count > 0:
            print(f"\nSummary: Found {dup_count} duplicate key group(s).")
            sys.exit(1)
        print("\nSummary: No duplicates found.")
        sys.exit(0)

    # Fix mode — only replace the *extra* occurrences of each duplicate ID, not the first occurrence
    print("\n🛠  Fix mode enabled: generating new GUIDs for duplicate IDs...")

    # Build fast lookup of which positions to replace
    q_dupes = find_duplicates(qid_occ)
    a_dupes = find_duplicates(ansid_occ)

    replacements = {}  # (where_string) -> new_id
    id_rewrite_map = {}  # (old_id at a specific position) -> new_id (for logging consistency)

    # Replace duplicate question IDs (keep first occurrence as-is)
    for dup_id, locs in q_dupes.items():
        # From the second occurrence onwards, reassign
        for where in locs[1:]:
            # where looks like "question[QI] id"
            qi = int(where.split("question[")[1].split("]")[0])
            new_id = generate_unique_uuid(all_ids)
            # Apply in structure
            questions[qi]["id"] = new_id
            replacements[where] = new_id
            id_rewrite_map[(dup_id, where)] = new_id

    # Replace duplicate answer IDs (keep first occurrence as-is)
    for dup_id, locs in a_dupes.items():
        for where in locs[1:]:
            # where looks like "question[QI].possibleAnswers[AI] id"
            left, _ = where.split("] id")
            qi = int(left.split("question[")[1].split("]")[0])
            ai = int(left.split("possibleAnswers[")[1].split("]")[0])
            new_id = generate_unique_uuid(all_ids)
            questions[qi]["possibleAnswers"][ai]["id"] = new_id
            replacements[where] = new_id
            id_rewrite_map[(dup_id, where)] = new_id

    # Write output (in-place or to --output)
    out_path = args.output or args.path
    if args.fix and not args.output and not args.no_backup:
        # Make a backup only for true in-place writes
        bak_path = args.path + ".bak"
        try:
            shutil.copyfile(args.path, bak_path)
            print(f"🗂  Backup created: {bak_path}")
        except Exception as e:
            print(f"⚠️  Could not create backup {bak_path}: {e}", file=sys.stderr)

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"💾 Wrote fixed JSON to: {out_path}")
    except Exception as e:
        print(f"Failed to write JSON to {out_path}: {e}", file=sys.stderr)
        sys.exit(2)

    # Print a clear mapping of all changes
    if replacements:
        print("\n🔁 ID replacements (old position → new GUID):")
        for where, new_id in sorted(replacements.items()):
            print(f"  {where}  →  {new_id}")
    else:
        print("\nNo replacements were necessary (unexpected in --fix mode).")

    print("\nDone.")
    sys.exit(0)

if __name__ == "__main__":
    main()
