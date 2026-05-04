"""Seed psychometric tests for the gh_advisor demo · 2026-05-04.

After running `seed_test_data.py`, this complementary seed:
- Adds 4-5 vocational tests to each B2C student (so the advisor sees the
  full psychometric view).
- Adds 1-2 tests to each B2B student that has a `gh_contact_requested_at`
  set (so the advisor can preview them too).

Idempotent: re-running is safe (UPSERT on (user_id, test_id) unique
constraint defined in models.py).

Usage:
    ./venv/bin/python scripts/seed_advisor_demo.py        # seed
    ./venv/bin/python scripts/seed_advisor_demo.py --clean  # remove only seeded tests
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
DB_URL = os.environ["DATABASE_URL"]


# Distinct test profiles · varied to make the cross-pattern UI rich.
PROFILES = [
    {
        "name": "investigador-introvertido",
        "tests": {
            "riasec": {"R": 35, "I": 88, "A": 55, "S": 40, "E": 30, "C": 50},
            "big5": {"openness": 82, "conscientiousness": 70, "extraversion": 35, "agreeableness": 60, "neuroticism": 45},
            "mbti": {"type": "INTJ"},
            "istrong": {"science": 78, "research": 80, "math": 72, "arts": 40, "social": 35, "business": 45},
            "values": {"autonomy": 85, "intellectual_challenge": 90, "stability": 70, "income": 50, "altruism": 55, "creativity": 65},
        },
    },
    {
        "name": "social-extrovertido",
        "tests": {
            "riasec": {"R": 30, "I": 50, "A": 65, "S": 92, "E": 75, "C": 45},
            "big5": {"openness": 70, "conscientiousness": 60, "extraversion": 85, "agreeableness": 80, "neuroticism": 35},
            "mbti": {"type": "ENFJ"},
            "istrong": {"social": 88, "communication": 82, "arts": 70, "business": 65, "science": 35, "research": 40},
            "values": {"altruism": 90, "social_impact": 85, "creativity": 70, "stability": 60, "income": 50, "autonomy": 65},
        },
    },
    {
        "name": "creativo-emprendedor",
        "tests": {
            "riasec": {"R": 40, "I": 55, "A": 85, "S": 60, "E": 78, "C": 35},
            "big5": {"openness": 88, "conscientiousness": 50, "extraversion": 70, "agreeableness": 55, "neuroticism": 50},
            "mbti": {"type": "ENFP"},
            "istrong": {"arts": 90, "design": 85, "business": 70, "communication": 75, "social": 55, "science": 40},
            "values": {"creativity": 92, "autonomy": 80, "income": 70, "social_impact": 65, "stability": 40, "altruism": 60},
        },
    },
    {
        "name": "convencional-estable",
        "tests": {
            "riasec": {"R": 50, "I": 45, "A": 30, "S": 55, "E": 60, "C": 88},
            "big5": {"openness": 50, "conscientiousness": 88, "extraversion": 55, "agreeableness": 70, "neuroticism": 40},
            "mbti": {"type": "ESTJ"},
            "istrong": {"business": 82, "social": 60, "research": 45, "communication": 65, "arts": 30, "science": 50},
            "values": {"stability": 92, "income": 80, "autonomy": 50, "altruism": 55, "creativity": 35, "intellectual_challenge": 60},
        },
    },
    {
        "name": "ambivalente-explorando",
        "tests": {
            "riasec": {"R": 50, "I": 60, "A": 65, "S": 70, "E": 55, "C": 50},
            "big5": {"openness": 65, "conscientiousness": 55, "extraversion": 50, "agreeableness": 65, "neuroticism": 55},
            "mbti": {"type": "INFP"},
            "istrong": {"arts": 65, "social": 60, "communication": 65, "research": 55, "business": 45, "science": 50},
            "values": {"creativity": 70, "altruism": 70, "intellectual_challenge": 65, "autonomy": 60, "stability": 55, "income": 45},
        },
    },
    {
        "name": "tecnico-pragmatico",
        "tests": {
            "riasec": {"R": 85, "I": 70, "A": 30, "S": 35, "E": 45, "C": 55},
            "big5": {"openness": 60, "conscientiousness": 75, "extraversion": 40, "agreeableness": 50, "neuroticism": 35},
            "mbti": {"type": "ISTP"},
            "istrong": {"science": 78, "math": 80, "research": 70, "business": 50, "arts": 35, "social": 40},
            "values": {"intellectual_challenge": 80, "autonomy": 75, "income": 70, "stability": 65, "creativity": 50, "altruism": 40},
        },
    },
]


# B2C students (5) · each gets a different profile (one to spare)
B2C_EMAILS = [
    "b2c.alumno1@grasshopper.dev",
    "b2c.alumno2@grasshopper.dev",
    "b2c.alumno3@grasshopper.dev",
    "b2c.alumno4@grasshopper.dev",
    "b2c.alumno5@grasshopper.dev",
]


def _seed_tests_for_user(cur, user_id, profile, tests_to_seed=None, clean=False):
    """Seed the chosen tests for a user. Use UPSERT on (user_id, test_id)."""
    selected = tests_to_seed or list(profile["tests"].keys())
    if clean:
        cur.execute(
            "DELETE FROM vocational_test_results WHERE user_id = %s AND test_id = ANY(%s)",
            (user_id, selected),
        )
        return len(selected)
    inserted = 0
    for tid in selected:
        scores = profile["tests"].get(tid)
        if scores is None:
            continue
        # ON CONFLICT (user_id, test_id) DO UPDATE so a re-run refreshes scores
        cur.execute(
            """
            INSERT INTO vocational_test_results (id, user_id, created_at, test_id,
                                                 answers, scores, source)
            VALUES (%s, %s, NOW() - (random() * INTERVAL '20 days'),
                    %s, %s::jsonb, %s::jsonb, 'internal')
            ON CONFLICT (user_id, test_id) DO UPDATE
                SET scores = EXCLUDED.scores,
                    created_at = vocational_test_results.created_at
            """,
            (
                str(uuid.uuid4()),
                user_id,
                tid,
                json.dumps({"profile": profile["name"]}),
                json.dumps(scores),
            ),
        )
        inserted += 1
    return inserted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true", help="Remove seeded tests (advisor demo subset)")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    print("=" * 60)
    print("ADVISOR CLINICAL DEMO SEED · 2026-05-04")
    print("=" * 60)

    # ---- 1. B2C students · all 6 tests each (rotates through profiles) ----
    print("\n[1/2] B2C students · 5 alumnos · 5 tests cada uno (rotando perfiles)...")
    for idx, email in enumerate(B2C_EMAILS):
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        row = cur.fetchone()
        if not row:
            print(f"  ! {email} not found (run seed_test_data.py first)")
            continue
        user_id = row[0]
        profile = PROFILES[idx % len(PROFILES)]
        # Subset · 5 tests (skip 1 randomly to vary)
        tests = list(profile["tests"].keys())
        n = _seed_tests_for_user(cur, user_id, profile, tests_to_seed=tests, clean=args.clean)
        action = "removed" if args.clean else "seeded"
        print(f"  - {email} · {profile['name']} · {n} tests {action}")

    # ---- 2. B2B students with gh_contact_requested · 1-2 tests each ----
    print("\n[2/2] B2B students con contact_request · 1-2 tests cada uno...")
    cur.execute(
        """
        SELECT id, email
        FROM users
        WHERE role::text = 'STUDENT'
          AND school_id IS NOT NULL
          AND gh_contact_requested_at IS NOT NULL
        ORDER BY created_at ASC
        """
    )
    rows = cur.fetchall()
    for idx, (uid, email) in enumerate(rows):
        profile = PROFILES[(idx + 2) % len(PROFILES)]  # offset to differ from B2C
        # 1-2 tests · pick from riasec + big5
        tests_to_seed = ["riasec", "big5"] if idx % 2 == 0 else ["riasec"]
        n = _seed_tests_for_user(cur, uid, profile, tests_to_seed=tests_to_seed, clean=args.clean)
        action = "removed" if args.clean else "seeded"
        print(f"  - {email} · {profile['name']} · {n} tests {action}")

    conn.commit()
    cur.close()
    conn.close()

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
