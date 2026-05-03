"""
Seed test data · 50 programs + 3 schools + admins + psychologists + students.
Idempotente: rerun is safe (UPSERT). Use --clean to remove all seeded data.

Usage:
    ./venv/bin/python scripts/seed_test_data.py        # seed
    ./venv/bin/python scripts/seed_test_data.py --clean  # remove all seeded data

Convention: all seeded entities have prefix `seed-` in slugs/program_ids/emails
for easy identification and cleanup. School emails are kept clean for realism
but tagged via school slug prefix.
"""
import os
import sys
import uuid
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path

import bcrypt
import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
DB_URL = os.environ["DATABASE_URL"]

PASSWORD_PLAIN = "Test2026!"
PASSWORD_HASH = bcrypt.hashpw(PASSWORD_PLAIN.encode(), bcrypt.gensalt()).decode()


# ============================================================
# 50 PROGRAMS
# ============================================================
COUNTRIES_CITIES = [
    ("USA", "Boston"), ("USA", "New York"), ("USA", "San Francisco"), ("USA", "Los Angeles"),
    ("UK", "London"), ("UK", "Edinburgh"), ("UK", "Cambridge"),
    ("Canada", "Toronto"), ("Canada", "Vancouver"), ("Canada", "Montreal"),
    ("Spain", "Barcelona"), ("Spain", "Madrid"),
    ("Germany", "Berlin"), ("Germany", "Munich"),
    ("Australia", "Sydney"), ("Australia", "Melbourne"),
    ("Argentina", "Buenos Aires"),
    ("Colombia", "Bogotá"), ("Colombia", "Medellín"),
    ("Mexico", "CDMX"),
    ("Chile", "Santiago"),
    ("Italy", "Milán"),
    ("France", "París"),
    ("Netherlands", "Amsterdam"),
]

