#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dropbox Explorer - Version corrigée avec prévisualisation Markdown
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import dropbox
import threading
from datetime import datetime
import os
import tempfile
from pathlib import Path

# Configuration du thème
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# Couleurs
COLORS = {
    'primary': '#007AFF',
    'secondary': '#8E8E93',
    'success': '#34C759',
    'error': '#FF3B30',
    'warning': '#FF9500',
    'background': '#F2F2F7',
    'surface': '#FFFFFF',
    'text': '#1C1C1E',
    'text_secondary': '#8E8E93',
    'folder': '#007AFF',
    'file': '#1C1C1E'
}

# Configuration Dropbox
DROPBOX_CONFIG = {
    "app_key": "",
    "app_secret": "",
    "refresh_token": ""
}

class FileItem:
    """Représente un fichier ou dossier"""
    def __init__(self, name, path, is_folder, size=0, modified=None, file_type=""):
        self.name = name
        self.path = path
        self.is_folder = is_folder
        self.size = size
        self.modified = modified or datetime.now()
        self.file_type = file_type

class MarkdownPreviewDialog:
    """Dialog de prévisualisation Markdown"""
    
    def __init__(self, parent, content, filename):
        self.dialog = ctk.CTkToplevel(parent)
        self.dialog.title(f"📝 Aperçu - {filename}")
        self.dialog.geometry("800x600")
        self.dialog.transient(parent)
        
        # Centre la fenêtre
        self.dialog.geometry("+%d+%d" % (
            parent.winfo_rootx() + 50,
            parent.winfo_rooty() + 50
        ))
        
        self.create_ui(content, filename)
    
    def create_ui(self, content, filename):
        """Interface de prévisualisation"""
        # Header
        header = ctk.CTkFrame(self.dialog, fg_color="white", corner_radius=0, height=60)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        title = ctk.CTkLabel(header, text=f"📝 {filename}",
                           font=ctk.CTkFont(size=18, weight="bold"),
                           text_color=COLORS['text'])
        title.pack(pady=20)
        
        # Contenu
        content_frame = ctk.CTkFrame(self.dialog, fg_color="white")
        content_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        # Zone de texte avec le contenu Markdown
        self.text_area = ctk.CTkTextbox(
            content_frame,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#F8F8F8",
            text_color=COLORS['text'],
            wrap="word"
        )
        self.text_area.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Affiche le contenu
        self.text_area.insert("1.0", content)
        self.text_area.configure(state="disabled")  # Lecture seule
        
        # Boutons
        button_frame = ctk.CTkFrame(self.dialog, fg_color="white", corner_radius=0)
        button_frame.pack(fill="x")
        
        buttons = ctk.CTkFrame(button_frame, fg_color="transparent")
        buttons.pack(pady=20)
        
        close_btn = ctk.CTkButton(buttons, text="Fermer", width=120, height=40,
                                 font=ctk.CTkFont(size=14), fg_color=COLORS['secondary'],
                                 command=self.close)
        close_btn.pack(side="left", padx=(0, 15))
        
        copy_btn = ctk.CTkButton(buttons, text="📋 Copier le texte", width=150, height=40,
                               font=ctk.CTkFont(size=14), fg_color=COLORS['primary'],
                               command=self.copy_content)
        copy_btn.pack(side="right")
        
        self.content = content
    
    def copy_content(self):
        """Copie le contenu dans le presse-papier"""
        self.dialog.clipboard_clear()
        self.dialog.clipboard_append(self.content)
        messagebox.showinfo("Copié", "Le contenu a été copié dans le presse-papier !")
    
    def close(self):
        """Ferme le dialog"""
        self.dialog.destroy()

