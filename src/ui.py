from __future__ import annotations

import os
import re
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from src.altitude_provider import OpenTopographyProvider
from src.fit_processor import FitProcessor
from src.settings import SettingsStore

try:
    from tkinterdnd2 import DND_FILES, Tk
except ImportError:  # pragma: no cover - fallback for environments without tkinterdnd2
    DND_FILES = None
    Tk = tk.Tk


class FitAltitudeApp(Tk):
    def __init__(self):
        super().__init__()
        self.title("FIT Altitude Tool")
        self.geometry("720x480")
        self.minsize(560, 360)

        self.processor = FitProcessor()
        self.settings = SettingsStore()
        self.altitude_provider = OpenTopographyProvider(api_key=self.settings.load_api_key())
        self.is_processing = False
        self.action_buttons: list[ttk.Button] = []

        self._build_ui()
        self._enable_drag_and_drop()

    def _build_ui(self) -> None:
        self._build_menu()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = ttk.Frame(self, padding=(16, 16, 16, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="FIT Altitude Tool", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, sticky="w")

        actions = ttk.Frame(self, padding=(16, 0, 16, 8))
        actions.grid(row=1, column=0, sticky="ew")
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)

        folder_button = ttk.Button(actions, text="Choisir un dossier", command=self.select_folder)
        folder_button.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        files_button = ttk.Button(actions, text="Ajouter des fichiers", command=self.select_files)
        files_button.grid(row=0, column=1, padx=(8, 0), sticky="ew")
        self.action_buttons.extend((folder_button, files_button))

        drop_zone = ttk.LabelFrame(self, text="Zone de dépôt", padding=(16, 10))
        drop_zone.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 8))
        drop_zone.columnconfigure(0, weight=1)
        self.drop_hint = ttk.Label(
            drop_zone,
            text="Glissez ici un ou plusieurs fichiers .FIT",
            foreground="#3b3b3b",
            anchor="center",
            font=("Segoe UI", 11),
        )
        self.drop_hint.grid(row=0, column=0, sticky="ew")

        self.log = tk.Text(self, wrap="word", height=15, state="disabled", bg="#f7f7f7")
        self.log.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 16))

        self._log("Application démarrée. Déposez des fichiers .FIT ici ou utilisez les boutons ci-dessus.")

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self)
        self.options_menu = tk.Menu(menu_bar, tearoff=False)
        self.options_menu.add_command(label="Clé API OpenTopography...", command=self.open_api_key_dialog)
        menu_bar.add_cascade(label="Options", menu=self.options_menu)
        self.configure(menu=menu_bar)

    def open_api_key_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Clé API OpenTopography")
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.grab_set()

        content = ttk.Frame(dialog, padding=16)
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)

        # Guide pour obtenir une clé API
        guide_frame = ttk.LabelFrame(content, text="Comment obtenir une clé API (gratuit) :", padding=10)
        guide_frame.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        guide_frame.columnconfigure(0, weight=1)

        instructions = (
            "1. Créez un compte gratuit sur le site OpenTopography.\n"
            "2. Connectez-vous et allez dans la rubrique 'MyOpenTopo'.\n"
            "3. Sélectionnez 'myTopography Authorizations / API Key'.\n"
            "4. Générez votre clé API, puis collez-la dans le champ ci-dessous."
        )
        ttk.Label(guide_frame, text=instructions, justify="left").grid(row=0, column=0, sticky="w")

        link_button = ttk.Button(
            guide_frame,
            text="🌐 Ouvrir portal.opentopography.org",
            command=lambda: webbrowser.open("https://portal.opentopography.org/myopentopo"),
        )
        link_button.grid(row=1, column=0, sticky="w", pady=(8, 0))

        # Champ de saisie de la clé
        ttk.Label(content, text="Clé API OpenTopography :").grid(row=1, column=0, sticky="w")
        api_key = tk.StringVar(value=self.altitude_provider.api_key or "")
        key_entry = ttk.Entry(content, textvariable=api_key, show="*", width=52)
        key_entry.grid(row=2, column=0, pady=(4, 12), sticky="ew")
        key_entry.focus_set()

        buttons = ttk.Frame(content)
        buttons.grid(row=3, column=0, sticky="e")
        ttk.Button(buttons, text="Annuler", command=dialog.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(
            buttons,
            text="Enregistrer",
            command=lambda: self._save_api_key(api_key.get(), dialog),
        ).grid(row=0, column=1)

    def _save_api_key(self, api_key: str, dialog: tk.Toplevel) -> None:
        api_key = api_key.strip()
        if not api_key:
            messagebox.showerror("Clé manquante", "Saisissez une clé API OpenTopography.", parent=dialog)
            return
        try:
            self.settings.save_api_key(api_key)
        except OSError as error:
            messagebox.showerror("Enregistrement impossible", str(error), parent=dialog)
            return

        self.altitude_provider.api_key = api_key
        dialog.destroy()
        self._log("Clé API OpenTopography enregistrée pour cet utilisateur Windows.")

    def _enable_drag_and_drop(self) -> None:
        if DND_FILES is None:
            self._log("Drag & drop : dépendance tkinterdnd2 absente. Installez les dépendances pour activer le dépôt de fichiers.")
            return

        try:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
            self.dnd_bind("<<DragEnter>>", self._on_drag_enter)
            self.dnd_bind("<<DragLeave>>", self._on_drag_leave)
        except Exception:
            self._log("Drag & drop : impossible d’activer le dépôt natif sur cette plateforme.")

    def _on_drag_enter(self, event):
        self.drop_hint.configure(style="Accent.TLabel")
        self.drop_hint.configure(text="Relâchez pour ajouter les fichiers .FIT")

    def _on_drag_leave(self, event):
        self.drop_hint.configure(style="")
        self.drop_hint.configure(text="Glissez ici un ou plusieurs fichiers .FIT")

    def _on_drop(self, event):
        if self.is_processing:
            self._log("Traitement déjà en cours. Attendez sa fin avant d'ajouter d'autres fichiers.")
            return
        payload = event.data
        dropped_paths = self._parse_drop_payload(payload)
        if not dropped_paths:
            self._log("Aucun fichier valide déposé.")
            return

        files_to_process = self._collect_fit_files(dropped_paths)
        if not files_to_process:
            self._log("Les fichiers ou dossiers déposés ne contiennent aucun fichier .FIT valide.")
            return

        self._log(f"{len(files_to_process)} fichier(s) .FIT détecté(s) via drag & drop.")
        for file_path in files_to_process[:20]:
            self._log(f"- {os.path.basename(file_path)}")
        if len(files_to_process) > 20:
            self._log(f"... et {len(files_to_process) - 20} fichier(s) supplémentaire(s)")
        self._process_files(files_to_process)
        self._on_drag_leave(event)

    def _collect_fit_files(self, paths: list[str]) -> list[str]:
        files: list[str] = []
        seen: set[str] = set()

        for raw_path in paths:
            candidate = raw_path.strip().strip('"')
            if not candidate:
                continue

            if os.path.isdir(candidate):
                discovered = self.processor.discover_fit_files(candidate)
                for file_path in discovered:
                    norm = os.path.normpath(str(file_path))
                    if norm not in seen:
                        seen.add(norm)
                        files.append(norm)
                continue

            if os.path.isfile(candidate) and candidate.lower().endswith(".fit"):
                norm = os.path.normpath(candidate)
                if norm not in seen:
                    seen.add(norm)
                    files.append(norm)

        return sorted(files)

    @staticmethod
    def _parse_drop_payload(payload: str) -> list[str]:
        cleaned = payload.strip()
        if not cleaned:
            return []

        brace_matches = re.findall(r"\{([^{}]+)\}", cleaned)
        if brace_matches:
            return [match.strip().strip('"') for match in brace_matches if match.strip()]

        if "\x00" in cleaned:
            return [part.strip().strip('"') for part in cleaned.split("\x00") if part.strip()]
        if "\n" in cleaned:
            return [line.strip().strip('"') for line in cleaned.splitlines() if line.strip()]
        if "\r" in cleaned:
            return [line.strip().strip('"') for line in cleaned.split("\r") if line.strip()]

        quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'|([^\s]+)', cleaned)
        flattened = []
        for group in quoted:
            for item in group:
                if item and item.strip():
                    flattened.append(item.strip())
        if flattened:
            return flattened

        return [cleaned.strip().strip('"')]

    def _log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert(tk.END, message + "\n")
        self.log.see(tk.END)
        self.log.configure(state="disabled")

    def _process_files(self, files: list[str]) -> None:
        if self.is_processing:
            return
        self.is_processing = True
        self._set_processing_state(True)
        self._log("Traitement COP30 en cours. L'interface reste utilisable.")
        threading.Thread(target=self._process_files_worker, args=(files,), daemon=True).start()

    def _process_files_worker(self, files: list[str]) -> None:
        cache = self.altitude_provider.cache
        try:
            results = self.processor.process_files_with_provider(files, cache, self.altitude_provider)
        except Exception as error:
            self.after(0, self._finish_processing, None, error)
            return
        self.after(0, self._finish_processing, results, None)

    def _finish_processing(self, results: list[dict] | None, error: Exception | None) -> None:
        self.is_processing = False
        self._set_processing_state(False)
        if error is not None:
            self._log(f"Erreur pendant le traitement : {error}")
            messagebox.showerror("Traitement impossible", str(error), parent=self)
            return

        for result in results or []:
            if result.get("skipped_incomplete"):
                self._log(
                    f"FIT non généré : {os.path.basename(result['source_path'])} - "
                    f"{len(result['debug_missing'])} point(s) restent sans altitude COP30."
                )
                continue

            name = os.path.basename(result["output_path"])
            if result.get("copied_without_gps"):
                self._log(f"Copie sans GPS : {name}")
            else:
                self._log(f"FIT généré : {name} ({result['updated_count']} altitude(s))")
            if result.get("debug_missing"):
                self._log(f"DEBUG : {len(result['debug_missing'])} point(s) sans altitude")
        self._log(f"Requêtes OpenTopography utilisées : {self.altitude_provider.request_count}/50")
        if self.altitude_provider.errors:
            self._log(f"COP30 : {self.altitude_provider.errors[0]}")
            if len(self.altitude_provider.errors) > 1:
                self._log(f"COP30 : {len(self.altitude_provider.errors) - 1} erreur(s) supplémentaire(s).")

    def _set_processing_state(self, processing: bool) -> None:
        state = "disabled" if processing else "normal"
        for button in self.action_buttons:
            button.configure(state=state)
        self.options_menu.entryconfigure(0, state=state)
        self.drop_hint.configure(
            text="Traitement COP30 en cours..." if processing else "Glissez ici un ou plusieurs fichiers .FIT"
        )

    def select_folder(self) -> None:
        folder = filedialog.askdirectory(title="Choisir un dossier contenant des fichiers FIT")
        if not folder:
            return
        files = self.processor.discover_fit_files(folder)
        if not files:
            self._log(f"Aucun fichier .FIT trouvé dans : {folder}")
            return
        self._log(f"{len(files)} fichier(s) .FIT détecté(s) dans le dossier sélectionné.")
        for file in files[:10]:
            self._log(f"- {os.path.basename(file)}")
        self._process_files([str(file) for file in files])

    def select_files(self) -> None:
        files = filedialog.askopenfilenames(
            title="Sélectionner des fichiers FIT",
            filetypes=[("Fichiers FIT", "*.fit")],
        )
        if not files:
            return
        self._log(f"{len(files)} fichier(s) sélectionné(s)")
        for file in files:
            self._log(f"- {os.path.basename(file)}")
        self._process_files([str(file) for file in files])


if __name__ == "__main__":
    app = FitAltitudeApp()
    app.mainloop()