PROGRAMS_DATA = [
    # USA (10)
    ("BSc Cognitive Science", "Harvard University", "USA", "Cambridge", "bachelor", "Ciencias", "Cognitive Science", 48, 78000, "USD", "premium", "preferential", "EN"),
    ("BA Computer Science", "Stanford University", "USA", "Stanford", "bachelor", "Tecnología", "Computer Science", 48, 82000, "USD", "premium", "standard", "EN"),
    ("BSc Business Analytics", "MIT", "USA", "Cambridge", "bachelor", "Negocios", "Business Analytics", 48, 80000, "USD", "premium", "standard", "EN"),
    ("BA Design + Psychology", "NYU", "USA", "New York", "bachelor", "Artes", "Design", 48, 58000, "USD", "high", "standard", "EN"),
    ("BSc Data Science", "UC Berkeley", "USA", "San Francisco", "bachelor", "Tecnología", "Data Science", 48, 45000, "USD", "high", "standard", "EN"),
    ("BA Communications", "USC", "USA", "Los Angeles", "bachelor", "Comunicación", "Media", 48, 62000, "USD", "high", "preferential", "EN"),
    ("BSc Mechanical Engineering", "Carnegie Mellon", "USA", "Pittsburgh", "bachelor", "Ingeniería", "Mechanical", 48, 60000, "USD", "high", "standard", "EN"),
    ("BA International Relations", "Georgetown", "USA", "Washington DC", "bachelor", "Ciencias Sociales", "International Relations", 48, 62000, "USD", "high", "standard", "EN"),
    ("BSc Biomedical Engineering", "Johns Hopkins", "USA", "Baltimore", "bachelor", "Salud", "Biomedical", 48, 60000, "USD", "high", "standard", "EN"),
    ("BFA Film", "UCLA", "USA", "Los Angeles", "bachelor", "Artes", "Film", 48, 45000, "USD", "high", "standard", "EN"),
    # UK (8)
    ("BSc Cognitive Science", "University of Edinburgh", "UK", "Edinburgh", "bachelor", "Ciencias", "Cognitive Science", 48, 32000, "USD", "mid", "preferential", "EN"),
    ("BSc Computer Science", "Imperial College London", "UK", "London", "bachelor", "Tecnología", "Computer Science", 36, 42000, "USD", "high", "preferential", "EN"),
    ("BA Economics", "London School of Economics", "UK", "London", "bachelor", "Negocios", "Economics", 36, 38000, "USD", "high", "standard", "EN"),
    ("BSc Mathematics", "University of Cambridge", "UK", "Cambridge", "bachelor", "Ciencias", "Mathematics", 36, 36000, "USD", "high", "standard", "EN"),
    ("BA Liberal Arts", "Durham University", "UK", "Durham", "bachelor", "Artes", "Liberal Arts", 36, 28000, "USD", "mid", "standard", "EN"),
    ("BSc Psychology", "University of Manchester", "UK", "Manchester", "bachelor", "Ciencias Sociales", "Psychology", 36, 26000, "USD", "mid", "standard", "EN"),
    ("BA Architecture", "Bartlett (UCL)", "UK", "London", "bachelor", "Artes", "Architecture", 60, 35000, "USD", "high", "standard", "EN"),
    ("BSc Renewable Energy", "Imperial College London", "UK", "London", "bachelor", "Ingeniería", "Energy", 36, 40000, "USD", "high", "standard", "EN"),
    # Canada (5)
    ("BSc Computer Science", "University of Toronto", "Canada", "Toronto", "bachelor", "Tecnología", "Computer Science", 48, 45000, "USD", "high", "preferential", "EN"),
    ("BSc Engineering Physics", "University of British Columbia", "Canada", "Vancouver", "bachelor", "Ingeniería", "Physics", 48, 40000, "USD", "high", "standard", "EN"),
    ("BA Cognitive Science", "McGill University", "Canada", "Montreal", "bachelor", "Ciencias", "Cognitive Science", 48, 35000, "USD", "high", "standard", "EN-FR"),
    ("BSc Game Design", "Sheridan College", "Canada", "Toronto", "bachelor", "Tecnología", "Game Design", 48, 25000, "USD", "mid", "preferential", "EN"),
    ("BA International Business", "Queen's University", "Canada", "Kingston", "bachelor", "Negocios", "International Business", 48, 38000, "USD", "high", "standard", "EN"),
    # Spain (5)
    ("Grado en Diseño", "ELISAVA", "Spain", "Barcelona", "bachelor", "Artes", "Design", 48, 18000, "EUR", "mid", "preferential", "ES"),
    ("Grado en Ingeniería Informática", "Universidad Politécnica Madrid", "Spain", "Madrid", "bachelor", "Tecnología", "Computer Engineering", 48, 8000, "EUR", "low", "preferential", "ES"),
    ("Grado en ADE", "ESADE", "Spain", "Barcelona", "bachelor", "Negocios", "Business Administration", 48, 26000, "EUR", "mid", "standard", "ES-EN"),
    ("Grado en Comunicación", "Universidad de Navarra", "Spain", "Pamplona", "bachelor", "Comunicación", "Communications", 48, 12000, "EUR", "mid", "standard", "ES"),
    ("Grado en Psicología", "Universitat de Barcelona", "Spain", "Barcelona", "bachelor", "Ciencias Sociales", "Psychology", 48, 7000, "EUR", "low", "standard", "ES"),
    # Germany (4)
    ("BSc Computer Science", "TU Munich", "Germany", "Munich", "bachelor", "Tecnología", "Computer Science", 36, 2000, "EUR", "low", "preferential", "EN-DE"),
    ("BSc Mechanical Engineering", "RWTH Aachen", "Germany", "Aachen", "bachelor", "Ingeniería", "Mechanical", 36, 1500, "EUR", "low", "standard", "DE"),
    ("BA International Business", "ESB Business School", "Germany", "Reutlingen", "bachelor", "Negocios", "International Business", 36, 5000, "EUR", "low", "standard", "EN-DE"),
    ("BSc Sustainable Energy", "Hochschule München", "Germany", "Munich", "bachelor", "Ingeniería", "Energy", 36, 2000, "EUR", "low", "standard", "DE"),
    # Australia (3)
    ("BSc Computer Science", "University of Melbourne", "Australia", "Melbourne", "bachelor", "Tecnología", "Computer Science", 36, 38000, "USD", "high", "standard", "EN"),
    ("BA Communications", "RMIT University", "Australia", "Melbourne", "bachelor", "Comunicación", "Communications", 36, 32000, "USD", "high", "standard", "EN"),
    ("BSc Marine Biology", "James Cook University", "Australia", "Townsville", "bachelor", "Ciencias", "Marine Biology", 36, 30000, "USD", "mid", "standard", "EN"),
    # Argentina (3)
    ("Licenciatura en Economía", "Universidad de San Andrés", "Argentina", "Buenos Aires", "bachelor", "Negocios", "Economics", 48, 14000, "USD", "mid", "preferential", "ES"),
    ("Licenciatura en Diseño", "Universidad Torcuato Di Tella", "Argentina", "Buenos Aires", "bachelor", "Artes", "Design", 48, 16000, "USD", "mid", "preferential", "ES"),
    ("Licenciatura en Ingeniería", "ITBA", "Argentina", "Buenos Aires", "bachelor", "Ingeniería", "Engineering", 60, 12000, "USD", "mid", "standard", "ES"),
    # Colombia (5)
    ("Pregrado en Psicología", "Universidad de los Andes", "Colombia", "Bogotá", "bachelor", "Ciencias Sociales", "Psychology", 60, 8000, "USD", "low", "preferential", "ES"),
    ("Ingeniería de Sistemas", "Universidad EAFIT", "Colombia", "Medellín", "bachelor", "Tecnología", "Computer Engineering", 60, 7000, "USD", "low", "preferential", "ES"),
    ("Administración de Empresas", "CESA", "Colombia", "Bogotá", "bachelor", "Negocios", "Business", 48, 9000, "USD", "low", "standard", "ES"),
    ("Diseño Gráfico", "Universidad Javeriana", "Colombia", "Bogotá", "bachelor", "Artes", "Graphic Design", 48, 6000, "USD", "low", "standard", "ES"),
    ("Comunicación Social", "Universidad del Norte", "Colombia", "Barranquilla", "bachelor", "Comunicación", "Media", 48, 6000, "USD", "low", "standard", "ES"),
    # Mexico (2)
    ("Lic. en Ciencias de la Computación", "ITAM", "Mexico", "CDMX", "bachelor", "Tecnología", "Computer Science", 48, 18000, "USD", "mid", "standard", "ES"),
    ("Lic. en Diseño Industrial", "Tec de Monterrey", "Mexico", "Monterrey", "bachelor", "Artes", "Industrial Design", 48, 22000, "USD", "mid", "preferential", "ES"),
    # Chile (1)
    ("Ingeniería Comercial", "Universidad Adolfo Ibáñez", "Chile", "Santiago", "bachelor", "Negocios", "Business", 60, 11000, "USD", "mid", "standard", "ES"),
    # Italy (2)
    ("BA Fashion Design", "Politecnico di Milano", "Italy", "Milán", "bachelor", "Artes", "Fashion Design", 36, 8000, "EUR", "low", "standard", "IT-EN"),
    ("BSc Architecture", "IUAV Venice", "Italy", "Venecia", "bachelor", "Artes", "Architecture", 60, 7000, "EUR", "low", "standard", "IT-EN"),
    # France (1)
    ("BBA International", "ESSEC Business School", "France", "París", "bachelor", "Negocios", "Business", 48, 18000, "EUR", "mid", "preferential", "EN-FR"),
    # Netherlands (1)
    ("BSc Liberal Arts and Sciences", "University of Amsterdam", "Netherlands", "Amsterdam", "bachelor", "Artes", "Liberal Arts", 36, 12000, "EUR", "low", "preferential", "EN"),
]


