#!/usr/bin/env python3
"""
3CX - Selecteur de numero sortant
Usage: python outbound_selector.py
"""

import os
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import yaml
from api_3cx import ThreeCXAPI

# En mode PyInstaller --onefile, __file__ pointe vers le dossier temporaire _MEIPASS.
# On utilise sys.executable pour ecrire a cote de l'exe.
import sys
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
    BASE_DIR = sys._MEIPASS
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = APP_DIR
# config.yaml : d'abord a cote de l'exe, sinon embarque dans _MEIPASS
_cfg_beside_exe = os.path.join(APP_DIR, "config.yaml")
CONFIG_FILE = _cfg_beside_exe if os.path.exists(_cfg_beside_exe) else os.path.join(BASE_DIR, "config.yaml")
STATE_FILE = os.path.join(APP_DIR, ".state.json")


class OutboundSelectorApp:

    def __init__(self, root):
        self.root = root
        self.root.title("3CX - Numero sortant")
        self.root.geometry("550x700")
        self.root.minsize(450, 400)
        self.root.resizable(True, True)

        self.api = None
        self.rules_data = []
        self.all_users = []
        self.selected_user_id = None
        self._reset_timer_id = None

        self._load_config()
        self._load_state()
        self._build_ui()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        if self.cfg.get("pbx", {}).get("url"):
            self.root.after(200, self._connect)

    # ------------------------------------------------------------------
    # Config & State
    # ------------------------------------------------------------------
    def _load_config(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                self.cfg = yaml.safe_load(f) or {}
        except FileNotFoundError:
            self.cfg = {}

    def _load_state(self):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                self.state = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.state = {}
        # Valeurs par defaut (ecrites dans le state des le 1er run pour
        # garantir que Reset/Auto-reset trouvent toujours quelque chose).
        self.state.setdefault("default_caller_id", "0274522539")

    def _save_state(self):
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
        except Exception:
            pass

    def _on_close(self):
        sel = self.ext_var.get()
        if sel:
            self.state["last_extension"] = sel.split(" - ")[0].strip()
        self._save_state()
        self.root.destroy()

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------
    def _build_ui(self):
        style = ttk.Style()
        available = style.theme_names()
        if "vista" in available:
            style.theme_use("vista")
        elif "winnative" in available:
            style.theme_use("winnative")
        else:
            style.theme_use("clam")

        # --- Notebook (onglets) ---
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)

        # === Onglet principal ===
        self.main_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.main_tab, text="Numero sortant")

        # Barre du haut - ligne 1 : extension + actions
        top = ttk.Frame(self.main_tab, padding=(8, 4))
        top.pack(fill="x")

        ttk.Label(top, text="Ext:").pack(side="left")
        self.ext_var = tk.StringVar()
        self.ext_combo = ttk.Combobox(top, textvariable=self.ext_var, width=28, state="readonly")
        self.ext_combo.pack(side="left", padx=(4, 4))
        self.ext_combo.bind("<<ComboboxSelected>>", self._on_ext_selected)

        ttk.Button(top, text="Actualiser", command=self._connect, width=9).pack(side="left", padx=(0, 3))
        ttk.Button(top, text="Reset", command=self._reset_caller_id, width=6).pack(side="left")

        self.current_cid_label = ttk.Label(top, text="", font=("Segoe UI", 9, "bold"), foreground="#0066cc")
        self.current_cid_label.pack(side="right")
        self.status_label = ttk.Label(top, text="Deconnecte", foreground="gray")
        self.status_label.pack(side="right", padx=(0, 10))

        ttk.Separator(self.main_tab, orient="horizontal").pack(fill="x")

        # Zone scrollable
        container = ttk.Frame(self.main_tab)
        container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(container, highlightthickness=0, bg="#f0f0f0")
        self.scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.cards_frame = ttk.Frame(self.canvas)
        self.cards_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._canvas_window = self.canvas.create_window((0, 0), window=self.cards_frame, anchor="nw")
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        # Barre du bas
        bottom = ttk.Frame(self.main_tab, padding=(8, 3))
        bottom.pack(fill="x", side="bottom")
        ttk.Separator(self.main_tab, orient="horizontal").pack(fill="x", side="bottom")
        self.bottom_status = ttk.Label(bottom, text="", foreground="gray")
        self.bottom_status.pack(side="left")

        # === Onglet Config ===
        self.cfg_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.cfg_tab, text="Config")
        self._build_config_tab()

    def _build_config_tab(self):
        wrapper = ttk.Frame(self.cfg_tab, padding=10)
        wrapper.pack(fill="both", expand=True)

        # --- Entreprise par defaut (Reset / Auto-reset) ---
        default_frame = ttk.LabelFrame(wrapper, text="Entreprise par defaut (Reset / Auto-reset)", padding=6)
        default_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(default_frame, text="Entreprise:").pack(side="left")
        self.default_company_var = tk.StringVar()
        self.default_company_combo = ttk.Combobox(
            default_frame, textvariable=self.default_company_var, state="readonly"
        )
        self.default_company_combo.pack(side="left", fill="x", expand=True, padx=(6, 6))
        self.default_company_combo.bind(
            "<<ComboboxSelected>>", lambda e: self._on_default_company_changed()
        )
        self.default_cid_save_label = ttk.Label(default_frame, text="", foreground="gray")
        self.default_cid_save_label.pack(side="left")
        # Map interne libelle -> rule (rempli a chaque _populate_config_tab)
        self._default_company_label_to_rule = {}

        # Conteneur 2 colonnes
        cols_wrapper = ttk.Frame(wrapper)
        cols_wrapper.pack(fill="both", expand=True)

        # --- Extensions visibles ---
        left = ttk.LabelFrame(cols_wrapper, text="Extensions visibles", padding=6)
        left.pack(side="left", fill="both", expand=True, padx=(0, 5))

        ext_btn_bar = ttk.Frame(left)
        ext_btn_bar.pack(fill="x", pady=(0, 4))
        ttk.Button(ext_btn_bar, text="Tout", width=5, command=lambda: self._toggle_all(self.ext_check_vars, True)).pack(side="left", padx=(0, 3))
        ttk.Button(ext_btn_bar, text="Aucun", width=5, command=lambda: self._toggle_all(self.ext_check_vars, False)).pack(side="left")

        self.ext_cfg_canvas = tk.Canvas(left, highlightthickness=0)
        ext_scrollbar = ttk.Scrollbar(left, orient="vertical", command=self.ext_cfg_canvas.yview)
        self.ext_cfg_frame = ttk.Frame(self.ext_cfg_canvas)
        self.ext_cfg_canvas.create_window((0, 0), window=self.ext_cfg_frame, anchor="nw")
        self.ext_cfg_frame.bind("<Configure>", lambda e: self.ext_cfg_canvas.configure(scrollregion=self.ext_cfg_canvas.bbox("all")))
        self.ext_cfg_canvas.configure(yscrollcommand=ext_scrollbar.set)
        self.ext_cfg_canvas.pack(side="left", fill="both", expand=True)
        ext_scrollbar.pack(side="right", fill="y")

        self.ext_check_vars = {}  # {ext_num: BooleanVar}

        # --- Entreprises visibles ---
        right = ttk.LabelFrame(cols_wrapper, text="Entreprises visibles", padding=6)
        right.pack(side="left", fill="both", expand=True, padx=(5, 0))

        rule_btn_bar = ttk.Frame(right)
        rule_btn_bar.pack(fill="x", pady=(0, 4))
        ttk.Button(rule_btn_bar, text="Tout", width=5, command=lambda: self._toggle_all(self.rule_check_vars, True)).pack(side="left", padx=(0, 3))
        ttk.Button(rule_btn_bar, text="Aucun", width=5, command=lambda: self._toggle_all(self.rule_check_vars, False)).pack(side="left")

        self.rule_cfg_canvas = tk.Canvas(right, highlightthickness=0)
        rule_scrollbar = ttk.Scrollbar(right, orient="vertical", command=self.rule_cfg_canvas.yview)
        self.rule_cfg_frame = ttk.Frame(self.rule_cfg_canvas)
        self.rule_cfg_canvas.create_window((0, 0), window=self.rule_cfg_frame, anchor="nw")
        self.rule_cfg_frame.bind("<Configure>", lambda e: self.rule_cfg_canvas.configure(scrollregion=self.rule_cfg_canvas.bbox("all")))
        self.rule_cfg_canvas.configure(yscrollcommand=rule_scrollbar.set)
        self.rule_cfg_canvas.pack(side="left", fill="both", expand=True)
        rule_scrollbar.pack(side="right", fill="y")

        self.rule_check_vars = {}  # {prefix: BooleanVar}

    def _populate_config_tab(self):
        """Remplit les checkboxes apres chargement des donnees."""
        hidden_exts = set(self.state.get("hidden_extensions", []))
        hidden_rules = set(self.state.get("hidden_rules", []))

        # Extensions
        for w in self.ext_cfg_frame.winfo_children():
            w.destroy()
        self.ext_check_vars.clear()

        for u in sorted(self.all_users, key=lambda u: str(u.get("Number") or "")):
            num = str(u.get("Number") or u.get("number") or "")
            fname = u.get("FirstName") or u.get("firstName") or ""
            lname = u.get("LastName") or u.get("lastName") or ""
            name = f"{fname} {lname}".strip() or u.get("Name") or ""
            label = f"{num} - {name}"

            var = tk.BooleanVar(value=(num not in hidden_exts))
            self.ext_check_vars[num] = var
            cb = ttk.Checkbutton(self.ext_cfg_frame, text=label, variable=var, command=self._on_config_changed)
            cb.pack(anchor="w")

        # Entreprises / regles
        for w in self.rule_cfg_frame.winfo_children():
            w.destroy()
        self.rule_check_vars.clear()

        sorted_rules = sorted(self.rules_data, key=lambda r: int(r["prefix"]) if r["prefix"].isdigit() else r["prefix"])
        for rule in sorted_rules:
            prefix = rule["prefix"]
            label = f"[{prefix}] {rule['name']}"

            var = tk.BooleanVar(value=(prefix not in hidden_rules))
            self.rule_check_vars[prefix] = var
            cb = ttk.Checkbutton(self.rule_cfg_frame, text=label, variable=var, command=self._on_config_changed)
            cb.pack(anchor="w")

        # Combobox "Entreprise par defaut" : seules les entreprises avec un numero
        self._default_company_label_to_rule.clear()
        labels = []
        for rule in sorted_rules:
            if not rule.get("trunk_number"):
                continue
            lab = rule["name"]
            if lab in self._default_company_label_to_rule:
                lab = f"{rule['name']} [{rule['prefix']}]"
            self._default_company_label_to_rule[lab] = rule
            labels.append(lab)
        self.default_company_combo["values"] = labels

        # Pre-selection depuis le state (par prefix de prefrence, sinon par numero)
        saved_prefix = self.state.get("default_company_prefix", "")
        saved_cid = self.state.get("default_caller_id", "")
        match_label = ""
        for lab, rule in self._default_company_label_to_rule.items():
            if saved_prefix and rule.get("prefix") == saved_prefix:
                match_label = lab
                break
            if saved_cid and rule.get("trunk_number") == saved_cid:
                match_label = lab
                break
        self.default_company_var.set(match_label)

    def _toggle_all(self, check_vars, value):
        for var in check_vars.values():
            var.set(value)
        self._on_config_changed()

    def _on_config_changed(self):
        """Sauvegarde les choix et rafraichit l'onglet principal."""
        hidden_exts = [num for num, var in self.ext_check_vars.items() if not var.get()]
        hidden_rules = [prefix for prefix, var in self.rule_check_vars.items() if not var.get()]
        self.state["hidden_extensions"] = hidden_exts
        self.state["hidden_rules"] = hidden_rules
        self._save_state()
        self._update_main_tab()

    def _on_default_company_changed(self):
        """Sauvegarde l'entreprise par defaut + son numero resolu."""
        label = self.default_company_var.get()
        rule = self._default_company_label_to_rule.get(label)
        if rule:
            self.state["default_caller_id"] = rule.get("trunk_number", "") or ""
            self.state["default_company_prefix"] = rule.get("prefix", "")
        else:
            self.state["default_caller_id"] = ""
            self.state["default_company_prefix"] = ""
        self._save_state()
        # Petit feedback visuel
        self.default_cid_save_label.config(text="Sauvegarde", foreground="green")
        if hasattr(self, "_default_cid_save_timer") and self._default_cid_save_timer:
            self.root.after_cancel(self._default_cid_save_timer)
        self._default_cid_save_timer = self.root.after(
            1500, lambda: self.default_cid_save_label.config(text="")
        )

    def _on_canvas_resize(self, event):
        self.canvas.itemconfig(self._canvas_window, width=event.width)

    # ------------------------------------------------------------------
    # Connexion
    # ------------------------------------------------------------------
    def _connect(self):
        self.status_label.config(text="Connexion...", foreground="orange")
        threading.Thread(target=self._do_connect, daemon=True).start()

    def _do_connect(self):
        try:
            pbx = self.cfg.get("pbx", {})
            self.api = ThreeCXAPI(
                pbx.get("url", ""), pbx.get("username", ""),
                pbx.get("password") or os.environ.get("THREECX_PASSWORD", ""), pbx.get("security_code", ""),
            )
            self.api.authenticate()

            rules = self.api.get_outbound_rules()
            users = self.api.get_users()

            if rules:
                print(f"[DEBUG] Cles OutboundRule : {list(rules[0].keys())}")
            if users:
                print(f"[DEBUG] Cles User : {list(users[0].keys())}")

            manual_labels = self.cfg.get("outbound_labels") or {}
            enriched = []
            for rule in rules:
                rid = rule.get("Id") or rule.get("id")
                prefix = rule.get("Prefix") or rule.get("prefix") or ""
                if not prefix.strip():
                    continue
                name = (
                    rule.get("Name") or rule.get("name")
                    or rule.get("RuleName") or f"Regle {prefix or rid}"
                )
                display_number = manual_labels.get(prefix) or manual_labels.get(str(prefix)) or ""
                if not display_number:
                    routes = rule.get("Routes") or rule.get("routes") or []
                    if not routes:
                        try:
                            routes = self.api.get_outbound_rule_routes(rid)
                        except Exception:
                            routes = []
                    for route in routes:
                        cid = route.get("CallerID") or route.get("OverrideCallerID") or ""
                        if cid:
                            display_number = cid
                            break
                print(f"[DEBUG] Rule: {name} | Prefix: {prefix} | Num: {display_number or '-'}")
                enriched.append({"id": rid, "name": name, "prefix": prefix, "trunk_number": display_number})

            self.rules_data = enriched
            self.all_users = users
            self.root.after(0, self._populate_config_tab)
            self.root.after(0, self._update_main_tab)
            n = len(enriched)
            self.root.after(0, lambda: self.status_label.config(text=f"Connecte ({n})", foreground="green"))
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.root.after(0, lambda: self.status_label.config(text=f"Erreur: {e}", foreground="red"))
            self.root.after(0, lambda: messagebox.showerror("Erreur", f"Connexion impossible.\n\n{e}"))

    # ------------------------------------------------------------------
    # Mise a jour onglet principal
    # ------------------------------------------------------------------
    def _update_main_tab(self):
        hidden_exts = set(self.state.get("hidden_extensions", []))
        hidden_rules = set(self.state.get("hidden_rules", []))

        # Extensions filtrees
        ext_values = []
        for u in self.all_users:
            num = str(u.get("Number") or u.get("number") or "")
            if num in hidden_exts:
                continue
            fname = u.get("FirstName") or u.get("firstName") or ""
            lname = u.get("LastName") or u.get("lastName") or ""
            name = f"{fname} {lname}".strip() or u.get("Name") or u.get("name") or ""
            ext_values.append(f"{num} - {name}")
        self.ext_combo["values"] = ext_values

        # Restaurer l'extension
        restore_ext = self.state.get("last_extension") or self.cfg.get("default_extension", "")
        if restore_ext:
            for i, v in enumerate(ext_values):
                if v.startswith(str(restore_ext)):
                    self.ext_combo.current(i)
                    self._on_ext_selected(None)
                    break

        # Cartes filtrees
        for w in self.cards_frame.winfo_children():
            w.destroy()

        visible_rules = [r for r in self.rules_data if r["prefix"] not in hidden_rules]
        visible_rules.sort(key=lambda r: int(r["prefix"]) if r["prefix"].isdigit() else r["prefix"])

        if not visible_rules:
            ttk.Label(self.cards_frame, text="Aucune entreprise visible.\nCochez-en dans l'onglet Config.", foreground="gray").pack(pady=30)
            return

        cols = 2
        for i, rule in enumerate(visible_rules):
            self._create_card(self.cards_frame, rule, i // cols, i % cols)
        for c in range(cols):
            self.cards_frame.columnconfigure(c, weight=1, uniform="cards")

    def _create_card(self, parent, rule, row, col):
        card = ttk.LabelFrame(parent, text=rule["name"], padding=(6, 2))
        card.grid(row=row, column=col, padx=3, pady=2, sticky="nsew")

        number_text = rule["trunk_number"]
        info_frame = ttk.Frame(card)
        info_frame.pack(fill="x")
        if number_text:
            ttk.Label(info_frame, text=number_text, font=("Segoe UI", 10, "bold")).pack(side="left")
        else:
            ttk.Label(info_frame, text="(config.yaml)", font=("Segoe UI", 8, "italic"), foreground="#999").pack(side="left")
        ttk.Label(info_frame, text=f"[{rule['prefix']}]", foreground="gray", font=("Segoe UI", 8)).pack(side="right")

        btn_frame = ttk.Frame(card)
        btn_frame.pack(fill="x", pady=(2, 0))
        ttk.Button(btn_frame, text="Copier", command=lambda r=rule: self._copy_prefix(r), width=7).pack(side="left", padx=(0, 3))
        if number_text:
            ttk.Button(btn_frame, text="Utiliser", command=lambda r=rule: self._apply_caller_id(r), width=7).pack(side="left")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _on_ext_selected(self, event):
        sel = self.ext_var.get()
        if sel:
            num = sel.split(" - ")[0].strip()
            for u in self.all_users:
                if str(u.get("Number") or u.get("number") or "") == num:
                    self.selected_user_id = u.get("Id") or u.get("id")
                    break
            self._refresh_current_caller_id()

    def _refresh_current_caller_id(self):
        if not self.selected_user_id or not self.api:
            self.current_cid_label.config(text="")
            return
        self.current_cid_label.config(text="...", foreground="gray")
        threading.Thread(target=self._do_fetch_caller_id, daemon=True).start()

    def _do_fetch_caller_id(self):
        try:
            user_data = self.api.get_user(self.selected_user_id)
            cid = (
                user_data.get("OutboundCallerId")
                or user_data.get("OutboundCallerNumber")
                or user_data.get("OutboundCallerID")
                or ""
            )
            if not cid:
                props = user_data.get("Properties") or {}
                if isinstance(props, dict):
                    cid = props.get("OutboundCallerId") or props.get("OutboundCallerNumber") or ""
            if cid:
                # Chercher le nom de l'entreprise correspondante
                company = ""
                for rule in self.rules_data:
                    if rule["trunk_number"] and rule["trunk_number"] == cid:
                        company = rule["name"]
                        break
                if company:
                    display, color = f"Actif: {company}", "#0066cc"
                else:
                    display, color = f"Actif: {cid}", "#0066cc"
            else:
                display, color = "Actif: (defaut)", "gray"
            self.root.after(0, lambda: self.current_cid_label.config(text=display, foreground=color))
        except Exception as e:
            print(f"[DEBUG] Erreur fetch caller ID: {e}")
            self.root.after(0, lambda: self.current_cid_label.config(text="Actif: ?", foreground="gray"))

    def _copy_prefix(self, rule):
        self.root.clipboard_clear()
        self.root.clipboard_append(rule["prefix"])
        self._show_bottom_status(f"Prefixe '{rule['prefix']}' copie", "green")

    def _reset_caller_id(self):
        if not self.selected_user_id:
            messagebox.showwarning("Attention", "Selectionnez d'abord une extension.")
            return
        # Annuler le timer auto-reset s'il tourne
        if self._reset_timer_id:
            self.root.after_cancel(self._reset_timer_id)
            self._reset_timer_id = None
        self.status_label.config(text="Reset...", foreground="orange")
        threading.Thread(target=self._do_reset_caller_id, daemon=True).start()

    def _do_reset_caller_id(self):
        default_cid = self.state.get("default_caller_id", "").strip()
        try:
            self.api.patch_user(self.selected_user_id, {"OutboundCallerID": default_cid})
            msg = f"Remis par defaut ({default_cid})" if default_cid else "Caller ID vide (defaut 3CX)"
            self.root.after(0, lambda m=msg: self._show_bottom_status(m, "green"))
            self.root.after(0, lambda: self.status_label.config(text="Connecte", foreground="green"))
            self.root.after(0, self._refresh_current_caller_id)
        except Exception as e:
            print(f"[DEBUG] Erreur reset: {e}")
            self.root.after(0, lambda: messagebox.showerror("Erreur", str(e)))
            self.root.after(0, lambda: self.status_label.config(text="Connecte", foreground="green"))

    def _apply_caller_id(self, rule):
        if not self.selected_user_id:
            messagebox.showwarning("Attention", "Selectionnez d'abord une extension.")
            return
        number = rule.get("trunk_number", "")
        if not number:
            messagebox.showwarning("Attention", "Numero indisponible, utilisez 'Copier'.")
            return
        self.status_label.config(text="Application...", foreground="orange")
        threading.Thread(target=self._do_apply_caller_id, args=(number,), daemon=True).start()

    def _do_apply_caller_id(self, number):
        success = False
        try:
            self.api.patch_user(self.selected_user_id, {"OutboundCallerId": number})
            success = True
        except Exception as e:
            print(f"[DEBUG] Erreur set caller ID: {e}")
            for alt in [{"OutboundCallerNumber": number}, {"OutboundCallerID": number}]:
                try:
                    self.api.patch_user(self.selected_user_id, alt)
                    success = True
                    break
                except Exception:
                    continue
            if not success:
                self.root.after(0, lambda: self.status_label.config(text="Erreur", foreground="red"))
                self.root.after(0, lambda: messagebox.showerror("Erreur", f"Echec modification.\n{e}"))
                return

        self.root.after(0, lambda: self._show_bottom_status(f"Numero change: {number}", "green"))
        self.root.after(0, self._refresh_current_caller_id)
        # Timer : reset auto dans 2 minutes
        self._start_reset_timer()

    # ------------------------------------------------------------------
    # Timer : reset auto apres 2 minutes
    # ------------------------------------------------------------------
    def _start_reset_timer(self):
        """Lance un timer de 2 min puis reset le caller ID."""
        # Annuler un timer precedent s'il existe
        if hasattr(self, '_reset_timer_id') and self._reset_timer_id:
            self.root.after_cancel(self._reset_timer_id)
        # Countdown
        self._reset_timer_id = self.root.after(60000, self._fire_auto_reset)

    def _fire_auto_reset(self):
        """Declenche le reset auto apres le delai."""
        self._reset_timer_id = None
        threading.Thread(target=self._do_auto_reset, daemon=True).start()

    def _do_auto_reset(self):
        default_cid = self.state.get("default_caller_id", "").strip()
        try:
            self.api.patch_user(self.selected_user_id, {"OutboundCallerID": default_cid})
            msg = (
                f"Auto-reset: numero remis par defaut ({default_cid})"
                if default_cid else "Auto-reset: caller ID vide (defaut 3CX)"
            )
            self.root.after(0, lambda m=msg: self._show_bottom_status(m, "green"))
            self.root.after(0, lambda: self.status_label.config(text="Connecte", foreground="green"))
            self.root.after(0, self._refresh_current_caller_id)
        except Exception as e:
            print(f"[DEBUG] Erreur auto-reset: {e}")
            self.root.after(0, lambda: self.status_label.config(text="Connecte", foreground="green"))

    def _show_bottom_status(self, text, color="gray"):
        self.bottom_status.config(text=text, foreground=color)
        self.root.after(4000, lambda: self.bottom_status.config(text="", foreground="gray"))


# =========================================================================
def main():
    root = tk.Tk()
    try:
        root.iconbitmap(os.path.join(BASE_DIR, "icon.ico"))
    except Exception:
        pass
    OutboundSelectorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