class DropboxExplorer:
    """Explorateur Dropbox simplifié"""
    
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("🔍 Dropbox Explorer")
        self.root.geometry("1200x800")
        
        # Variables
        self.dbx = None
        self.current_path = ""
        self.current_items = []
        self.selected_item = None
        self.loading = False
        
        # Interface
        self.create_interface()
        self.init_dropbox()
    
    def create_interface(self):
        """Interface principale"""
        # Header
        self.create_header()
        
        # Body
        body = ctk.CTkFrame(self.root, fg_color=COLORS['background'])
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Layout 2 colonnes
        self.create_main_layout(body)
        
        # Footer
        self.create_footer()
    
    def create_header(self):
        """Header avec navigation"""
        header = ctk.CTkFrame(self.root, height=70, fg_color="white", corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        nav = ctk.CTkFrame(header, fg_color="transparent")
        nav.pack(fill="x", padx=20, pady=15)
        
        # Boutons navigation
        nav_buttons = ctk.CTkFrame(nav, fg_color="transparent")
        nav_buttons.pack(side="left")
        
        self.back_btn = ctk.CTkButton(nav_buttons, text="←", width=40, height=40,
                                     font=ctk.CTkFont(size=16), fg_color=COLORS['secondary'],
                                     command=self.go_back, state="disabled")
        self.back_btn.pack(side="left", padx=(0, 5))
        
        self.up_btn = ctk.CTkButton(nav_buttons, text="↑", width=40, height=40,
                                   font=ctk.CTkFont(size=16), fg_color=COLORS['secondary'],
                                   command=self.go_up, state="disabled")
        self.up_btn.pack(side="left", padx=(0, 15))
        
        # Chemin actuel
        self.path_label = ctk.CTkLabel(nav, text="📁 /", font=ctk.CTkFont(size=14),
                                      text_color=COLORS['text'])
        self.path_label.pack(side="left", fill="x", expand=True)
        
        # Boutons action
        action_buttons = ctk.CTkFrame(nav, fg_color="transparent")
        action_buttons.pack(side="right")
        
        self.refresh_btn = ctk.CTkButton(action_buttons, text="🔄", width=40, height=40,
                                        font=ctk.CTkFont(size=14), fg_color=COLORS['primary'],
                                        command=self.refresh)
        self.refresh_btn.pack(side="left", padx=(0, 5))
        
        self.home_btn = ctk.CTkButton(action_buttons, text="🏠", width=40, height=40,
                                     font=ctk.CTkFont(size=14), fg_color=COLORS['primary'],
                                     command=lambda: self.navigate_to(""))
        self.home_btn.pack(side="left")
    
    def create_main_layout(self, parent):
        """Layout principal"""
        # Colonne gauche - Liste
        left_panel = ctk.CTkFrame(parent, fg_color="white", corner_radius=10)
        left_panel.pack(side="left", fill="both", expand=True, padx=(0, 5), pady=5)
        
        self.create_file_browser(left_panel)
        
        # Colonne droite - Détails
        right_panel = ctk.CTkFrame(parent, fg_color="white", corner_radius=10, width=350)
        right_panel.pack(side="right", fill="y", padx=(5, 0), pady=5)
        right_panel.pack_propagate(False)
        
        self.create_details_panel(right_panel)
    
    def create_file_browser(self, parent):
        """Panneau de fichiers"""
        # Header
        header = ctk.CTkFrame(parent, fg_color="transparent", height=50)
        header.pack(fill="x", padx=20, pady=(20, 0))
        header.pack_propagate(False)
        
        self.folder_title = ctk.CTkLabel(header, text="📁 Dropbox",
                                        font=ctk.CTkFont(size=18, weight="bold"),
                                        text_color=COLORS['text'])
        self.folder_title.pack(side="left")
        
        self.item_count = ctk.CTkLabel(header, text="0 éléments",
                                      font=ctk.CTkFont(size=12),
                                      text_color=COLORS['text_secondary'])
        self.item_count.pack(side="right")
        
        # Liste
        list_container = ctk.CTkFrame(parent, fg_color="transparent")
        list_container.pack(fill="both", expand=True, padx=20, pady=(15, 20))
        
        self.file_list = ctk.CTkScrollableFrame(list_container, fg_color="#F8F8F8", corner_radius=8)
        self.file_list.pack(fill="both", expand=True)
    
    def create_details_panel(self, parent):
        """Panneau de détails"""
        # Header
        details_header = ctk.CTkLabel(parent, text="📋 Détails",
                                     font=ctk.CTkFont(size=16, weight="bold"),
                                     text_color=COLORS['text'])
        details_header.pack(anchor="w", padx=20, pady=(20, 15))
        
        # Zone détails
        self.details_frame = ctk.CTkScrollableFrame(parent, fg_color="#F8F8F8", corner_radius=8)
        self.details_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        self.show_no_selection()
    
    def create_footer(self):
        """Footer"""
        footer = ctk.CTkFrame(self.root, height=35, fg_color="white", corner_radius=0)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        
        separator = ctk.CTkFrame(footer, height=1, fg_color="#E5E5EA")
        separator.pack(fill="x", side="top")
        
        status_container = ctk.CTkFrame(footer, fg_color="transparent")
        status_container.pack(fill="both", expand=True, padx=15)
        
        self.connection_status = ctk.CTkLabel(status_container, text="• Déconnecté",
                                            font=ctk.CTkFont(size=11), text_color=COLORS['error'])
        self.connection_status.pack(side="left", pady=8)
        
        self.status_info = ctk.CTkLabel(status_container, text="Prêt",
                                       font=ctk.CTkFont(size=11), text_color=COLORS['text_secondary'])
        self.status_info.pack(side="right", pady=8)
    
    def init_dropbox(self):
        """Initialise Dropbox"""
        def init_thread():
            try:
                self.dbx = dropbox.Dropbox(
                    oauth2_refresh_token=DROPBOX_CONFIG["refresh_token"],
                    app_key=DROPBOX_CONFIG["app_key"],
                    app_secret=DROPBOX_CONFIG["app_secret"]
                )
                
                account = self.dbx.users_get_current_account()
                self.root.after(0, lambda: self.connection_status.configure(
                    text=f"• Connecté - {account.name.display_name}",
                    text_color=COLORS['success']
                ))
                
                self.root.after(0, lambda: self.load_folder(""))
                
            except Exception as e:
                self.root.after(0, lambda: self.show_connection_error(str(e)))
        
        threading.Thread(target=init_thread, daemon=True).start()
    
    def show_connection_error(self, error):
        """Erreur de connexion"""
        self.connection_status.configure(text="• Erreur connexion", text_color=COLORS['error'])
        messagebox.showerror("Erreur Dropbox", f"Impossible de se connecter:\n{error}")
    
    def load_folder(self, path):
        """Charge un dossier"""
        if self.loading or not self.dbx:
            return
        
        def load_thread():
            self.loading = True
            self.root.after(0, self.show_loading)
            
            try:
                result = self.dbx.files_list_folder(path, recursive=False)
                
                items = []
                for entry in result.entries:
                    if isinstance(entry, dropbox.files.FolderMetadata):
                        items.append(FileItem(
                            name=entry.name,
                            path=entry.path_display,
                            is_folder=True,
                            file_type="Dossier"
                        ))
                    elif isinstance(entry, dropbox.files.FileMetadata):
                        items.append(FileItem(
                            name=entry.name,
                            path=entry.path_display,
                            is_folder=False,
                            size=entry.size,
                            modified=entry.server_modified,
                            file_type=self.get_file_type(entry.name)
                        ))
                
                self.root.after(0, lambda: self.update_file_list(items, path))
                
            except Exception as e:
                self.root.after(0, lambda: self.show_error(f"Erreur: {e}"))
            finally:
                self.loading = False
        
        threading.Thread(target=load_thread, daemon=True).start()
    
    def show_loading(self):
        """Chargement"""
        for widget in self.file_list.winfo_children():
            widget.destroy()
        
        loading_label = ctk.CTkLabel(self.file_list, text="⏳ Chargement...",
                                    font=ctk.CTkFont(size=14),
                                    text_color=COLORS['text_secondary'])
        loading_label.pack(expand=True, pady=50)
        
        self.status_info.configure(text="Chargement...")
    
    def update_file_list(self, items, path):
        """Met à jour la liste"""
        self.current_items = items
        self.current_path = path
        
        # Met à jour l'affichage
        folder_name = os.path.basename(path) if path else "Dropbox"
        self.folder_title.configure(text=f"📁 {folder_name}")
        self.item_count.configure(text=f"{len(items)} éléments")
        self.path_label.configure(text=f"📁 /{path}" if path else "📁 /")
        
        # Trie et affiche
        items.sort(key=lambda x: (not x.is_folder, x.name.lower()))
        self.display_files()
        
        # Met à jour navigation
        self.up_btn.configure(state="normal" if path else "disabled")
        self.status_info.configure(text="Prêt")
    
    def display_files(self):
        """Affiche les fichiers"""
        for widget in self.file_list.winfo_children():
            widget.destroy()
        
        if not self.current_items:
            empty_label = ctk.CTkLabel(self.file_list, text="📭 Dossier vide",
                                      font=ctk.CTkFont(size=14),
                                      text_color=COLORS['text_secondary'])
            empty_label.pack(expand=True, pady=50)
            return
        
        for item in self.current_items:
            self.create_file_item(item)
    
    def create_file_item(self, item):
        """Crée un élément de fichier - VERSION SIMPLIFIÉE"""
        # Frame principal
        item_frame = ctk.CTkFrame(self.file_list, fg_color="white", corner_radius=6)
        item_frame.pack(fill="x", padx=5, pady=2)
        
        # Container
        container = ctk.CTkFrame(item_frame, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=12, pady=8)
        
        # Icône
        icon = "📁" if item.is_folder else self.get_file_icon(item.name)
        icon_label = ctk.CTkLabel(container, text=icon, font=ctk.CTkFont(size=20), width=30)
        icon_label.pack(side="left", padx=(0, 10))
        
        # Info
        info_frame = ctk.CTkFrame(container, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True)
        
        # Nom
        name_color = COLORS['folder'] if item.is_folder else COLORS['text']
        name_label = ctk.CTkLabel(info_frame, text=item.name,
                                 font=ctk.CTkFont(size=13, weight="bold"),
                                 text_color=name_color, anchor="w")
        name_label.pack(anchor="w", fill="x")
        
        # Détails pour fichiers
        if not item.is_folder:
            details = f"{self.format_size(item.size)} • {item.modified.strftime('%d/%m/%Y')}"
            details_label = ctk.CTkLabel(info_frame, text=details,
                                        font=ctk.CTkFont(size=10),
                                        text_color=COLORS['text_secondary'], anchor="w")
            details_label.pack(anchor="w", fill="x")
        
        # Actions pour fichiers
        if not item.is_folder:
            actions_frame = ctk.CTkFrame(container, fg_color="transparent")
            actions_frame.pack(side="right")
            
            # Télécharger
            download_btn = ctk.CTkButton(actions_frame, text="📥", width=30, height=30,
                                        font=ctk.CTkFont(size=12), fg_color=COLORS['primary'],
                                        command=lambda i=item: self.download_file(i))
            download_btn.pack(side="right", padx=(5, 0))
            
            # Prévisualiser Markdown
            if item.name.lower().endswith('.md'):
                preview_btn = ctk.CTkButton(actions_frame, text="👁", width=30, height=30,
                                           font=ctk.CTkFont(size=12), fg_color=COLORS['warning'],
                                           command=lambda i=item: self.preview_markdown(i))
                preview_btn.pack(side="right", padx=(5, 0))
        
        # Événements de clic - VERSION SIMPLIFIÉE
        def on_click(event):
            self.select_item(item)
        
        def on_double_click(event):
            if item.is_folder:
                self.navigate_to(item.path)
        
        # Bind sur les widgets principaux seulement
        for widget in [item_frame, container, icon_label, name_label]:
            widget.bind("<Button-1>", on_click)
            widget.bind("<Double-Button-1>", on_double_click)
    
    def select_item(self, item):
        """Sélectionne un item - VERSION SIMPLIFIÉE"""
        self.selected_item = item
        self.show_file_details(item)
    
    def show_file_details(self, item):
        """Détails du fichier"""
        for widget in self.details_frame.winfo_children():
            widget.destroy()
        
        # Icône et nom
        icon = "📁" if item.is_folder else self.get_file_icon(item.name)
        icon_label = ctk.CTkLabel(self.details_frame, text=icon, font=ctk.CTkFont(size=32))
        icon_label.pack(pady=(10, 10))
        
        name_label = ctk.CTkLabel(self.details_frame, text=item.name,
                                 font=ctk.CTkFont(size=14, weight="bold"),
                                 text_color=COLORS['text'], wraplength=300)
        name_label.pack(pady=(0, 15))
        
        # Informations
        self.create_info_row("Type", "Dossier" if item.is_folder else item.file_type)
        self.create_info_row("Chemin", item.path)
        
        if not item.is_folder:
            self.create_info_row("Taille", self.format_size(item.size))
            self.create_info_row("Modifié", item.modified.strftime('%d/%m/%Y'))
        
        # Actions
        if not item.is_folder:
            actions_frame = ctk.CTkFrame(self.details_frame, fg_color="transparent")
            actions_frame.pack(fill="x", pady=(15, 0))
            
            # Télécharger
            download_btn = ctk.CTkButton(actions_frame, text="📥 Télécharger",
                                        font=ctk.CTkFont(size=12), fg_color=COLORS['primary'],
                                        height=35, command=lambda: self.download_file(item))
            download_btn.pack(fill="x", pady=(0, 8))
            
            # Prévisualiser Markdown
            if item.name.lower().endswith('.md'):
                preview_btn = ctk.CTkButton(actions_frame, text="📝 Aperçu Markdown",
                                           font=ctk.CTkFont(size=12), fg_color=COLORS['warning'],
                                           height=35, command=lambda: self.preview_markdown(item))
                preview_btn.pack(fill="x")
    
    def create_info_row(self, label, value):
        """Ligne d'info"""
        row = ctk.CTkFrame(self.details_frame, fg_color="transparent")
        row.pack(fill="x", pady=2)
        
        label_widget = ctk.CTkLabel(row, text=f"{label}:",
                                   font=ctk.CTkFont(size=11, weight="bold"),
                                   text_color=COLORS['text_secondary'], anchor="w", width=60)
        label_widget.pack(side="left")
        
        value_widget = ctk.CTkLabel(row, text=value,
                                   font=ctk.CTkFont(size=11), text_color=COLORS['text'],
                                   anchor="w", wraplength=220)
        value_widget.pack(side="left", fill="x", expand=True, padx=(5, 0))
    
    def show_no_selection(self):
        """Pas de sélection"""
        for widget in self.details_frame.winfo_children():
            widget.destroy()
        
        icon = ctk.CTkLabel(self.details_frame, text="📂", font=ctk.CTkFont(size=32))
        icon.pack(pady=(30, 10))
        
        text = ctk.CTkLabel(self.details_frame,
                           text="Sélectionnez un fichier\npour voir ses détails",
                           font=ctk.CTkFont(size=12), text_color=COLORS['text_secondary'])
        text.pack()
    
    def show_error(self, message):
        """Erreur"""
        for widget in self.file_list.winfo_children():
            widget.destroy()
        
        error_label = ctk.CTkLabel(self.file_list, text=f"❌ {message}",
                                  font=ctk.CTkFont(size=14), text_color=COLORS['error'])
        error_label.pack(expand=True, pady=50)
        
        self.status_info.configure(text="Erreur")
    
    # Navigation
    def navigate_to(self, path):
        """Navigue vers un chemin"""
        self.load_folder(path)
    
    def go_back(self):
        """Retour (simplifié)"""
        if self.current_path:
            parent = str(Path(self.current_path).parent)
            if parent == "." or parent == "/":
                parent = ""
            self.navigate_to(parent)
    
    def go_up(self):
        """Monte d'un niveau"""
        self.go_back()
    
    def refresh(self):
        """Actualise"""
        self.load_folder(self.current_path)
    
    # Actions fichiers
    def download_file(self, item):
        """Télécharge - VERSION CORRIGÉE"""
        save_path = filedialog.asksaveasfilename(
            title="Enregistrer le fichier",
            initialfile=item.name,  # CORRIGÉ: initialfile au lieu de initialname
            defaultextension=os.path.splitext(item.name)[1]
        )
        
        if save_path:
            def download_thread():
                try:
                    self.root.after(0, lambda: self.status_info.configure(text="Téléchargement..."))
                    
                    metadata, response = self.dbx.files_download(item.path)
                    
                    with open(save_path, 'wb') as f:
                        f.write(response.content)
                    
                    self.root.after(0, lambda: self.status_info.configure(text="Téléchargé !"))
                    self.root.after(0, lambda: messagebox.showinfo("Succès", f"Fichier téléchargé:\n{save_path}"))
                    
                except Exception as e:
                    error_msg = str(e)
                    self.root.after(0, lambda: self.status_info.configure(text="Erreur téléchargement"))
                    self.root.after(0, lambda: messagebox.showerror("Erreur", f"Erreur téléchargement:\n{error_msg}"))
            
            threading.Thread(target=download_thread, daemon=True).start()
    
    def preview_markdown(self, item):
        """Prévisualise un fichier Markdown"""
        def preview_thread():
            try:
                self.root.after(0, lambda: self.status_info.configure(text="Chargement aperçu..."))
                
                # Télécharge le contenu
                metadata, response = self.dbx.files_download(item.path)
                
                # Décode le contenu
                try:
                    content = response.content.decode('utf-8')
                except UnicodeDecodeError:
                    content = response.content.decode('utf-8', errors='ignore')
                
                # Affiche l'aperçu
                self.root.after(0, lambda: self.show_markdown_preview(content, item.name))
                self.root.after(0, lambda: self.status_info.configure(text="Aperçu ouvert"))
                
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: self.status_info.configure(text="Erreur aperçu"))
                self.root.after(0, lambda: messagebox.showerror("Erreur", f"Erreur aperçu:\n{error_msg}"))
        
        threading.Thread(target=preview_thread, daemon=True).start()
    
    def show_markdown_preview(self, content, filename):
        """Affiche l'aperçu Markdown"""
        MarkdownPreviewDialog(self.root, content, filename)
    
    # Utilitaires
    def get_file_type(self, filename):
        """Type de fichier"""
        ext = os.path.splitext(filename)[1].lower()
        type_map = {
            '.md': 'Markdown', '.txt': 'Texte', '.pdf': 'PDF',
            '.jpg': 'Image', '.png': 'Image', '.docx': 'Word',
            '.xlsx': 'Excel', '.json': 'JSON'
        }
        return type_map.get(ext, f'Fichier {ext.upper()}' if ext else 'Fichier')
    
    def get_file_icon(self, filename):
        """Icône de fichier"""
        ext = os.path.splitext(filename)[1].lower()
        icon_map = {
            '.md': '📝', '.txt': '📄', '.pdf': '📕',
            '.jpg': '🖼️', '.png': '🖼️', '.docx': '📘',
            '.xlsx': '📊', '.json': '⚙️'
        }
        return icon_map.get(ext, '📄')
    
    def format_size(self, size):
        """Formate la taille"""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.1f} GB"
    
    def run(self):
        """Lance l'explorateur"""
        self.root.mainloop()


def main():
    """Point d'entrée"""
    print("🚀 Lancement Dropbox Explorer (Version corrigée)...")
    print("📝 Fonctionnalités:")
    print("   • Navigation dans Dropbox")
    print("   • Téléchargement de fichiers")
    print("   • Prévisualisation Markdown (.md)")
    print("   • Interface simplifiée et stable")
    print("")
    
    try:
        app = DropboxExplorer()
        app.run()
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