# ============================================================
# 3 SCHOOLS
# ============================================================
SCHOOLS_DATA = [
    {
        "slug": "seed-cumbres",
        "name": "Colegio Cumbres",
        "license_tier": "gold",
        "license_seats": 200,
        "school_admin": ("admin.cumbres@grasshopper.dev", "María González · Directora Cumbres"),
        "psychologists": [
            ("psy.cumbres1@grasshopper.dev", "Laura Restrepo"),
            ("psy.cumbres2@grasshopper.dev", "Andrés Rojas"),
        ],
    },
    {
        "slug": "seed-san-marcos",
        "name": "Liceo San Marcos",
        "license_tier": "silver",
        "license_seats": 100,
        "school_admin": ("admin.sanmarcos@grasshopper.dev", "Carlos Pérez · Coordinador San Marcos"),
        "psychologists": [
            ("psy.sanmarcos1@grasshopper.dev", "Carolina Vargas"),
            ("psy.sanmarcos2@grasshopper.dev", "Felipe Hernández"),
        ],
    },
    {
        "slug": "seed-campestre",
        "name": "Gimnasio Campestre",
        "license_tier": "bronze",
        "license_seats": 50,
        "school_admin": ("admin.campestre@grasshopper.dev", "Ana Martínez · Directora Campestre"),
        "psychologists": [
            ("psy.campestre1@grasshopper.dev", "Camila Ortega"),
            ("psy.campestre2@grasshopper.dev", "Daniel Salazar"),
        ],
    },
]


