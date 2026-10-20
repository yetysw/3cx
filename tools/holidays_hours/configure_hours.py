#!/usr/bin/env python3
"""
3CX - Configuration des jours fériés (VS/VD) et horaires de bureau

Usage:
    python3 configure_hours.py              # Applique tout
    python3 configure_hours.py --dry-run    # Aperçu sans modification
    python3 configure_hours.py --list       # Liste les départements
"""

import argparse
import json
import os
import sys

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =============================================================================
# CONNEXION
# =============================================================================
PBX_URL = os.environ.get("THREECX_URL", "https://pbx.example.com")
USERNAME = os.environ.get("THREECX_USER", "")
PASSWORD = os.environ.get("THREECX_PASSWORD", "")
SECURITY_CODE = os.environ.get("THREECX_SECURITY_CODE", "")

# =============================================================================
# HORAIRES DE BUREAU - 3 profils
# =============================================================================

# Type A : Lu-Jeu 08:00-11:59 + 13:30-17:30, Ven 08:00-11:59 + 13:30-17:00
HOURS_TYPE_A = {
    "Type": "SpecificHours",
    "Periods": [
        {"DayOfWeek": "Monday",    "Start": "08:00:00", "Stop": "11:59:00"},
        {"DayOfWeek": "Monday",    "Start": "13:30:00", "Stop": "17:30:00"},
        {"DayOfWeek": "Tuesday",   "Start": "08:00:00", "Stop": "11:59:00"},
        {"DayOfWeek": "Tuesday",   "Start": "13:30:00", "Stop": "17:30:00"},
        {"DayOfWeek": "Wednesday", "Start": "08:00:00", "Stop": "11:59:00"},
        {"DayOfWeek": "Wednesday", "Start": "13:30:00", "Stop": "17:30:00"},
        {"DayOfWeek": "Thursday",  "Start": "08:00:00", "Stop": "11:59:00"},
        {"DayOfWeek": "Thursday",  "Start": "13:30:00", "Stop": "17:30:00"},
        {"DayOfWeek": "Friday",    "Start": "08:00:00", "Stop": "11:59:00"},
        {"DayOfWeek": "Friday",    "Start": "13:30:00", "Stop": "17:00:00"},
    ],
}

# Type B (Montfort) : Lu-Jeu 08:00-11:59 + 13:30-17:30, Ven 08:00-11:59 uniquement
HOURS_TYPE_B = {
    "Type": "SpecificHours",
    "Periods": [
        {"DayOfWeek": "Monday",    "Start": "08:00:00", "Stop": "11:59:00"},
        {"DayOfWeek": "Monday",    "Start": "13:30:00", "Stop": "17:30:00"},
        {"DayOfWeek": "Tuesday",   "Start": "08:00:00", "Stop": "11:59:00"},
        {"DayOfWeek": "Tuesday",   "Start": "13:30:00", "Stop": "17:30:00"},
        {"DayOfWeek": "Wednesday", "Start": "08:00:00", "Stop": "11:59:00"},
        {"DayOfWeek": "Wednesday", "Start": "13:30:00", "Stop": "17:30:00"},
        {"DayOfWeek": "Thursday",  "Start": "08:00:00", "Stop": "11:59:00"},
        {"DayOfWeek": "Thursday",  "Start": "13:30:00", "Stop": "17:30:00"},
        {"DayOfWeek": "Friday",    "Start": "08:00:00", "Stop": "11:59:00"},
    ],
}

# Type C : Lu-Ven 08:00-11:59 (matin uniquement)
HOURS_TYPE_C = {
    "Type": "SpecificHours",
    "Periods": [
        {"DayOfWeek": "Monday",    "Start": "08:00:00", "Stop": "11:59:00"},
        {"DayOfWeek": "Tuesday",   "Start": "08:00:00", "Stop": "11:59:00"},
        {"DayOfWeek": "Wednesday", "Start": "08:00:00", "Stop": "11:59:00"},
        {"DayOfWeek": "Thursday",  "Start": "08:00:00", "Stop": "11:59:00"},
        {"DayOfWeek": "Friday",    "Start": "08:00:00", "Stop": "11:59:00"},
    ],
}

# =============================================================================
# JOURS FÉRIÉS VALAIS (VS) - 2026
# =============================================================================


def make_holiday(name, day, month, year=0, day_end=None, month_end=None,
                 year_end=None, is_recurrent=True, is_whole_day=True,
                 start_time=None, end_time=None, prompt=""):
    """Helper pour créer un objet Holiday 3CX."""
    if day_end is None:
        day_end = day
    if month_end is None:
        month_end = month
    if year_end is None:
        year_end = year

    if is_whole_day:
        time_start = "P0D"
        time_end = "P1D"
    else:
        time_start = _to_duration(start_time or "00:00")
        time_end = _to_duration(end_time or "00:00")

    return {
        "Name": name,
        "HolidayPrompt": prompt,
        "IsRecurrent": is_recurrent,
        "Day": day,
        "Month": month,
        "Year": 0 if is_recurrent else year,
        "TimeOfStartDate": time_start,
        "DayEnd": day_end,
        "MonthEnd": month_end,
        "YearEnd": 0 if is_recurrent else year_end,
        "TimeOfEndDate": time_end,
    }


def _to_duration(time_str):
    parts = time_str.split(":")
    h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    if h == 0 and m == 0:
        return "P0D"
    r = "PT"
    if h > 0:
        r += f"{h}H"
    if m > 0:
        r += f"{m}M"
    return r


