#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Obsidian Vault Manager - Style Apple Minimaliste
Synchronisation intelligente avec Dropbox - Design épuré
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import json
import hashlib
import threading
import time
import subprocess
import sqlite3
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional
import logging
import schedule
import dropbox
from dropbox.exceptions import AuthError, ApiError
import difflib
import fnmatch
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configuration Dropbox
DROPBOX_CONFIG = {
    "app_key": "YOUR APP KEY",
    "app_secret": "YOUR APP SECRET",
    "refresh_token": "YOUR REFRESH TOKEN"
}

# Configuration du thème
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# Couleurs Apple
COLORS = {
    'primary': '#007AFF',
    'secondary': '#8E8E93',
    'success': '#34C759',
    'error': '#FF3B30',
    'background': '#F2F2F7',
    'surface': '#FFFFFF',
    'text': '#1C1C1E',
    'text_secondary': '#8E8E93'
}

@dataclass
class FileMetadata:
    """Métadonnées d'un fichier pour la synchronisation"""
    path: str
    size: int
    mtime: float
    hash: str
    version: int = 1

@dataclass
class SyncAction:
    """Action de synchronisation à effectuer"""
    action: str
    local_path: str
    remote_path: str
    reason: str

class VaultDatabase:
    """Base de données SQLite pour gérer l'historique et métadonnées"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialise la base de données"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS file_metadata (
                    path TEXT PRIMARY KEY,
                    size INTEGER,
                    mtime REAL,
                    hash TEXT,
                    version INTEGER DEFAULT 1,
                    last_sync TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS sync_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    action TEXT,
                    file_path TEXT,
                    status TEXT,
                    details TEXT
                );
            """)
    
    def save_file_metadata(self, metadata: FileMetadata):
        """Sauvegarde les métadonnées d'un fichier"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO file_metadata 
                (path, size, mtime, hash, version) 
                VALUES (?, ?, ?, ?, ?)
            """, (metadata.path, metadata.size, metadata.mtime, metadata.hash, metadata.version))
    
    def get_file_metadata(self, path: str) -> Optional[FileMetadata]:
        """Récupère les métadonnées d'un fichier"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("""
                SELECT path, size, mtime, hash, version 
                FROM file_metadata WHERE path = ?
            """, (path,)).fetchone()
            
            if row:
                return FileMetadata(*row)
        return None
    
    def log_sync_action(self, action: str, file_path: str, status: str, details: str = ""):
        """Enregistre une action de synchronisation"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO sync_history (action, file_path, status, details)
                VALUES (?, ?, ?, ?)
            """, (action, file_path, status, details))

class FileWatcher(FileSystemEventHandler):
    """Surveillance temps réel des modifications de fichiers"""
    
    def __init__(self, vault_manager):
        self.vault_manager = vault_manager
        self.last_event_time = {}
        self.debounce_delay = 2
    
    def on_modified(self, event):
        if event.is_directory:
            return
        
        now = time.time()
        if (event.src_path in self.last_event_time and 
            now - self.last_event_time[event.src_path] < self.debounce_delay):
            return
        
        self.last_event_time[event.src_path] = now
        
        threading.Timer(self.debounce_delay, 
                       self.vault_manager.schedule_file_sync, 
                       [event.src_path]).start()

class ObsidianVaultManager:
    """Gestionnaire principal du vault Obsidian"""
    
    def __init__(self):
        # Configuration
        self.config_file = "vault_config.json"
        self.db_file = "vault_manager.db"
        self.config = self.load_config()
        
        # Base de données
        self.db = VaultDatabase(self.db_file)
        
        # Interface
        self.root = ctk.CTk()
        self.root.title("Obsidian Vault Manager")
        self.root.geometry("900x650")
        
        # Variables
        self.vault_path = tk.StringVar(value=self.config.get('vault_path', ''))
        self.auto_sync = tk.BooleanVar(value=self.config.get('auto_sync', False))
        self.real_time_sync = tk.BooleanVar(value=self.config.get('real_time_sync', False))
        
        # État
        self.sync_in_progress = False
        self.file_watcher = None
        self.observer = None
        self.dbx = None
        
        # Initialisation
        self.create_interface()
        self.init_dropbox()
        self.setup_scheduler()
        
        # Événements
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.FileHandler('vault_manager.log', encoding='utf-8')]
        )
        self.logger = logging.getLogger(__name__)

    def load_config(self) -> Dict:
        """Charge la configuration"""
        default_config = {
            'vault_path': '',
            'auto_sync': False,
            'real_time_sync': False,
            'sync_interval': 30,
            'ignore_patterns': ['.obsidian/workspace*', '.trash/*', '*.tmp']
        }
        
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return {**default_config, **config}
        except Exception as e:
            logging.error(f"Erreur chargement config: {e}")
        
        return default_config

    def save_config(self):
        """Sauvegarde la configuration"""
        config = {
            'vault_path': self.vault_path.get(),
            'auto_sync': self.auto_sync.get(),
            'real_time_sync': self.real_time_sync.get(),
            'sync_interval': self.config.get('sync_interval', 30),
            'ignore_patterns': self.config.get('ignore_patterns', [])
        }
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self.config = config
            self.log_message("Configuration sauvegardée")
        except Exception as e:
            self.log_message(f"Erreur sauvegarde config: {e}")

    def create_interface(self):
        """Crée l'interface utilisateur"""
        # Header
        header_frame = ctk.CTkFrame(self.root, height=70, corner_radius=0, fg_color="white")
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        
        title_label = ctk.CTkLabel(
            header_frame,
            text="Obsidian Vault Manager",
            font=ctk.CTkFont(size=22, weight="normal"),
            text_color=COLORS['text']
        )
        title_label.pack(pady=20)
        
        # Séparateur
        separator = ctk.CTkFrame(self.root, height=1, fg_color="#E5E5EA")
        separator.pack(fill="x")
        
        # Container principal
        main_container = ctk.CTkFrame(self.root, fg_color=COLORS['background'], corner_radius=0)
        main_container.pack(fill="both", expand=True)
        
        # Sections
        self.create_vault_section(main_container)
        self.create_sync_options_section(main_container)
        self.create_actions_section(main_container)
        self.create_progress_section(main_container)
        self.create_status_footer()

    def create_vault_section(self, parent):
        """Section configuration du vault"""
        vault_frame = ctk.CTkFrame(parent, fg_color="white", corner_radius=12)
        vault_frame.pack(fill="x", padx=20, pady=(20, 10))
        
        title_label = ctk.CTkLabel(
            vault_frame,
            text="Configuration",
            font=ctk.CTkFont(size=16, weight="normal"),
            text_color=COLORS['text']
        )
        title_label.pack(anchor="w", padx=20, pady=(20, 10))
        
        path_container = ctk.CTkFrame(vault_frame, fg_color="transparent")
        path_container.pack(fill="x", padx=20, pady=(0, 20))
        
        path_label = ctk.CTkLabel(
            path_container,
            text="Vault Folder:",
            font=ctk.CTkFont(size=14),
            text_color=COLORS['text_secondary']
        )
        path_label.pack(anchor="w", pady=(0, 5))
        
        input_frame = ctk.CTkFrame(path_container, fg_color="transparent")
        input_frame.pack(fill="x")
        
        self.path_entry = ctk.CTkEntry(
            input_frame,
            textvariable=self.vault_path,
            placeholder_text="Select Obsidian Vault Folder",
            height=36,
            font=ctk.CTkFont(size=14),
            fg_color="#F2F2F7",
            border_color="#D1D1D6",
            corner_radius=8
        )
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        browse_btn = ctk.CTkButton(
            input_frame,
            text="Search",
            width=100,
            height=36,
            font=ctk.CTkFont(size=14),
            fg_color=COLORS['primary'],
            hover_color="#0051D5",
            corner_radius=8,
            command=self.browse_vault_folder
        )
        browse_btn.pack(side="right")

    def create_sync_options_section(self, parent):
        """Section options de synchronisation"""
        options_frame = ctk.CTkFrame(parent, fg_color="white", corner_radius=12)
        options_frame.pack(fill="x", padx=20, pady=10)
        
        title_label = ctk.CTkLabel(
            options_frame,
            text="Synchronization Options",
            font=ctk.CTkFont(size=16, weight="normal"),
            text_color=COLORS['text']
        )
        title_label.pack(anchor="w", padx=20, pady=(20, 15))
        
        options_container = ctk.CTkFrame(options_frame, fg_color="transparent")
        options_container.pack(fill="x", padx=20, pady=(0, 20))
        
        # Auto-sync
        auto_sync_frame = ctk.CTkFrame(options_container, fg_color="transparent")
        auto_sync_frame.pack(fill="x", pady=(0, 10))
        
        auto_sync_label = ctk.CTkLabel(
            auto_sync_frame,
            text="Automatic Synchronization",
            font=ctk.CTkFont(size=14),
            text_color=COLORS['text']
        )
        auto_sync_label.pack(side="left")
        
        self.auto_sync_switch = ctk.CTkSwitch(
            auto_sync_frame,
            text="",
            variable=self.auto_sync,
            command=self.toggle_auto_sync,
            progress_color=COLORS['primary']
        )
        self.auto_sync_switch.pack(side="right")
        
        # Temps réel
        real_time_frame = ctk.CTkFrame(options_container, fg_color="transparent")
        real_time_frame.pack(fill="x")
        
        real_time_label = ctk.CTkLabel(
            real_time_frame,
            text="Real-time Synchronization",
            font=ctk.CTkFont(size=14),
            text_color=COLORS['text']
        )
        real_time_label.pack(side="left")
        
        self.real_time_switch = ctk.CTkSwitch(
            real_time_frame,
            text="",
            variable=self.real_time_sync,
            command=self.toggle_real_time_sync,
            progress_color=COLORS['primary']
        )
        self.real_time_switch.pack(side="right")

    def create_actions_section(self, parent):
        """Section actions principales"""
        actions_frame = ctk.CTkFrame(parent, fg_color="white", corner_radius=12)
        actions_frame.pack(fill="x", padx=20, pady=10)
        
        title_label = ctk.CTkLabel(
            actions_frame,
            text="Actions",
            font=ctk.CTkFont(size=16, weight="normal"),
            text_color=COLORS['text']
        )
        title_label.pack(anchor="w", padx=20, pady=(20, 15))
        
        buttons_container = ctk.CTkFrame(actions_frame, fg_color="transparent")
        buttons_container.pack(fill="x", padx=20, pady=(0, 20))
        
        # Ligne 1
        row1 = ctk.CTkFrame(buttons_container, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 10))
        
        self.sync_btn = ctk.CTkButton(
            row1,
            text="Synchronize",
            height=44,
            font=ctk.CTkFont(size=16, weight="normal"),
            fg_color=COLORS['primary'],
            hover_color="#0051D5",
            corner_radius=10,
            command=self.full_sync
        )
        self.sync_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.launch_btn = ctk.CTkButton(
            row1,
            text="Start Obsidian",
            height=44,
            font=ctk.CTkFont(size=16, weight="normal"),
            fg_color=COLORS['secondary'],
            hover_color="#6D6D70",
            corner_radius=10,
            command=self.launch_obsidian
        )
        self.launch_btn.pack(side="right", fill="x", expand=True, padx=(5, 0))
        
        # Ligne 2
        row2 = ctk.CTkFrame(buttons_container, fg_color="transparent")
        row2.pack(fill="x")
        
        self.push_btn = ctk.CTkButton(
            row2,
            text="Push Local",
            height=36,
            font=ctk.CTkFont(size=14),
            fg_color="#F2F2F7",
            hover_color="#E5E5EA",
            text_color=COLORS['text'],
            border_color="#D1D1D6",
            border_width=1,
            corner_radius=8,
            command=self.push_local_changes
        )
        self.push_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.pull_btn = ctk.CTkButton(
            row2,
            text="Pull Remote",
            height=36,
            font=ctk.CTkFont(size=14),
            fg_color="#F2F2F7",
            hover_color="#E5E5EA",
            text_color=COLORS['text'],
            border_color="#D1D1D6",
            border_width=1,
            corner_radius=8,
            command=self.pull_remote_changes
        )
        self.pull_btn.pack(side="left", fill="x", expand=True, padx=2.5)
        
        self.snapshot_btn = ctk.CTkButton(
            row2,
            text="Snapshot",
            height=36,
            font=ctk.CTkFont(size=14),
            fg_color="#F2F2F7",
            hover_color="#E5E5EA",
            text_color=COLORS['text'],
            border_color="#D1D1D6",
            border_width=1,
            corner_radius=8,
            command=self.create_snapshot
        )
        self.snapshot_btn.pack(side="right", fill="x", expand=True, padx=(5, 0))

    def create_progress_section(self, parent):
        """Section progress et logs"""
        progress_frame = ctk.CTkFrame(parent, fg_color="white", corner_radius=12)
        progress_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        title_label = ctk.CTkLabel(
            progress_frame,
            text="Journal",
            font=ctk.CTkFont(size=16, weight="normal"),
            text_color=COLORS['text']
        )
        title_label.pack(anchor="w", padx=20, pady=(20, 10))
        
        progress_container = ctk.CTkFrame(progress_frame, fg_color="transparent")
        progress_container.pack(fill="x", padx=20, pady=(0, 15))
        
        self.progress_bar = ctk.CTkProgressBar(
            progress_container,
            height=4,
            corner_radius=2,
            progress_color=COLORS['primary'],
            fg_color="#E5E5EA"
        )
        self.progress_bar.pack(fill="x")
        self.progress_bar.set(0)
        
        self.log_textbox = ctk.CTkTextbox(
            progress_frame,
            font=ctk.CTkFont(family="Courier", size=12),
            fg_color="#F8F8F8",
            border_color="#E5E5EA",
            border_width=1,
            corner_radius=8,
            wrap="word"
        )
        self.log_textbox.pack(fill="both", expand=True, padx=20, pady=(0, 20))

    def create_status_footer(self):
        """Footer avec statut"""
        status_frame = ctk.CTkFrame(self.root, height=40, corner_radius=0, fg_color="white")
        status_frame.pack(fill="x", side="bottom")
        status_frame.pack_propagate(False)
        
        separator = ctk.CTkFrame(status_frame, height=1, fg_color="#E5E5EA")
        separator.pack(fill="x", side="top")
        
        status_container = ctk.CTkFrame(status_frame, fg_color="transparent")
        status_container.pack(fill="both", expand=True, padx=20)
        
        self.connection_status = ctk.CTkLabel(
            status_container,
            text="• Disconnected",
            font=ctk.CTkFont(size=12),
            text_color=COLORS['error']
        )
        self.connection_status.pack(side="left", pady=10)
        
        self.sync_status = ctk.CTkLabel(
            status_container,
            text="Ready",
            font=ctk.CTkFont(size=12),
            text_color=COLORS['text_secondary']
        )
        self.sync_status.pack(side="right", pady=10)

    def get_dropbox_client(self):
        """Obtient le client Dropbox"""
        if not self.dbx:
            self.dbx = dropbox.Dropbox(
                oauth2_refresh_token=DROPBOX_CONFIG["refresh_token"],
                app_key=DROPBOX_CONFIG["app_key"],
                app_secret=DROPBOX_CONFIG["app_secret"]
            )
        return self.dbx

    def init_dropbox(self):
        """Initialise la connexion Dropbox"""
        try:
            self.dbx = self.get_dropbox_client()
            account = self.dbx.users_get_current_account()
            self.connection_status.configure(
                text=f"• Connecté - {account.name.display_name}",
                text_color=COLORS['success']
            )
            self.log_message(f"Connecté à Dropbox: {account.name.display_name}")
        except Exception as e:
            self.connection_status.configure(
                text="• Erreur connexion",
                text_color=COLORS['error']
            )
            self.log_message(f"Erreur connexion Dropbox: {e}")

    def setup_scheduler(self):
        """Configure le planificateur"""
        if self.auto_sync.get():
            interval = self.config.get('sync_interval', 30)
            schedule.every(interval).minutes.do(self.scheduled_sync)
            
            def run_scheduler():
                while self.auto_sync.get():
                    schedule.run_pending()
                    time.sleep(60)
            
            threading.Thread(target=run_scheduler, daemon=True).start()

    def calculate_file_hash(self, file_path: str) -> str:
        """Calcule le hash SHA256 d'un fichier"""
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except Exception:
            return ""

    def get_file_metadata(self, file_path: str):
        """Récupère les métadonnées d'un fichier"""
        try:
            stat = os.stat(file_path)
            return FileMetadata(
                path=file_path,
                size=stat.st_size,
                mtime=stat.st_mtime,
                hash=self.calculate_file_hash(file_path)
            )
        except Exception:
            return None

    def should_ignore_file(self, file_path: str) -> bool:
        """Vérifie si un fichier doit être ignoré"""
        ignore_patterns = self.config.get('ignore_patterns', [])
        for pattern in ignore_patterns:
            if fnmatch.fnmatch(file_path, pattern):
                return True
        return False

    def scan_local_files(self):
        """Scanne les fichiers locaux"""
        vault_path = Path(self.vault_path.get())
        files_metadata = {}
        
        if not vault_path.exists():
            return files_metadata
        
        for file_path in vault_path.rglob('*'):
            if file_path.is_file():
                relative_path = str(file_path.relative_to(vault_path))
                if not self.should_ignore_file(relative_path):
                    metadata = self.get_file_metadata(str(file_path))
                    if metadata:
                        files_metadata[relative_path] = metadata
        
        return files_metadata

    def scan_remote_files(self):
        """Scanne les fichiers distants"""
        files_metadata = {}
        
        try:
            dbx = self.get_dropbox_client()
            
            def list_folder_recursive(path):
                try:
                    result = dbx.files_list_folder(path, recursive=True)
                    entries = result.entries
                    
                    while result.has_more:
                        result = dbx.files_list_folder_continue(result.cursor)
                        entries.extend(result.entries)
                    
                    return entries
                except Exception:
                    return []
            
            entries = list_folder_recursive("/vault")
            
            for entry in entries:
                if hasattr(entry, 'content_hash'):
                    relative_path = entry.path_display[7:]
                    if not self.should_ignore_file(relative_path):
                        files_metadata[relative_path] = FileMetadata(
                            path=relative_path,
                            size=entry.size,
                            mtime=entry.server_modified.timestamp(),
                            hash=entry.content_hash
                        )
        
        except Exception as e:
            self.log_message(f"Erreur scan fichiers distants: {e}")
        
        return files_metadata

    def analyze_sync_actions(self, local_files, remote_files):
        """Analyse les actions de sync nécessaires"""
        actions = []
        all_files = set(local_files.keys()) | set(remote_files.keys())
        
        for file_path in all_files:
            local_meta = local_files.get(file_path)
            remote_meta = remote_files.get(file_path)
            db_meta = self.db.get_file_metadata(file_path)
            
            if local_meta and remote_meta:
                if local_meta.hash != remote_meta.hash:
                    if local_meta.mtime > remote_meta.mtime:
                        actions.append(SyncAction(
                            action='upload',
                            local_path=file_path,
                            remote_path=f"/vault/{file_path}",
                            reason="Version locale plus récente"
                        ))
                    else:
                        actions.append(SyncAction(
                            action='download',
                            local_path=file_path,
                            remote_path=f"/vault/{file_path}",
                            reason="Version distante plus récente"
                        ))
            elif local_meta and not remote_meta:
                actions.append(SyncAction(
                    action='upload',
                    local_path=file_path,
                    remote_path=f"/vault/{file_path}",
                    reason="Nouveau fichier local"
                ))
            elif not local_meta and remote_meta:
                actions.append(SyncAction(
                    action='download',
                    local_path=file_path,
                    remote_path=f"/vault/{file_path}",
                    reason="Nouveau fichier distant"
                ))
        
        return actions

    def execute_sync_actions(self, actions):
        """Exécute les actions de synchronisation"""
        total_actions = len(actions)
        
        if total_actions == 0:
            self.log_message("Vault déjà synchronisé")
            return
        
        self.log_message(f"Exécution de {total_actions} actions")
        
        for i, action in enumerate(actions):
            try:
                progress = (i / total_actions)
                self.progress_bar.set(progress)
                self.root.update()
                
                if action.action == 'upload':
                    self.upload_file(action.local_path, action.remote_path)
                    self.log_message(f"↑ {action.local_path}")
                elif action.action == 'download':
                    self.download_file(action.remote_path, action.local_path)
                    self.log_message(f"↓ {action.local_path}")
                
                self.db.log_sync_action(action.action, action.local_path, "success", action.reason)
                
            except Exception as e:
                self.log_message(f"✗ Erreur {action.local_path}: {e}")
                self.db.log_sync_action(action.action, action.local_path, "error", str(e))
        
        self.progress_bar.set(1.0)
        self.sync_status.configure(text=f"Sync terminée: {total_actions} actions")
        self.log_message(f"Synchronisation terminée: {total_actions} actions")
        
        self.root.after(2000, lambda: self.progress_bar.set(0))

    def upload_file(self, local_path: str, remote_path: str):
        """Upload un fichier vers Dropbox"""
        vault_path = Path(self.vault_path.get())
        full_local_path = vault_path / local_path
        
        try:
            dbx = self.get_dropbox_client()
            with open(full_local_path, 'rb') as f:
                dbx.files_upload(f.read(), remote_path, mode=dropbox.files.WriteMode.overwrite)
            
            metadata = self.get_file_metadata(str(full_local_path))
            if metadata:
                self.db.save_file_metadata(metadata)
        
        except Exception as e:
            raise Exception(f"Erreur upload {local_path}: {e}")

    def download_file(self, remote_path: str, local_path: str):
        """Télécharge un fichier depuis Dropbox"""
        vault_path = Path(self.vault_path.get())
        full_local_path = vault_path / local_path
        
        try:
            full_local_path.parent.mkdir(parents=True, exist_ok=True)
            
            dbx = self.get_dropbox_client()
            metadata, response = dbx.files_download(remote_path)
            
            with open(full_local_path, 'wb') as f:
                f.write(response.content)
            
            file_metadata = self.get_file_metadata(str(full_local_path))
            if file_metadata:
                self.db.save_file_metadata(file_metadata)
        
        except Exception as e:
            raise Exception(f"Erreur download {local_path}: {e}")

    def browse_vault_folder(self):
        """Sélection du dossier vault"""
        folder = filedialog.askdirectory(title="Sélectionner le dossier Vault Obsidian")
        if folder:
            self.vault_path.set(folder)
            self.log_message(f"Vault configuré: {folder}")
            self.save_config()

    def log_message(self, message: str):
        """Ajoute un message au log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"{timestamp}  {message}\n"
        
        self.log_textbox.insert("end", log_entry)
        self.log_textbox.see("end")
        
        lines = self.log_textbox.get("1.0", "end").count('\n')
        if lines > 500:
            self.log_textbox.delete("1.0", "100.0")
        
        self.root.update()
        logging.info(message)

    def toggle_auto_sync(self):
        """Active/désactive la synchronisation automatique"""
        if self.auto_sync.get():
            self.setup_scheduler()
            self.log_message("Synchronisation automatique activée")
            self.sync_status.configure(text="Auto-sync activé")
        else:
            schedule.clear()
            self.log_message("Synchronisation automatique désactivée")
            self.sync_status.configure(text="Auto-sync désactivé")
        self.save_config()

    def toggle_real_time_sync(self):
        """Active/désactive la synchronisation temps réel"""
        if self.real_time_sync.get() and self.vault_path.get():
            self.start_file_watcher()
            self.log_message("Surveillance temps réel activée")
            self.sync_status.configure(text="Temps réel activé")
        else:
            self.stop_file_watcher()
            self.log_message("Surveillance temps réel désactivée")
            self.sync_status.configure(text="Temps réel désactivé")
        self.save_config()

    def start_file_watcher(self):
        """Démarre la surveillance des fichiers"""
        if self.observer:
            self.stop_file_watcher()
        
        vault_path = self.vault_path.get()
        if os.path.exists(vault_path):
            self.file_watcher = FileWatcher(self)
            self.observer = Observer()
            self.observer.schedule(self.file_watcher, vault_path, recursive=True)
            self.observer.start()

    def stop_file_watcher(self):
        """Arrête la surveillance des fichiers"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            self.file_watcher = None

    def full_sync(self):
        """Lance une synchronisation complète"""
        if self.sync_in_progress:
            messagebox.showwarning("Sync en cours", "Une synchronisation est déjà en cours")
            return
        
        if not self.vault_path.get():
            messagebox.showerror("Erreur", "Veuillez sélectionner un dossier vault")
            return
        
        def sync_thread():
            self.sync_in_progress = True
            self.sync_status.configure(text="Synchronisation en cours...")
            self.sync_btn.configure(state="disabled", text="Synchronisation...")
            
            try:
                self.log_message("Début synchronisation complète")
                
                self.log_message("Scan des fichiers locaux...")
                local_files = self.scan_local_files()
                
                self.log_message("Scan des fichiers distants...")
                remote_files = self.scan_remote_files()
                
                self.log_message("Analyse des différences...")
                actions = self.analyze_sync_actions(local_files, remote_files)
                
                self.execute_sync_actions(actions)
                
            except Exception as e:
                self.log_message(f"✗ Erreur synchronisation: {e}")
                messagebox.showerror("Erreur", f"Erreur lors de la synchronisation: {e}")
                self.sync_status.configure(text="Erreur de sync")
            finally:
                self.sync_in_progress = False
                self.sync_btn.configure(state="normal", text="Synchroniser")
                if not self.auto_sync.get() and not self.real_time_sync.get():
                    self.sync_status.configure(text="Prêt")
        
        threading.Thread(target=sync_thread, daemon=True).start()

    def push_local_changes(self):
        """Pousse uniquement les changements locaux"""
        def push_thread():
            try:
                self.sync_status.configure(text="Push en cours...")
                self.log_message("Push des changements locaux...")
                local_files = self.scan_local_files()
                
                for file_path, metadata in local_files.items():
                    db_meta = self.db.get_file_metadata(file_path)
                    
                    if not db_meta or db_meta.hash != metadata.hash:
                        self.upload_file(file_path, f"/vault/{file_path}")
                        self.log_message(f"↑ {file_path}")
                
                self.log_message("Push terminé")
                self.sync_status.configure(text="Push terminé")
            except Exception as e:
                self.log_message(f"✗ Erreur push: {e}")
                self.sync_status.configure(text="Erreur push")
        
        threading.Thread(target=push_thread, daemon=True).start()

    def pull_remote_changes(self):
        """Récupère uniquement les changements distants"""
        def pull_thread():
            try:
                self.sync_status.configure(text="Pull en cours...")
                self.log_message("Pull des changements distants...")
                remote_files = self.scan_remote_files()
                
                for file_path, metadata in remote_files.items():
                    db_meta = self.db.get_file_metadata(file_path)
                    
                    if not db_meta or db_meta.hash != metadata.hash:
                        self.download_file(f"/vault/{file_path}", file_path)
                        self.log_message(f"↓ {file_path}")
                
                self.log_message("Pull terminé")
                self.sync_status.configure(text="Pull terminé")
            except Exception as e:
                self.log_message(f"✗ Erreur pull: {e}")
                self.sync_status.configure(text="Erreur pull")
        
        threading.Thread(target=pull_thread, daemon=True).start()

    def create_snapshot(self):
        """Crée un snapshot du vault actuel"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_name = f"snapshot_{timestamp}"
        
        def create_snapshot_thread():
            try:
                self.sync_status.configure(text="Création snapshot...")
                self.log_message(f"Création du snapshot: {snapshot_name}")
                
                vault_path = Path(self.vault_path.get())
                zip_path = f"{snapshot_name}.zip"
                
                import zipfile
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in vault_path.rglob('*'):
                        if file_path.is_file() and not self.should_ignore_file(str(file_path.relative_to(vault_path))):
                            arcname = file_path.relative_to(vault_path)
                            zipf.write(file_path, arcname)
                
                dbx = self.get_dropbox_client()
                with open(zip_path, 'rb') as f:
                    dbx.files_upload(f.read(), f"/vault_snapshots/{zip_path}")
                
                os.remove(zip_path)
                
                self.log_message(f"Snapshot créé: {snapshot_name}")
                self.sync_status.configure(text="Snapshot créé")
                
            except Exception as e:
                self.log_message(f"✗ Erreur création snapshot: {e}")
                self.sync_status.configure(text="Erreur snapshot")
        
        threading.Thread(target=create_snapshot_thread, daemon=True).start()

    def find_obsidian_executable(self):
        """Trouve automatiquement l'exécutable Obsidian"""
        import platform
        import glob
        
        system = platform.system()
        possible_paths = []
        
        if system == "Windows":
            # Chemins Windows typiques
            possible_paths = [
                os.path.expanduser("~/AppData/Local/Obsidian/Obsidian.exe"),
                os.path.expanduser("~/AppData/Local/Programs/Obsidian/Obsidian.exe"),
                "C:/Program Files/Obsidian/Obsidian.exe",
                "C:/Program Files (x86)/Obsidian/Obsidian.exe",
                os.path.expanduser("~/scoop/apps/obsidian/current/Obsidian.exe"),
                os.path.expanduser("~/AppData/Local/obsidian/Obsidian.exe")
            ]
            
        elif system == "Darwin":  # macOS
            # Chemins macOS typiques
            possible_paths = [
                "/Applications/Obsidian.app",
                os.path.expanduser("~/Applications/Obsidian.app"),
                "/System/Applications/Obsidian.app"
            ]
            
        else:  # Linux
            # Chemins Linux typiques
            possible_paths = [
                # AppImage dans différents dossiers
                os.path.expanduser("~/Applications/Obsidian.AppImage"),
                os.path.expanduser("~/Downloads/Obsidian*.AppImage"),
                os.path.expanduser("~/.local/bin/Obsidian.AppImage"),
                "/opt/Obsidian/Obsidian.AppImage",
                "/usr/local/bin/Obsidian.AppImage",
                # Installations package
                "/usr/bin/obsidian",
                "/usr/local/bin/obsidian",
                # Flatpak
                "/var/lib/flatpak/exports/bin/md.obsidian.Obsidian",
                os.path.expanduser("~/.local/share/flatpak/exports/bin/md.obsidian.Obsidian")
            ]
            
            # Cherche aussi avec which
            try:
                which_result = subprocess.run(['which', 'obsidian'], 
                                            capture_output=True, text=True)
                if which_result.returncode == 0:
                    possible_paths.insert(0, which_result.stdout.strip())
            except:
                pass
            
            # Cherche snap
            try:
                if subprocess.run(['which', 'obsidian.obsidian'], 
                                capture_output=True).returncode == 0:
                    possible_paths.insert(0, 'obsidian.obsidian')
            except:
                pass
        
        # Vérifie chaque chemin possible
        for path in possible_paths:
            # Gère les wildcards pour Linux AppImage
            if '*' in path:
                matches = glob.glob(path)
                if matches:
                    # Prend le plus récent
                    path = max(matches, key=os.path.getctime)
            
            if os.path.exists(path) or (system != "Windows" and path in ['obsidian', 'obsidian.obsidian']):
                self.log_message(f"Obsidian trouvé: {path}")
                return path
        
        # Si rien trouvé, demande à l'utilisateur
        self.log_message("Obsidian non trouvé automatiquement")
        
        if system == "Windows":
            file_types = [("Exécutables", "*.exe"), ("Tous fichiers", "*.*")]
            title = "Sélectionner Obsidian.exe"
        elif system == "Darwin":
            file_types = [("Applications", "*.app"), ("Tous fichiers", "*.*")]
            title = "Sélectionner Obsidian.app"
        else:
            file_types = [("AppImage", "*.AppImage"), ("Exécutables", "*"), ("Tous fichiers", "*.*")]
            title = "Sélectionner l'exécutable Obsidian"
        
        obsidian_path = filedialog.askopenfilename(
            title=title,
            filetypes=file_types
        )
        
        if obsidian_path:
            self.log_message(f"Obsidian sélectionné: {obsidian_path}")
            # Sauvegarde le chemin dans la config
            self.config['obsidian_path'] = obsidian_path
            self.save_config()
            return obsidian_path
        
        return None

    def launch_obsidian(self):
        """Lance Obsidian avec le vault configuré"""
        vault_path = self.vault_path.get()
        
        if not vault_path or not os.path.exists(vault_path):
            messagebox.showerror("Erreur", "Dossier vault introuvable")
            return
        
        # Cherche Obsidian dans la config d'abord
        obsidian_path = self.config.get('obsidian_path')
        
        # Si pas dans la config, cherche automatiquement
        if not obsidian_path or not os.path.exists(obsidian_path):
            obsidian_path = self.find_obsidian_executable()
        
        if not obsidian_path:
            messagebox.showerror("Erreur", "Impossible de trouver Obsidian")
            return
        
        try:
            import platform
            system = platform.system()
            
            if system == "Windows":
                # Windows - Lance directement l'exe
                subprocess.Popen([obsidian_path, vault_path])
                
            elif system == "Darwin":  # macOS
                if obsidian_path.endswith('.app'):
                    # Lance l'app bundle avec open
                    subprocess.Popen(['open', '-a', obsidian_path, vault_path])
                else:
                    # Lance directement l'exécutable
                    subprocess.Popen([obsidian_path, vault_path])
                    
            else:  # Linux
                if obsidian_path in ['obsidian', 'obsidian.obsidian']:
                    # Commande système
                    subprocess.Popen([obsidian_path, vault_path])
                elif obsidian_path.endswith('.AppImage'):
                    # AppImage - doit être exécutable
                    if not os.access(obsidian_path, os.X_OK):
                        os.chmod(obsidian_path, 0o755)
                    subprocess.Popen([obsidian_path, vault_path])
                else:
                    # Autre exécutable
                    subprocess.Popen([obsidian_path, vault_path])
            
            self.log_message(f"Obsidian lancé avec vault: {vault_path}")
            
        except Exception as e:
            # En cas d'erreur, propose de re-sélectionner Obsidian
            error_msg = f"Erreur lors du lancement: {e}\n\nVoulez-vous sélectionner un autre exécutable Obsidian?"
            
            if messagebox.askyesno("Erreur", error_msg):
                # Supprime le chemin sauvegardé et re-cherche
                if 'obsidian_path' in self.config:
                    del self.config['obsidian_path']
                    self.save_config()
                self.launch_obsidian()  # Re-essaie
            else:
                self.log_message(f"Échec lancement Obsidian: {e}")

    def scheduled_sync(self):
        """Synchronisation programmée"""
        if not self.sync_in_progress:
            self.log_message("Synchronisation automatique")
            self.full_sync()

    def schedule_file_sync(self, file_path: str):
        """Planifie la synchronisation d'un fichier spécifique"""
        if not self.sync_in_progress:
            def sync_single_file():
                try:
                    relative_path = os.path.relpath(file_path, self.vault_path.get())
                    self.upload_file(relative_path, f"/vault/{relative_path}")
                    self.log_message(f"⟳ Sync temps réel: {relative_path}")
                except Exception as e:
                    self.log_message(f"✗ Erreur sync temps réel {relative_path}: {e}")
            
            threading.Thread(target=sync_single_file, daemon=True).start()

    def on_closing(self):
        """Événement de fermeture de l'application"""
        self.stop_file_watcher()
        self.save_config()
        
        if self.sync_in_progress:
            choice = messagebox.askyesno(
                "Synchronisation en cours",
                "Une synchronisation est en cours. Voulez-vous vraiment quitter?"
            )
            if not choice:
                return
        
        self.log_message("Fermeture de l'application")
        self.root.destroy()

    def run(self):
        """Lance l'application"""
        self.root.mainloop()


def main():
    """Point d'entrée principal"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler('vault_manager.log', encoding='utf-8')]
    )
    
    try:
        import customtkinter
    except ImportError:
        import tkinter.messagebox as mb
        mb.showerror(
            "Dépendance manquante",
            "CustomTkinter n'est pas installé.\n\n"
            "Installez-le avec:\n"
            "pip install customtkinter\n\n"
            "Puis relancez l'application."
        )
        return
    
    try:
        app = ObsidianVaultManager()
        app.run()
    
    except Exception as e:
        logging.error(f"Erreur fatale: {e}")
        try:
            messagebox.showerror("Erreur Fatale", f"Une erreur fatale s'est produite: {e}")
        except:
            print(f"Erreur fatale: {e}")


if __name__ == "__main__":
    main()