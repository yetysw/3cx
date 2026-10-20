#!/usr/bin/env python3
"""
Module API 3CX v20+ (XAPI / OData)
Base de connexion et helpers generiques pour interagir avec le PBX.
"""

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ThreeCXAPI:
    """Client API 3CX - authentification et appels XAPI."""

    def __init__(self, base_url, username, password, security_code=""):
        if not base_url.startswith("http"):
            base_url = f"https://{base_url}"
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.security_code = security_code
        self._headers = {}

    # ------------------------------------------------------------------
    # Authentification
    # ------------------------------------------------------------------
    def authenticate(self):
        """Obtient un token Bearer via l'API webclient."""
        resp = requests.post(
            f"{self.base_url}/webclient/api/Login/GetAccessToken",
            json={
                "Username": self.username,
                "Password": self.password,
                "SecurityCode": self.security_code,
            },
            verify=False,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("Token", {}).get("access_token")
        if not token:
            raise RuntimeError(f"Echec auth: {data}")
        self._headers = {"Authorization": f"Bearer {token}"}

    # ------------------------------------------------------------------
    # Helpers generiques
    # ------------------------------------------------------------------
    def _get(self, path, params=None):
        """GET generique sur l'API."""
        resp = requests.get(
            f"{self.base_url}{path}",
            headers=self._headers,
            params=params,
            verify=False,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _patch(self, path, payload):
        """PATCH generique sur l'API."""
        resp = requests.patch(
            f"{self.base_url}{path}",
            headers={**self._headers, "Content-Type": "application/json"},
            json=payload,
            verify=False,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def _post(self, path, payload):
        """POST generique sur l'API."""
        resp = requests.post(
            f"{self.base_url}{path}",
            headers={**self._headers, "Content-Type": "application/json"},
            json=payload,
            verify=False,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    # ------------------------------------------------------------------
    # Active Calls (appels en cours)
    # ------------------------------------------------------------------
    def get_active_calls(self):
        """Recupere les appels en cours."""
        return self._get("/xapi/v1/ActiveCalls").get("value", [])

    # ------------------------------------------------------------------
    # Outbound Rules (regles sortantes)
    # ------------------------------------------------------------------
    def get_outbound_rules(self):
        """Recupere toutes les regles sortantes."""
        return self._get("/xapi/v1/OutboundRules").get("value", [])

    def get_outbound_rule_routes(self, rule_id):
        """Recupere les routes d'une regle sortante."""
        return self._get(
            f"/xapi/v1/OutboundRules({rule_id})/Routes"
        ).get("value", [])

    # ------------------------------------------------------------------
    # Trunks (lignes SIP)
    # ------------------------------------------------------------------
    def get_trunks(self):
        """Recupere tous les trunks SIP."""
        return self._get("/xapi/v1/Trunks").get("value", [])

    # ------------------------------------------------------------------
    # Users / Extensions
    # ------------------------------------------------------------------
    def get_users(self):
        """Recupere la liste des utilisateurs/extensions."""
        return self._get("/xapi/v1/Users").get("value", [])

    def get_user(self, user_id):
        """Recupere un utilisateur par ID."""
        return self._get(f"/xapi/v1/Users({user_id})")

    def patch_user(self, user_id, payload):
        """Modifie un utilisateur (ex: OutboundCallerId)."""
        return self._patch(f"/xapi/v1/Users({user_id})", payload)

    # ------------------------------------------------------------------
    # Groups (departements / ring groups)
    # ------------------------------------------------------------------
    def get_groups(self):
        """Recupere les groupes (hors favoris)."""
        return self._get(
            "/xapi/v1/Groups"
            "?$filter=not startsWith(Name, '___FAVORITES___')"
            "&$select=Id,Number,Name"
        ).get("value", [])

    def patch_group(self, group_id, payload):
        """Modifie la config d'un groupe."""
        return self._patch(f"/xapi/v1/Groups({group_id})", payload)