# ============================================================
# SUPER ADMINS extra (Grasshopper team · solo JP + 2 staff que mantienen super_admin)
# ============================================================
SUPER_ADMINS_EXTRA = [
    ("veronica@stayirrelevant.com", "Verónica Bustamante"),
    ("sebastian@stayirrelevant.com", "Sebastián García"),
]


# ============================================================
# GH ADVISORS (orientadores Grasshopper · GH-ROLES-001)
# ============================================================
GH_ADVISORS = [
    ("advisor1.gh@stayirrelevant.com", "Carolina Méndez"),
    ("advisor2.gh@stayirrelevant.com", "Mateo Lozano"),
]


# ============================================================
# GH COMMERCIALS (asesoras comerciales · GH-ROLES-001)
# ============================================================
GH_COMMERCIALS = [
    ("commercial1.gh@stayirrelevant.com", "Daniela Ríos"),
    ("commercial2.gh@stayirrelevant.com", "Joaquín Pérez"),
]


# ============================================================
# B2C STUDENTS (no school_id · target del gh_advisor)
# ============================================================
B2C_STUDENTS = [
    ("b2c.alumno1@grasshopper.dev", "Alejandro Mejía",   "COMPLETED",   True,  "B2"),
    ("b2c.alumno2@grasshopper.dev", "Valentina Cuervo",  "IN_PROGRESS", True,  "B1"),
    ("b2c.alumno3@grasshopper.dev", "Tomás Restrepo",    "IN_PROGRESS", False, None),
    ("b2c.alumno4@grasshopper.dev", "Laura Henao",       "NOT_STARTED", False, None),
    ("b2c.alumno5@grasshopper.dev", "Mariana Echeverri", "COMPLETED",   True,  "C1"),
]


# ============================================================
# B2B STUDENTS marcados con contact request (3 students existentes)
# Tomamos uno de cada colegio · status alterno para variedad demo.
# ============================================================
B2B_CONTACT_REQUEST_TARGETS = [
    # (email_alumno, status, message)
    ("alumno5.cumbr@grasshopper.dev",   "pending",     "Quiero más info sobre programas en USA · presupuesto medio."),
    ("alumno6.san-m@grasshopper.dev",   "in_progress", "Ya hablé con mi mamá · necesitamos opciones sin TOEFL."),
    ("alumno7.campe@grasshopper.dev",   "pending",     "Estoy entre Diseño y Comunicación · me gustaría guía."),
]


# ============================================================
# 30 STUDENTS (10 per school) with varying journey states
# ============================================================
STUDENT_NAMES = [
    "María Pérez", "Juan García", "Ana Rodríguez", "Pedro Martínez", "Sofía López",
    "Diego Ramírez", "Valentina Torres", "Mateo Castro", "Camila Vargas", "Sebastián Rojas",
    "Isabella Gómez", "Daniel Mora", "Lucía Hernández", "Tomás Silva", "Emma Jiménez",
    "Nicolás Ortiz", "Mariana Flores", "Andrés Restrepo", "Catalina Mendoza", "Felipe Cárdenas",
    "Paula Salazar", "Santiago Romero", "Renata Acosta", "Joaquín Pinto", "Antonella Quintero",
    "Emiliano Bedoya", "Manuela Suárez", "Maximiliano Villa", "Olivia Ríos", "Esteban Mejía",
]

