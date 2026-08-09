"""Ein modernes Erscheinungsbild für ttk - ohne zusätzliche Bibliotheken.

Absichtlich keine Fremdpakete (ttkbootstrap, customtkinter): die App soll
sich als eine einzelne, kleine EXE ausliefern lassen und beim Start nicht
an einer fehlenden Abhängigkeit scheitern. Das Standard-Theme "clam"
lässt sich weit genug umgestalten, um flach und aufgeräumt zu wirken.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Dict

LIGHT: Dict[str, str] = {
    "bg": "#F4F6F9",
    "surface": "#FFFFFF",
    "surface_alt": "#EEF1F6",
    "border": "#D8DEE7",
    "text": "#1B2130",
    "muted": "#69748A",
    "accent": "#2D6CDF",
    "accent_hover": "#2559BC",
    "accent_text": "#FFFFFF",
    "success": "#15803D",
    "warning": "#B45309",
    "danger": "#B42318",
    "selection": "#DCE8FC",
    "log_bg": "#1B2130",
    "log_text": "#D7DEEA",
}

DARK: Dict[str, str] = {
    "bg": "#141821",
    "surface": "#1C2130",
    "surface_alt": "#232838",
    "border": "#333A4D",
    "text": "#E8ECF4",
    "muted": "#98A2B8",
    "accent": "#4C8DFF",
    "accent_hover": "#3B78E0",
    "accent_text": "#FFFFFF",
    "success": "#3DD07A",
    "warning": "#F0A03C",
    "danger": "#F97066",
    "selection": "#2A3550",
    "log_bg": "#0F131C",
    "log_text": "#C7D0E0",
}


def base_family() -> str:
    if sys.platform == "win32":
        return "Segoe UI"
    if sys.platform == "darwin":
        return "SF Pro Text"
    return "DejaVu Sans"


class Theme:
    """Hält die Farbpalette und richtet alle ttk-Stile ein."""

    def __init__(self, root: tk.Misc, dark: bool = False) -> None:
        self.root = root
        self.dark = dark
        self.colors: Dict[str, str] = dict(DARK if dark else LIGHT)
        self.style = ttk.Style(root)
        self._setup_fonts()
        self.apply()

    # -- Schriften ---------------------------------------------------------
    def _setup_fonts(self) -> None:
        family = base_family()
        self.font_body = tkfont.Font(family=family, size=10)
        self.font_small = tkfont.Font(family=family, size=9)
        self.font_bold = tkfont.Font(family=family, size=10, weight="bold")
        self.font_title = tkfont.Font(family=family, size=15, weight="bold")
        self.font_heading = tkfont.Font(family=family, size=11, weight="bold")
        self.font_mono = tkfont.Font(
            family="Consolas" if sys.platform == "win32" else "monospace", size=9)

        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            try:
                tkfont.nametofont(name).configure(family=family, size=10)
            except tk.TclError:
                pass

    def color(self, key: str) -> str:
        return self.colors.get(key, "#000000")

    # -- Stile -------------------------------------------------------------
    def apply(self) -> None:
        c = self.colors
        st = self.style
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass

        self.root.configure(bg=c["bg"])

        st.configure(".", background=c["bg"], foreground=c["text"],
                     font=self.font_body, borderwidth=0, focuscolor=c["accent"])

        # Flächen
        st.configure("TFrame", background=c["bg"])
        st.configure("Surface.TFrame", background=c["surface"])
        st.configure("Card.TFrame", background=c["surface"], relief="flat")
        st.configure("Alt.TFrame", background=c["surface_alt"])
        st.configure("Separator.TFrame", background=c["border"])

        # Beschriftungen
        st.configure("TLabel", background=c["bg"], foreground=c["text"])
        st.configure("Surface.TLabel", background=c["surface"], foreground=c["text"])
        st.configure("Title.TLabel", background=c["bg"], foreground=c["text"],
                     font=self.font_title)
        st.configure("Heading.TLabel", background=c["surface"], foreground=c["text"],
                     font=self.font_heading)
        st.configure("Muted.TLabel", background=c["surface"], foreground=c["muted"],
                     font=self.font_small)
        st.configure("MutedBg.TLabel", background=c["bg"], foreground=c["muted"],
                     font=self.font_small)
        st.configure("Success.TLabel", background=c["surface"], foreground=c["success"],
                     font=self.font_bold)
        st.configure("Warning.TLabel", background=c["surface"], foreground=c["warning"])
        st.configure("Danger.TLabel", background=c["surface"], foreground=c["danger"],
                     font=self.font_bold)
        st.configure("Mono.TLabel", background=c["surface"], foreground=c["text"],
                     font=self.font_mono)

        # Schaltflächen
        st.configure("TButton", background=c["surface_alt"], foreground=c["text"],
                     borderwidth=1, relief="flat", padding=(14, 7))
        st.map("TButton",
               background=[("pressed", c["border"]), ("active", c["border"]),
                           ("disabled", c["surface_alt"])],
               foreground=[("disabled", c["muted"])],
               bordercolor=[("!disabled", c["border"])])

        st.configure("Accent.TButton", background=c["accent"],
                     foreground=c["accent_text"], borderwidth=0, padding=(16, 8),
                     font=self.font_bold)
        st.map("Accent.TButton",
               background=[("pressed", c["accent_hover"]), ("active", c["accent_hover"]),
                           ("disabled", c["border"])],
               foreground=[("disabled", c["muted"])])

        st.configure("Big.TButton", background=c["accent"], foreground=c["accent_text"],
                     borderwidth=0, padding=(24, 14), font=self.font_heading)
        st.map("Big.TButton",
               background=[("pressed", c["accent_hover"]), ("active", c["accent_hover"]),
                           ("disabled", c["border"])],
               foreground=[("disabled", c["muted"])])

        st.configure("Link.TButton", background=c["surface"], foreground=c["accent"],
                     borderwidth=0, padding=(4, 2), font=self.font_small)
        st.map("Link.TButton", background=[("active", c["surface"])],
               foreground=[("active", c["accent_hover"])])

        st.configure("Small.TButton", background=c["surface_alt"], foreground=c["text"],
                     borderwidth=1, padding=(8, 4), font=self.font_small)
        st.map("Small.TButton", background=[("active", c["border"])])

        # Eingabefelder
        st.configure("TEntry", fieldbackground=c["surface"], foreground=c["text"],
                     bordercolor=c["border"], lightcolor=c["border"],
                     darkcolor=c["border"], insertcolor=c["text"], padding=6)
        st.map("TEntry", bordercolor=[("focus", c["accent"])])

        # Bei "readonly" markiert ttk den Inhalt wie eine Textauswahl. Ohne die
        # folgenden Zuordnungen steht der Text dann weiss auf weiss, sobald das
        # Feld den Fokus hat - der Wert scheint dann zu fehlen.
        st.configure("TCombobox", fieldbackground=c["surface"], background=c["surface"],
                     foreground=c["text"], bordercolor=c["border"],
                     lightcolor=c["border"], darkcolor=c["border"],
                     arrowcolor=c["muted"], padding=5,
                     selectbackground=c["surface"], selectforeground=c["text"])
        st.map("TCombobox",
               fieldbackground=[("readonly", c["surface"]),
                                ("disabled", c["surface_alt"])],
               foreground=[("readonly", c["text"]), ("focus", c["text"]),
                           ("disabled", c["muted"])],
               bordercolor=[("focus", c["accent"])],
               selectbackground=[("readonly", c["surface"]),
                                 ("focus", c["surface"]),
                                 ("!focus", c["surface"])],
               selectforeground=[("readonly", c["text"]),
                                 ("focus", c["text"]),
                                 ("!focus", c["text"])])

        # Die aufklappende Liste ist ein klassisches Tk-Listenfeld und wird
        # nicht über ttk-Stile erreicht.
        self.root.option_add("*TCombobox*Listbox.background", c["surface"])
        self.root.option_add("*TCombobox*Listbox.foreground", c["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", c["accent"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", c["accent_text"])
        self.root.option_add("*TCombobox*Listbox.font", self.font_body)

        st.configure("TCheckbutton", background=c["surface"], foreground=c["text"],
                     indicatorcolor=c["surface"], focuscolor=c["surface"])
        st.map("TCheckbutton",
               background=[("active", c["surface"])],
               indicatorcolor=[("selected", c["accent"])])

        st.configure("Bg.TCheckbutton", background=c["bg"], foreground=c["text"])
        st.map("Bg.TCheckbutton", background=[("active", c["bg"])])

        st.configure("TRadiobutton", background=c["surface"], foreground=c["text"])
        st.map("TRadiobutton", background=[("active", c["surface"])],
               indicatorcolor=[("selected", c["accent"])])

        # Register
        st.configure("TNotebook", background=c["bg"], borderwidth=0, tabmargins=(0, 6, 0, 0))
        st.configure("TNotebook.Tab", background=c["bg"], foreground=c["muted"],
                     padding=(20, 11), borderwidth=0, font=self.font_body)
        st.map("TNotebook.Tab",
               background=[("selected", c["surface"])],
               foreground=[("selected", c["accent"]), ("active", c["text"])],
               font=[("selected", self.font_bold)])

        # Fortschritt
        st.configure("TProgressbar", background=c["accent"], troughcolor=c["surface_alt"],
                     bordercolor=c["surface_alt"], lightcolor=c["accent"],
                     darkcolor=c["accent"], thickness=8)
        st.configure("Success.Horizontal.TProgressbar", background=c["success"],
                     troughcolor=c["surface_alt"], bordercolor=c["surface_alt"],
                     lightcolor=c["success"], darkcolor=c["success"], thickness=8)

        # Tabellen
        st.configure("Treeview", background=c["surface"], fieldbackground=c["surface"],
                     foreground=c["text"], borderwidth=0, rowheight=28)
        st.configure("Treeview.Heading", background=c["surface_alt"],
                     foreground=c["muted"], relief="flat", padding=(8, 6),
                     font=self.font_small)
        st.map("Treeview.Heading", background=[("active", c["border"])])
        st.map("Treeview",
               background=[("selected", c["selection"])],
               foreground=[("selected", c["text"])])

        # Bildlaufleisten
        st.configure("Vertical.TScrollbar", background=c["surface_alt"],
                     troughcolor=c["bg"], bordercolor=c["bg"],
                     arrowcolor=c["muted"], width=12)
        st.map("Vertical.TScrollbar", background=[("active", c["border"])])
        st.configure("Horizontal.TScrollbar", background=c["surface_alt"],
                     troughcolor=c["bg"], bordercolor=c["bg"],
                     arrowcolor=c["muted"])

        st.configure("TLabelframe", background=c["surface"], foreground=c["muted"],
                     bordercolor=c["border"], borderwidth=1, relief="solid")
        st.configure("TLabelframe.Label", background=c["surface"],
                     foreground=c["muted"], font=self.font_small)

        st.configure("TSeparator", background=c["border"])
