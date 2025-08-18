#!/usr/bin/env python3
"""
GUI pro hromadné přejmenování RAW souborů podle odpovídajících JPG souborů na základě vizuální podobnosti obrazu.
"""

import os
import sys
import json
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

try:
    from PIL import Image, ImageTk
    import imagehash
except ImportError:
    print("Chyba: Potřebné knihovny nejsou nainstalovány.")
    print("Nainstalujte je pomocí: pip install Pillow imagehash")
    sys.exit(1)

# Konfigurace
RAW_EXTENSIONS = {'.cr2', '.nef', '.arw', '.dng', '.raf', '.orf', '.rw2', '.pef', '.srw'}
JPG_EXTENSIONS = {'.jpg', '.jpeg'}
HASH_SIZE = 16
DEFAULT_SIMILARITY_THRESHOLD = 5
CONFIG_FILE = "renamer_config.json"
THUMBNAIL_SIZE = (80, 60)  # Velikost náhledů pro detail

class FileRenamerCore:
    """Základní logika pro přejmenování souborů"""
    
    def __init__(self, raw_folder_path: str, jpg_folder_path: str, similarity_threshold: int = DEFAULT_SIMILARITY_THRESHOLD):
        self.raw_folder_path = Path(raw_folder_path)
        self.jpg_folder_path = Path(jpg_folder_path)
        self.similarity_threshold = similarity_threshold
        self.raw_files = []
        self.jpg_files = []
        self.pairs = []
        self.log_file = None

    def scan_files(self) -> Tuple[int, int]:
        """Prohledá složky a rozdělí soubory na RAW a JPG."""
        self.raw_files = []
        self.jpg_files = []
        
        if not self.raw_folder_path.exists():
            raise FileNotFoundError(f"RAW složka {self.raw_folder_path} neexistuje.")
        
        if not self.jpg_folder_path.exists():
            raise FileNotFoundError(f"JPG složka {self.jpg_folder_path} neexistuje.")

        # Skenování RAW souborů
        for file_path in self.raw_folder_path.iterdir():
            if file_path.is_file():
                ext = file_path.suffix.lower()
                if ext in RAW_EXTENSIONS:
                    self.raw_files.append(file_path)

        # Skenování JPG souborů
        for file_path in self.jpg_folder_path.iterdir():
            if file_path.is_file():
                ext = file_path.suffix.lower()
                if ext in JPG_EXTENSIONS:
                    self.jpg_files.append(file_path)

        return len(self.raw_files), len(self.jpg_files)

    def calculate_image_hash(self, image_path: Path) -> Optional[imagehash.ImageHash]:
        """Vypočítá perceptual hash obrázku."""
        try:
            with Image.open(image_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                dhash = imagehash.dhash(img, hash_size=HASH_SIZE)
                return dhash
        except Exception:
            return None

    def find_pairs(self, progress_callback=None) -> List[Tuple[Path, Path, int]]:
        """Najde páry RAW a JPG souborů na základě vizuální podobnosti."""
        self.pairs = []
        
        # Vypočítáme hashe pro všechny JPG soubory
        jpg_hashes = {}
        total_files = len(self.jpg_files) + len(self.raw_files)
        processed = 0
        
        for jpg_file in self.jpg_files:
            hash_value = self.calculate_image_hash(jpg_file)
            if hash_value is not None:
                jpg_hashes[jpg_file] = hash_value
            processed += 1
            if progress_callback:
                progress_callback(processed, total_files, f"Zpracovávám JPG: {jpg_file.name}")

        # Pro každý RAW soubor najdeme nejpodobnější JPG
        for raw_file in self.raw_files:
            raw_hash = self.calculate_image_hash(raw_file)
            processed += 1
            if progress_callback:
                progress_callback(processed, total_files, f"Zpracovávám RAW: {raw_file.name}")
            
            if raw_hash is None:
                continue
                
            best_match = None
            best_similarity = float('inf')
            
            for jpg_file, jpg_hash in jpg_hashes.items():
                similarity = raw_hash - jpg_hash
                if similarity < best_similarity and similarity <= self.similarity_threshold:
                    best_similarity = similarity
                    best_match = jpg_file
            
            if best_match is not None:
                self.pairs.append((raw_file, best_match, best_similarity))

        return self.pairs

    def generate_rename_plan(self) -> List[Tuple[Path, Path]]:
        """Vygeneruje plán přejmenování."""
        rename_plan = []
        
        for raw_file, jpg_file, similarity in self.pairs:
            new_raw_name = jpg_file.stem + raw_file.suffix
            new_raw_path = raw_file.parent / new_raw_name
            
            if new_raw_path.exists() and new_raw_path != raw_file:
                continue
                
            if raw_file != new_raw_path:
                rename_plan.append((raw_file, new_raw_path))
        
        return rename_plan

    def execute_rename(self, rename_plan: List[Tuple[Path, Path]]) -> Tuple[int, str]:
        """Provede přejmenování souborů a vytvoří záložní log."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"rename_backup_{timestamp}.json"
        self.log_file = self.raw_folder_path / log_filename
        
        backup_data = {
            'timestamp': datetime.now().isoformat(),
            'raw_folder': str(self.raw_folder_path),
            'jpg_folder': str(self.jpg_folder_path),
            'operations': []
        }
        
        successful_renames = 0
        
        for old_path, new_path in rename_plan:
            try:
                old_path.rename(new_path)
                operation = {
                    'old_name': old_path.name,
                    'new_name': new_path.name,
                    'old_path': str(old_path),
                    'new_path': str(new_path),
                    'status': 'success'
                }
                backup_data['operations'].append(operation)
                successful_renames += 1
            except Exception as e:
                operation = {
                    'old_name': old_path.name,
                    'new_name': new_path.name,
                    'old_path': str(old_path),
                    'new_path': str(new_path),
                    'status': 'error',
                    'error': str(e)
                }
                backup_data['operations'].append(operation)

        # Uložení záložního logu
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False)

        return successful_renames, str(self.log_file)


class ImageComparisonWindow:
    """Okno pro porovnání obrázků s možností procházení"""
    
    def __init__(self, parent, pairs_data, initial_index=0):
        self.parent = parent
        self.pairs_data = pairs_data  # Seznam (raw_path, jpg_path, similarity, new_name)
        self.current_index = initial_index
        
        self.window = tk.Toplevel(parent)
        self.window.title("Porovnání obrázků")
        self.window.geometry("1000x700")
        self.window.focus_set()
        
        # Binding pro klávesy
        self.window.bind('<Left>', self.prev_image)
        self.window.bind('<Right>', self.next_image)
        self.window.bind('<Escape>', self.close_window)
        
        self.create_widgets()
        self.update_display()
    
    def create_widgets(self):
        # Hlavní frame
        main_frame = ttk.Frame(self.window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Info panel
        self.info_frame = ttk.LabelFrame(main_frame, text="Informace o páru", padding="10")
        self.info_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Navigační tlačítka
        nav_frame = ttk.Frame(main_frame)
        nav_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.prev_btn = ttk.Button(nav_frame, text="◀ Předchozí (←)", command=self.prev_image)
        self.prev_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.position_label = ttk.Label(nav_frame, text="")
        self.position_label.pack(side=tk.LEFT, expand=True)
        
        self.next_btn = ttk.Button(nav_frame, text="Následující (→) ▶", command=self.next_image)
        self.next_btn.pack(side=tk.RIGHT, padx=(10, 0))
        
        # Frame pro obrázky
        self.images_frame = ttk.Frame(main_frame)
        self.images_frame.pack(fill=tk.BOTH, expand=True)
        
        # RAW frame
        self.raw_frame = ttk.LabelFrame(self.images_frame, text="RAW soubor", padding="5")
        self.raw_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # JPG frame
        self.jpg_frame = ttk.LabelFrame(self.images_frame, text="JPG soubor", padding="5")
        self.jpg_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
    
    def update_display(self):
        """Aktualizuje zobrazení pro aktuální index"""
        if not self.pairs_data or self.current_index >= len(self.pairs_data):
            return
        
        raw_path, jpg_path, similarity, new_name = self.pairs_data[self.current_index]
        
        # Aktualizace pozice
        self.position_label.config(text=f"{self.current_index + 1} / {len(self.pairs_data)}")
        
        # Aktualizace tlačítek
        self.prev_btn.config(state=tk.NORMAL if self.current_index > 0 else tk.DISABLED)
        self.next_btn.config(state=tk.NORMAL if self.current_index < len(self.pairs_data) - 1 else tk.DISABLED)
        
        # Vymazání starých informací
        for widget in self.info_frame.winfo_children():
            widget.destroy()
        
        # Zobrazení informací
        info_text = f"""RAW soubor: {raw_path.name}
JPG soubor: {jpg_path.name}
Podobnost: {similarity}
Nový název: {new_name}
RAW velikost: {self.get_file_size(raw_path)}
JPG velikost: {self.get_file_size(jpg_path)}"""
        
        ttk.Label(self.info_frame, text=info_text, justify=tk.LEFT).pack(anchor=tk.W)
        
        # Aktualizace názvů framů
        self.raw_frame.config(text=f"RAW: {raw_path.name}")
        self.jpg_frame.config(text=f"JPG: {jpg_path.name}")
        
        # Vymazání starých obrázků
        for widget in self.raw_frame.winfo_children():
            widget.destroy()
        for widget in self.jpg_frame.winfo_children():
            widget.destroy()
        
        # Načtení a zobrazení RAW obrázku
        try:
            with Image.open(raw_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.thumbnail((450, 450), Image.Resampling.LANCZOS)
                raw_photo = ImageTk.PhotoImage(img)
                raw_label = ttk.Label(self.raw_frame, image=raw_photo)
                raw_label.image = raw_photo  # Udržení reference
                raw_label.pack(expand=True)
                
                # Informace o rozlišení
                original_size = Image.open(raw_path).size
                ttk.Label(self.raw_frame, text=f"Rozlišení: {original_size[0]} × {original_size[1]}").pack()
        except Exception as e:
            ttk.Label(self.raw_frame, text=f"Chyba načítání: {e}").pack()
        
        # Načtení a zobrazení JPG obrázku
        try:
            with Image.open(jpg_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.thumbnail((450, 450), Image.Resampling.LANCZOS)
                jpg_photo = ImageTk.PhotoImage(img)
                jpg_label = ttk.Label(self.jpg_frame, image=jpg_photo)
                jpg_label.image = jpg_photo  # Udržení reference
                jpg_label.pack(expand=True)
                
                # Informace o rozlišení
                original_size = Image.open(jpg_path).size
                ttk.Label(self.jpg_frame, text=f"Rozlišení: {original_size[0]} × {original_size[1]}").pack()
        except Exception as e:
            ttk.Label(self.jpg_frame, text=f"Chyba načítání: {e}").pack()
    
    def get_file_size(self, file_path):
        """Vrátí velikost souboru v čitelném formátu"""
        try:
            size = file_path.stat().st_size
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024.0:
                    return f"{size:.1f} {unit}"
                size /= 1024.0
            return f"{size:.1f} TB"
        except:
            return "N/A"
    
    def prev_image(self, event=None):
        """Přejde na předchozí obrázek"""
        if self.current_index > 0:
            self.current_index -= 1
            self.update_display()
    
    def next_image(self, event=None):
        """Přejde na následující obrázek"""
        if self.current_index < len(self.pairs_data) - 1:
            self.current_index += 1
            self.update_display()
    
    def close_window(self, event=None):
        """Zavře okno"""
        self.window.destroy()


class FileRenamerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("RAW File Renamer - Přejmenování RAW souborů")
        self.root.geometry("1400x900")  # Zvětšeno kvůli náhledům

        # Proměnné
        self.raw_folder_path = tk.StringVar()
        self.jpg_folder_path = tk.StringVar()
        self.similarity_threshold = tk.IntVar(value=DEFAULT_SIMILARITY_THRESHOLD)
        self.preview_height = tk.IntVar(value=150)  # Výška preview oblasti
        
        self.renamer_core = None
        self.rename_plan = []
        self.pairs = []
        self.thumbnails = {}  # Cache pro náhledy
        self.column_thumbnails = {}  # Cache pro náhledy ve sloupcích
        self.pairs_data = []  # Data pro detail window

        # Načtení konfigurace
        self.load_config()
        self.create_widgets()

    def load_config(self):
        """Načte uloženou konfiguraci"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                self.jpg_folder_path.set(config.get('jpg_folder_path', ''))
                self.raw_folder_path.set(config.get('raw_folder_path', ''))
                self.similarity_threshold.set(config.get('similarity_threshold', DEFAULT_SIMILARITY_THRESHOLD))
        except Exception:
            pass  # Ignorujeme chyby při načítání konfigurace

    def save_config(self):
        """Uloží aktuální konfiguraci"""
        try:
            config = {
                'jpg_folder_path': self.jpg_folder_path.get(),
                'raw_folder_path': self.raw_folder_path.get(),
                'similarity_threshold': self.similarity_threshold.get()
            }
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass  # Ignorujeme chyby při ukládání konfigurace

    def create_thumbnail(self, image_path: Path, size=(60, 45)) -> Optional[ImageTk.PhotoImage]:
        """Vytvoří náhled obrázku"""
        try:
            # Kontrola cache
            cache_key = f"{image_path}_{size}"
            if cache_key in self.thumbnails:
                return self.thumbnails[cache_key]

            with Image.open(image_path) as img:
                # Konverze do RGB pokud je potřeba
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Vytvoření náhledu se zachováním poměru stran
                img.thumbnail(size, Image.Resampling.LANCZOS)
                
                # Vytvoření PhotoImage
                photo = ImageTk.PhotoImage(img)
                
                # Uložení do cache
                self.thumbnails[cache_key] = photo
                return photo
        except Exception as e:
            print(f"Chyba při vytváření náhledu pro {image_path}: {e}")
            return None

    def create_column_thumbnail(self, image_path: Path) -> Optional[ImageTk.PhotoImage]:
        """Vytvoří malý náhled pro sloupec treeview"""
        try:
            cache_key = f"col_{image_path}"
            if cache_key in self.column_thumbnails:
                return self.column_thumbnails[cache_key]

            with Image.open(image_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Malý náhled pro sloupec
                img.thumbnail((40, 30), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                
                self.column_thumbnails[cache_key] = photo
                return photo
        except Exception as e:
            print(f"Chyba při vytváření náhledu pro sloupec {image_path}: {e}")
            return None

    def create_widgets(self):
        # Hlavní frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Konfigurace grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        # Výběr RAW složky
        ttk.Label(main_frame, text="Složka s RAW soubory:").grid(row=0, column=0, sticky=tk.W, pady=5)
        raw_folder_frame = ttk.Frame(main_frame)
        raw_folder_frame.grid(row=0, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        raw_folder_frame.columnconfigure(0, weight=1)

        self.raw_folder_entry = ttk.Entry(raw_folder_frame, textvariable=self.raw_folder_path, width=50)
        self.raw_folder_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        ttk.Button(raw_folder_frame, text="Procházet...", command=self.browse_raw_folder).grid(row=0, column=1)

        # Výběr JPG složky
        ttk.Label(main_frame, text="Složka s JPG soubory:").grid(row=1, column=0, sticky=tk.W, pady=5)
        jpg_folder_frame = ttk.Frame(main_frame)
        jpg_folder_frame.grid(row=1, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        jpg_folder_frame.columnconfigure(0, weight=1)

        self.jpg_folder_entry = ttk.Entry(jpg_folder_frame, textvariable=self.jpg_folder_path, width=50)
        self.jpg_folder_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        ttk.Button(jpg_folder_frame, text="Procházet...", command=self.browse_jpg_folder).grid(row=0, column=1)

        # Nastavení podobnosti
        ttk.Label(main_frame, text="Práh podobnosti:").grid(row=2, column=0, sticky=tk.W, pady=5)
        similarity_frame = ttk.Frame(main_frame)
        similarity_frame.grid(row=2, column=1, sticky=tk.W, pady=5)

        ttk.Scale(similarity_frame, from_=1, to=20, variable=self.similarity_threshold, 
                 orient=tk.HORIZONTAL, length=200).grid(row=0, column=0, padx=(0, 10))
        self.similarity_label = ttk.Label(similarity_frame, text=str(self.similarity_threshold.get()))
        self.similarity_label.grid(row=0, column=1)
        self.similarity_threshold.trace('w', self.update_similarity_label)

        # Tlačítka
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=3, pady=20)

        self.scan_button = ttk.Button(button_frame, text="Skenovat soubory", command=self.scan_files)
        self.scan_button.grid(row=0, column=0, padx=5)

        self.find_pairs_button = ttk.Button(button_frame, text="Najít páry", command=self.find_pairs, state=tk.DISABLED)
        self.find_pairs_button.grid(row=0, column=1, padx=5)

        self.rename_button = ttk.Button(button_frame, text="Přejmenovat", command=self.rename_files, state=tk.DISABLED)
        self.rename_button.grid(row=0, column=2, padx=5)

        self.restore_button = ttk.Button(button_frame, text="Obnovit ze zálohy", command=self.restore_backup)
        self.restore_button.grid(row=0, column=3, padx=5)

        # Progress bar
        self.progress = ttk.Progressbar(main_frame, mode='determinate')
        self.progress.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)

        self.status_label = ttk.Label(main_frame, text="Připraven")
        self.status_label.grid(row=5, column=0, columnspan=3, pady=5)

        # Výsledky s náhledy
        results_frame = ttk.LabelFrame(main_frame, text="Výsledky", padding="5")
        results_frame.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(6, weight=1)

        # Treeview pro zobrazení párů s náhledy
        columns = ('RAW náhled', 'RAW soubor', 'JPG náhled', 'JPG soubor', 'Podobnost', 'Nový název')
        self.tree = ttk.Treeview(results_frame, columns=columns, show='headings', height=12)

        # Nastavení sloupců
        self.tree.heading('RAW náhled', text='RAW')
        self.tree.heading('RAW soubor', text='RAW soubor')
        self.tree.heading('JPG náhled', text='JPG')
        self.tree.heading('JPG soubor', text='JPG soubor')
        self.tree.heading('Podobnost', text='Podobnost')
        self.tree.heading('Nový název', text='Nový název')

        # Nastavení šířek sloupců
        self.tree.column('RAW náhled', width=50, minwidth=50)
        self.tree.column('RAW soubor', width=180)
        self.tree.column('JPG náhled', width=50, minwidth=50)
        self.tree.column('JPG soubor', width=180)
        self.tree.column('Podobnost', width=80)
        self.tree.column('Nový název', width=180)

        # Nastavení výšky řádků pro náhledy
        style = ttk.Style()
        style.configure("Treeview", rowheight=35)  # Výška řádku pro malé náhledy

        # Scrollbary
        v_scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(results_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        v_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        h_scrollbar.grid(row=1, column=0, sticky=(tk.W, tk.E))

        # Binding pro zobrazení detailů při kliknutí
        self.tree.bind('<Double-1>', self.show_image_details)

        # Frame pro náhledy pod tabulkou s posuvníkem výšky
        preview_container = ttk.Frame(main_frame)
        preview_container.grid(row=7, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(10, 0))
        preview_container.columnconfigure(0, weight=1)

        # Posuvník pro výšku preview
        height_control_frame = ttk.Frame(preview_container)
        height_control_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        ttk.Label(height_control_frame, text="Výška náhledu:").pack(side=tk.LEFT)
        height_scale = ttk.Scale(height_control_frame, from_=100, to=400, 
                               variable=self.preview_height, orient=tk.HORIZONTAL, 
                               length=200, command=self.update_preview_height)
        height_scale.pack(side=tk.LEFT, padx=(10, 10))
        
        self.height_label = ttk.Label(height_control_frame, text=f"{self.preview_height.get()}px")
        self.height_label.pack(side=tk.LEFT)

        # Frame pro náhledy
        self.preview_frame = ttk.LabelFrame(preview_container, text="Náhled vybraného páru (dvojklik pro detail s navigací)", padding="5")
        self.preview_frame.grid(row=1, column=0, sticky=(tk.W, tk.E))
        self.preview_frame.configure(height=self.preview_height.get())

        # Binding pro výběr řádku
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)

    def update_preview_height(self, value):
        """Aktualizuje výšku preview oblasti"""
        height = int(float(value))
        self.height_label.config(text=f"{height}px")
        self.preview_frame.configure(height=height)
        
        # Aktualizace náhledů pokud jsou zobrazeny
        selection = self.tree.selection()
        if selection:
            self.on_tree_select(None)

    def on_tree_select(self, event):
        """Zobrazí náhledy vybraného páru"""
        selection = self.tree.selection()
        if not selection:
            # Vymazání náhledů
            for widget in self.preview_frame.winfo_children():
                widget.destroy()
            return

        item = self.tree.item(selection[0])
        values = item['values']
        if len(values) >= 4:
            raw_name = values[1]
            jpg_name = values[3]

            # Najdeme cesty k souborům
            raw_path = None
            jpg_path = None
            for raw_file, jpg_file, similarity in self.pairs:
                if raw_file.name == raw_name and jpg_file.name == jpg_name:
                    raw_path = raw_file
                    jpg_path = jpg_file
                    break

            if raw_path and jpg_path:
                self.show_preview_thumbnails(raw_path, jpg_path)

    def show_preview_thumbnails(self, raw_path: Path, jpg_path: Path):
        """Zobrazí náhledy v preview frame"""
        # Vymazání starých náhledů
        for widget in self.preview_frame.winfo_children():
            widget.destroy()

        # Výpočet velikosti náhledů podle výšky preview
        preview_height = self.preview_height.get()
        thumbnail_height = int(preview_height * 0.7)  # 70% výšky pro obrázek
        thumbnail_size = (int(thumbnail_height * 1.5), thumbnail_height)  # Poměr 3:2

        # RAW náhled
        raw_frame = ttk.Frame(self.preview_frame)
        raw_frame.pack(side=tk.LEFT, padx=10, fill=tk.BOTH, expand=True)
        
        ttk.Label(raw_frame, text=f"RAW: {raw_path.name}").pack()
        raw_thumbnail = self.create_thumbnail(raw_path, thumbnail_size)
        if raw_thumbnail:
            raw_label = ttk.Label(raw_frame, image=raw_thumbnail)
            raw_label.image = raw_thumbnail  # Udržení reference
            raw_label.pack()
        else:
            ttk.Label(raw_frame, text="Náhled nedostupný").pack()

        # JPG náhled
        jpg_frame = ttk.Frame(self.preview_frame)
        jpg_frame.pack(side=tk.LEFT, padx=10, fill=tk.BOTH, expand=True)
        
        ttk.Label(jpg_frame, text=f"JPG: {jpg_path.name}").pack()
        jpg_thumbnail = self.create_thumbnail(jpg_path, thumbnail_size)
        if jpg_thumbnail:
            jpg_label = ttk.Label(jpg_frame, image=jpg_thumbnail)
            jpg_label.image = jpg_thumbnail  # Udržení reference
            jpg_label.pack()
        else:
            ttk.Label(jpg_frame, text="Náhled nedostupný").pack()

    def show_image_details(self, event):
        """Zobrazí detail obrázků při dvojkliku s možností navigace"""
        selection = self.tree.selection()
        if not selection:
            return

        # Najdeme index vybraného řádku
        selected_item = selection[0]
        all_items = self.tree.get_children()
        current_index = list(all_items).index(selected_item)

        # Otevřeme detail window s navigací
        ImageComparisonWindow(self.root, self.pairs_data, current_index)

    def update_similarity_label(self, *args):
        self.similarity_label.config(text=str(self.similarity_threshold.get()))

    def browse_raw_folder(self):
        folder = filedialog.askdirectory(title="Vyberte složku s RAW soubory")
        if folder:
            self.raw_folder_path.set(folder)
            self.save_config()

    def browse_jpg_folder(self):
        folder = filedialog.askdirectory(title="Vyberte složku s JPG soubory")
        if folder:
            self.jpg_folder_path.set(folder)
            self.save_config()

    def scan_files(self):
        if not self.raw_folder_path.get():
            messagebox.showerror("Chyba", "Vyberte prosím složku s RAW soubory.")
            return

        if not self.jpg_folder_path.get():
            messagebox.showerror("Chyba", "Vyberte prosím složku s JPG soubory.")
            return

        try:
            self.renamer_core = FileRenamerCore(
                self.raw_folder_path.get(),
                self.jpg_folder_path.get(),
                self.similarity_threshold.get()
            )

            raw_count, jpg_count = self.renamer_core.scan_files()
            self.status_label.config(text=f"Nalezeno {raw_count} RAW souborů a {jpg_count} JPG souborů")

            if raw_count > 0 and jpg_count > 0:
                self.find_pairs_button.config(state=tk.NORMAL)
            else:
                messagebox.showwarning("Upozornění", "Ve složkách nebyly nalezeny RAW nebo JPG soubory.")

        except Exception as e:
            messagebox.showerror("Chyba", f"Chyba při skenování souborů: {e}")

    def find_pairs(self):
        if not self.renamer_core:
            return

        def progress_callback(current, total, message):
            progress_percent = (current / total) * 100
            self.progress['value'] = progress_percent
            self.status_label.config(text=message)
            self.root.update_idletasks()

        def find_pairs_thread():
            try:
                self.pairs = self.renamer_core.find_pairs(progress_callback)
                self.rename_plan = self.renamer_core.generate_rename_plan()

                # Aktualizace GUI v hlavním vlákně
                self.root.after(0, self.update_pairs_display)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Chyba", f"Chyba při hledání párů: {e}"))
            finally:
                self.root.after(0, lambda: self.progress.config(value=0))

        # Spuštění v samostatném vlákně
        threading.Thread(target=find_pairs_thread, daemon=True).start()

    def update_pairs_display(self):
        # Vymazání starých dat
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Vymazání cache náhledů
        self.thumbnails.clear()
        self.column_thumbnails.clear()

        # Vymazání preview
        for widget in self.preview_frame.winfo_children():
            widget.destroy()

        # Příprava dat pro detail window
        self.pairs_data = []

        # Přidání nových párů s náhledy
        for raw_file, new_path in self.rename_plan:
            # Najdeme odpovídající pár pro získání JPG souboru a podobnosti
            jpg_file = None
            similarity = None
            for r, j, s in self.pairs:
                if r == raw_file:
                    jpg_file = j
                    similarity = s
                    break

            if jpg_file:
                # Přidání do dat pro detail window
                self.pairs_data.append((raw_file, jpg_file, similarity, new_path.name))

                # Vytvoření náhledů pro sloupce
                raw_thumbnail = self.create_column_thumbnail(raw_file)
                jpg_thumbnail = self.create_column_thumbnail(jpg_file)

                # Označení existence náhledů
                raw_preview = "🖼️" if raw_thumbnail else "❌"
                jpg_preview = "🖼️" if jpg_thumbnail else "❌"

                # Vložení řádku
                self.tree.insert('', tk.END, values=(
                    raw_preview,
                    raw_file.name,
                    jpg_preview,
                    jpg_file.name,
                    similarity if similarity is not None else "N/A",
                    new_path.name
                ))

        self.status_label.config(text=f"Nalezeno {len(self.rename_plan)} párů k přejmenování (klik pro náhled, dvojklik pro detail s navigací)")

        if self.rename_plan:
            self.rename_button.config(state=tk.NORMAL)

    def rename_files(self):
        if not self.rename_plan:
            return

        # Potvrzení od uživatele
        result = messagebox.askyesno(
            "Potvrzení",
            f"Opravdu chcete přejmenovat {len(self.rename_plan)} souborů?\n\n"
            "Bude vytvořen záložní log pro možnost obnovy."
        )

        if not result:
            return

        try:
            successful, log_file = self.renamer_core.execute_rename(self.rename_plan)
            messagebox.showinfo(
                "Dokončeno",
                f"Přejmenování dokončeno!\n\n"
                f"Úspěšně přejmenováno: {successful}/{len(self.rename_plan)} souborů\n"
                f"Záložní log: {log_file}"
            )

            # Reset GUI
            self.reset_gui()

        except Exception as e:
            messagebox.showerror("Chyba", f"Chyba při přejmenování: {e}")

    def restore_backup(self):
        backup_file = filedialog.askopenfilename(
            title="Vyberte záložní soubor",
            filetypes=[("JSON soubory", "*.json"), ("Všechny soubory", "*.*")]
        )

        if not backup_file:
            return

        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)

            restored = 0
            errors = []

            for operation in backup_data['operations']:
                if operation['status'] == 'success':
                    old_path = Path(operation['old_path'])
                    new_path = Path(operation['new_path'])

                    if new_path.exists():
                        try:
                            new_path.rename(old_path)
                            restored += 1
                        except Exception as e:
                            errors.append(f"{new_path.name}: {e}")

            message = f"Obnoveno {restored} souborů"
            if errors:
                message += f"\n\nChyby:\n" + "\n".join(errors[:5])
                if len(errors) > 5:
                    message += f"\n... a dalších {len(errors)-5} chyb"

            messagebox.showinfo("Obnova dokončena", message)

        except Exception as e:
            messagebox.showerror("Chyba", f"Chyba při obnově ze zálohy: {e}")

    def reset_gui(self):
        """Reset GUI do výchozího stavu"""
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Vymazání preview
        for widget in self.preview_frame.winfo_children():
            widget.destroy()

        self.find_pairs_button.config(state=tk.DISABLED)
        self.rename_button.config(state=tk.DISABLED)
        self.status_label.config(text="Připraven")
        self.progress['value'] = 0
        self.renamer_core = None
        self.rename_plan = []
        self.pairs = []
        self.pairs_data = []
        self.thumbnails.clear()
        self.column_thumbnails.clear()


def main():
    root = tk.Tk()
    app = FileRenamerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