# Journey distributions per school: 3 NOT_STARTED · 5 IN_PROGRESS · 2 COMPLETED


def _create_user(cur, email, name, role, school_id=None, password_hash=PASSWORD_HASH,
                 onboarding_status="NOT_STARTED", english_completed=False, english_level=None):
    cur.execute("""
        INSERT INTO users (id, created_at, updated_at, email, hashed_password, name, role,
                           school_id, is_active, onboarding_status, onboarding_answers,
                           preferred_countries, english_test_completed, english_cefr_level)
        VALUES (%s, NOW(), NOW(), %s, %s, %s, %s, %s, true, %s, '{}', '[]', %s, %s)
        ON CONFLICT (email) DO UPDATE SET
            hashed_password = EXCLUDED.hashed_password,
            role = EXCLUDED.role,
            school_id = EXCLUDED.school_id,
            is_active = true,
            updated_at = NOW()
        RETURNING id
    """, (str(uuid.uuid4()), email, password_hash, name, role, school_id,
          onboarding_status, english_completed, english_level))
    return cur.fetchone()[0]


def seed():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    print("=" * 60)
    print("GRASSHOPPER · TEST DATA SEEDING")
    print("=" * 60)

    # ---- 1. Programs (50) ----
    print("\n[1/6] Programs...")
    for idx, p in enumerate(PROGRAMS_DATA, 1):
        program_id = f"SEED-{idx:03d}"
        slug = f"seed-{p[0].lower().replace(' ', '-').replace('.', '')}-{idx:03d}"
        cur.execute("""
            INSERT INTO programs (id, program_id, name, slug, country, city, institution,
                                  type, area, subject, duration_months, cost_total, currency,
                                  budget_tier, alliance_type, language_requirement, active,
                                  raw, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true,
                    '{}', NOW(), NOW())
            ON CONFLICT (program_id) DO UPDATE SET
                name = EXCLUDED.name, country = EXCLUDED.country, city = EXCLUDED.city,
                institution = EXCLUDED.institution, cost_total = EXCLUDED.cost_total,
                budget_tier = EXCLUDED.budget_tier, updated_at = NOW()
        """, (str(uuid.uuid4()), program_id, p[0], slug, p[2], p[3], p[1], p[4],
              p[5], p[6], p[7], p[8], p[9], p[10], p[11], p[12]))
    print(f"  ✓ {len(PROGRAMS_DATA)} programas seeded")

    # ---- 2. Super admins + GH internal team (advisor + commercial) ----
    print("\n[2/6] Super admins · GH advisors · GH commercials...")
    for email, name in SUPER_ADMINS_EXTRA:
        _create_user(cur, email, name, "SUPER_ADMIN")
        print(f"  ✓ super_admin   · {email} · {name}")
    for email, name in GH_ADVISORS:
        _create_user(cur, email, name, "GH_ADVISOR")
        print(f"  ✓ gh_advisor    · {email} · {name}")
    for email, name in GH_COMMERCIALS:
        _create_user(cur, email, name, "GH_COMMERCIAL")
        print(f"  ✓ gh_commercial · {email} · {name}")

    # ---- 3. Schools + licenses + admins + psychologists ----
    print("\n[3/6] Schools + licenses + admins + psychologists...")
    school_ids = {}
    for s in SCHOOLS_DATA:
        # School
        expires = datetime.utcnow() + timedelta(days=365)
        cur.execute("""
            INSERT INTO schools (id, created_at, updated_at, name, slug, license_active, license_expires_at)
            VALUES (%s, NOW(), NOW(), %s, %s, true, %s)
            ON CONFLICT (slug) DO UPDATE SET
                name = EXCLUDED.name, license_active = true, archived_at = NULL,
                license_expires_at = EXCLUDED.license_expires_at, updated_at = NOW()
            RETURNING id
        """, (str(uuid.uuid4()), s["name"], s["slug"], expires))
        school_id = cur.fetchone()[0]
        school_ids[s["slug"]] = school_id

        # License
        cur.execute("""
            INSERT INTO licenses (id, school_id, tier, seats, starts_at, expires_at, status,
                                  created_at, updated_at)
            VALUES (%s, %s, %s, %s, NOW(), %s, 'active', NOW(), NOW())
            ON CONFLICT DO NOTHING
        """, (str(uuid.uuid4()), school_id, s["license_tier"], s["license_seats"], expires))

        # School admin
        admin_email, admin_name = s["school_admin"]
        _create_user(cur, admin_email, admin_name, "SCHOOL_ADMIN", school_id=school_id)

        # Psychologists
        for p_email, p_name in s["psychologists"]:
            _create_user(cur, p_email, p_name, "PSYCHOLOGIST", school_id=school_id)

        print(f"  ✓ {s['name']} ({s['slug']}) · admin: {admin_email} · 2 psychologists")

    # ---- 4. Students (10 per school = 30 total) ----
    print("\n[4/6] Students (30 total · 10 per school)...")
    student_idx = 0
    statuses_distrib = (
        ["NOT_STARTED"] * 3 +
        ["IN_PROGRESS"] * 5 +
        ["COMPLETED"] * 2
    )
    for s in SCHOOLS_DATA:
        school_id = school_ids[s["slug"]]
        school_short = s["slug"].replace("seed-", "")[:5]
        for i in range(10):
            name = STUDENT_NAMES[student_idx]
            student_idx += 1
            email = f"alumno{i+1}.{school_short}@grasshopper.dev"
            status = statuses_distrib[i]
            english_completed = (status != "NOT_STARTED")
            english_level = ["A2", "B1", "B2", "C1"][i % 4] if english_completed else None
            uid = _create_user(cur, email, name, "STUDENT", school_id=school_id,
                              onboarding_status=status, english_completed=english_completed,
                              english_level=english_level)

            # Sample vocational tests for IN_PROGRESS and COMPLETED students
            if status == "IN_PROGRESS":
                # 1-2 tests
                tests = ["riasec", "big5"][:1 + (i % 2)]
                for tid in tests:
                    cur.execute("""
                        INSERT INTO vocational_test_results (id, user_id, created_at, test_id,
                                                             answers, scores, source)
                        VALUES (%s, %s, NOW(), %s, '{}', %s, 'internal')
                        ON CONFLICT DO NOTHING
                    """, (str(uuid.uuid4()), uid, tid, json.dumps({"sample": "scores"})))
            elif status == "COMPLETED":
                # 4 tests
                for tid in ["riasec", "big5", "mbti", "istrong"]:
                    cur.execute("""
                        INSERT INTO vocational_test_results (id, user_id, created_at, test_id,
                                                             answers, scores, source)
                        VALUES (%s, %s, NOW(), %s, '{}', %s, 'internal')
                        ON CONFLICT DO NOTHING
                    """, (str(uuid.uuid4()), uid, tid, json.dumps({"sample": "scores"})))

        print(f"  ✓ 10 students en {s['name']} (3 not_started · 5 in_progress · 2 completed)")

    # ---- 5. B2C students (no school_id) · target gh_advisor ----
    print("\n[5/6] B2C students (no school_id · 5 alumnos)...")
    for email, name, status_val, eng_done, eng_lvl in B2C_STUDENTS:
        _create_user(
            cur,
            email,
            name,
            "STUDENT",
            school_id=None,
            onboarding_status=status_val,
            english_completed=eng_done,
            english_level=eng_lvl,
        )
        print(f"  ✓ {email} · {name} · {status_val.lower()}")

    # ---- 6. Mark 3 B2B students as gh_contact_requested (demo seed) ----
    print("\n[6/6] Contact requests (3 alumnos B2B opted-in al equipo GH)...")
    for email, status_val, message in B2B_CONTACT_REQUEST_TARGETS:
        cur.execute(
            """
            UPDATE users
            SET gh_contact_requested_at = NOW() - (random() * INTERVAL '5 days'),
                gh_contact_status = %s,
                gh_contact_message = %s,
                updated_at = NOW()
            WHERE email = %s
            """,
            (status_val, message, email),
        )
        if cur.rowcount:
            print(f"  ✓ {email} · status={status_val}")
        else:
            print(f"  ! {email} · NOT FOUND (skipped)")

    conn.commit()
    cur.close()
    conn.close()

    print("\n" + "=" * 60)
    print("✓ SEED COMPLETO")
    print("=" * 60)
    print_credentials()