HOLIDAYS_VS = [
    # Jours fériés récurrents (chaque année)
    make_holiday("Nouvel An",               1,  1),
    make_holiday("Saint-Joseph",           19,  3),
    make_holiday("Fête du Travail",         1,  5),
    make_holiday("Fête nationale",          1,  8),
    make_holiday("Assomption",             15,  8),
    make_holiday("Toussaint",               1, 11),
    make_holiday("Immaculée Conception",    8, 12),
    make_holiday("Noël",                   25, 12),
    # Jours fériés 2026 (dates mobiles)
    make_holiday("Vendredi Saint 2026",     3,  4, year=2026, is_recurrent=False),
    make_holiday("Lundi de Pâques 2026",    6,  4, year=2026, is_recurrent=False),
    make_holiday("Ascension 2026",         14,  5, year=2026, is_recurrent=False),
    make_holiday("Lundi de Pentecôte 2026",25,  5, year=2026, is_recurrent=False),
    make_holiday("Fête-Dieu 2026",          4,  6, year=2026, is_recurrent=False),
]

# =============================================================================
# JOURS FÉRIÉS VAUD (VD) - 2026
# =============================================================================
HOLIDAYS_VD = [
    # Jours fériés récurrents (chaque année)
    make_holiday("Nouvel An",               1,  1),
    make_holiday("Lendemain de Nouvel An",  2,  1),
    make_holiday("Fête nationale",          1,  8),
    make_holiday("Noël",                   25, 12),
    # Jours fériés 2026 (dates mobiles)
    make_holiday("Vendredi Saint 2026",     3,  4, year=2026, is_recurrent=False),
    make_holiday("Lundi de Pâques 2026",    6,  4, year=2026, is_recurrent=False),
    make_holiday("Ascension 2026",         14,  5, year=2026, is_recurrent=False),
    make_holiday("Lundi de Pentecôte 2026",25,  5, year=2026, is_recurrent=False),
    make_holiday("Lundi du Jeûne 2026",    21,  9, year=2026, is_recurrent=False),
]

# =============================================================================
# MAPPING DÉPARTEMENTS → horaires + canton
# =============================================================================
# Clé = nom dans 3CX, Valeur = (type_horaire, canton)
DEPT_CONFIG = {
    "Company A": (HOURS_TYPE_A, "VS"),
    "Company B": (HOURS_TYPE_B, "VS"),   # vendredi matin uniquement
    "Company C": (HOURS_TYPE_A, "VD"),
    "Company D": (HOURS_TYPE_C, "VD"),   # matin uniquement
}

CANTON_HOLIDAYS = {
    "VS": HOLIDAYS_VS,
    "VD": HOLIDAYS_VD,
}


# =============================================================================
# FONCTIONS API
# =============================================================================
def authenticate():
    resp = requests.post(
        f"{PBX_URL}/webclient/api/Login/GetAccessToken",
        json={"Username": USERNAME, "Password": PASSWORD, "SecurityCode": SECURITY_CODE},
        verify=False, timeout=30,
    )
    resp.raise_for_status()
    token = resp.json().get("Token", {}).get("access_token")
    if not token:
        raise RuntimeError(f"Échec auth: {resp.json()}")
    return {"Authorization": f"Bearer {token}"}


def get_groups(headers):
    resp = requests.get(
        f"{PBX_URL}/xapi/v1/Groups"
        "?$filter=not startsWith(Name, '___FAVORITES___')"
        "&$select=Id,Number,Name",
        headers=headers, verify=False, timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("value", [])


def patch_group(headers, group_id, payload, dry_run=False):
    if dry_run:
        return True
    resp = requests.patch(
        f"{PBX_URL}/xapi/v1/Groups({group_id})",
        headers={**headers, "Content-Type": "application/json; charset=utf-8"},
        json=payload, verify=False, timeout=30,
    )
    resp.raise_for_status()
    return True


# =============================================================================
# MAIN
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="Configure 3CX - Fériés & Horaires")
    parser.add_argument("--dry-run", action="store_true", help="Aperçu sans modification")
    parser.add_argument("--list", action="store_true", help="Liste les départements")
    args = parser.parse_args()

    print("Connexion au PBX...")
    headers = authenticate()
    print("OK\n")

    groups = get_groups(headers)

    if args.list:
        print(f"{'Numéro':<10} {'Nom':<25} {'ID':<6} {'Config'}")
        print("-" * 70)
        for g in sorted(groups, key=lambda x: x["Number"]):
            name = g.get("Name", "")
            cfg = DEPT_CONFIG.get(name)
            status = f"→ {cfg[1]}" if cfg else "(non configuré)"
            print(f"{g['Number']:<10} {name:<25} {g['Id']:<6} {status}")
        return

    prefix = "[DRY-RUN] " if args.dry_run else ""
    configured = 0
    errors = []

    for group in sorted(groups, key=lambda x: x["Number"]):
        gid = group["Id"]
        gnum = group["Number"]
        gname = group.get("Name", "")

        payload = {
            "Hours": HOURS_TYPE_A,
        }

        try:
            patch_group(headers, gid, payload, dry_run=args.dry_run)
            n_p = len(HOURS_TYPE_A["Periods"])
            print(f"  {prefix}OK    {gnum:<10} {gname:<25} {n_p} plages horaires")
            configured += 1
        except requests.HTTPError as e:
            msg = f"{e.response.status_code} - {e.response.text[:200]}"
            print(f"  ERR   {gnum:<10} {gname:<25} {msg}")
            errors.append((gnum, gname, msg))

    print(f"\n{'=' * 50}")
    print(f"{prefix}Résumé : {configured} configuré(s), {len(errors)} erreur(s)")

    if errors:
        print("\nErreurs :")
        for gnum, gname, msg in errors:
            print(f"  - {gnum} ({gname}): {msg}")


if __name__ == "__main__":
    main()