def clean():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    print("=" * 60)
    print("CLEANING ALL SEEDED DATA")
    print("=" * 60)

    # Borrar emails seed (students + admins + psychologists + super admins + gh team)
    extra_emails = (
        tuple(e for e, _ in SUPER_ADMINS_EXTRA)
        + tuple(e for e, _ in GH_ADVISORS)
        + tuple(e for e, _ in GH_COMMERCIALS)
    )
    cur.execute("""
        DELETE FROM users WHERE email LIKE '%@grasshopper.dev' AND email != 'jp@grasshopper.dev'
        OR email IN %s
    """, (extra_emails,))
    print(f"  ✓ {cur.rowcount} users deleted")

    # Borrar schools (cascade licenses)
    cur.execute("DELETE FROM licenses WHERE school_id IN (SELECT id FROM schools WHERE slug LIKE 'seed-%')")
    print(f"  ✓ {cur.rowcount} licenses deleted")
    cur.execute("DELETE FROM schools WHERE slug LIKE 'seed-%'")
    print(f"  ✓ {cur.rowcount} schools deleted")

    # Borrar programs seed
    cur.execute("DELETE FROM programs WHERE program_id LIKE 'SEED-%'")
    print(f"  ✓ {cur.rowcount} programs deleted")

    conn.commit()
    cur.close()
    conn.close()
    print("\n✓ CLEAN COMPLETO")


def print_credentials():
    print(f"\nPASSWORD GLOBAL para todos los seed users: {PASSWORD_PLAIN}")
    print("\n--- SUPER ADMINS (vista global · staff Grasshopper · CRUD total) ---")
    print("  jp@grasshopper.dev               · JpLocal2026!  (creado previamente)")
    for email, name in SUPER_ADMINS_EXTRA:
        print(f"  {email:<33}· {PASSWORD_PLAIN}  · {name}")

    print("\n--- GH ADVISORS (orientadores GH · /gh/students) ---")
    for email, name in GH_ADVISORS:
        print(f"  {email:<33}· {PASSWORD_PLAIN}  · {name}")

    print("\n--- GH COMMERCIALS (asesoras comerciales · /gh/leads + Bitrix) ---")
    for email, name in GH_COMMERCIALS:
        print(f"  {email:<33}· {PASSWORD_PLAIN}  · {name}")

    print("\n--- B2C STUDENTS (sin school · captados directo por GH) ---")
    for email, name, status_val, _, _ in B2C_STUDENTS:
        print(f"  {email:<33}· {PASSWORD_PLAIN}  · {name} · {status_val.lower()}")

    print("\n--- B2B STUDENTS con contact request a GH (demo data) ---")
    for email, status_val, _ in B2B_CONTACT_REQUEST_TARGETS:
        print(f"  {email:<33}· {PASSWORD_PLAIN}  · status={status_val}")

    print("\n--- SCHOOL ADMINS (1 por colegio · panel /school) ---")
    for s in SCHOOLS_DATA:
        e, n = s["school_admin"]
        print(f"  {e:<32}· {PASSWORD_PLAIN}  · {n} · {s['name']}")

    print("\n--- PSYCHOLOGISTS (2 por colegio · read-only /school) ---")
    for s in SCHOOLS_DATA:
        for e, n in s["psychologists"]:
            print(f"  {e:<32}· {PASSWORD_PLAIN}  · {n} · {s['name']}")

    print("\n--- STUDENTS (10 por colegio · 30 total) ---")
    for s in SCHOOLS_DATA:
        short = s["slug"].replace("seed-", "")[:5]
        print(f"  {s['name']}: alumno1.{short}@grasshopper.dev → alumno10.{short}@grasshopper.dev (password: {PASSWORD_PLAIN})")
        print(f"    · 3 not_started · 5 in_progress (1-2 tests) · 2 completed (4 tests)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true", help="Remove all seeded data")
    args = parser.parse_args()
    if args.clean:
        clean()
    else:
        seed()
