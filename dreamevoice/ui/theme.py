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

# Ruhigere, leicht kühle Neutrale statt des früheren Blaustichs, dazu ein
# gedecktes Petrol als Akzent. Ein knalliges Blau wirkt bei einem Werkzeug,
# das auf ein Gerät schreibt, unnötig laut; Petrol bleibt freundlich, ohne
# sich vorzudrängen. Der Akzent kommt nur an wenigen Stellen vor - auf dem
# Hauptknopf, am aktiven Eintrag der Leiste, im Fokusrahmen.
LIGHT: Dict[str, str] = {
    "bg": "#F2F4F5",
    "surface": "#FFFFFF",
    "surface_alt": "#EAEEEF",
    "border": "#DCE2E4",
    "text": "#12191C",
    "muted": "#5D6C72",
    "accent": "#1F6F7A",
    "accent_hover": "#175860",
    "accent_text": "#FFFFFF",
    "success": "#1B7A4B",
    "warning": "#A2610C",
    "danger": "#B0342A",
    "selection": "#DCE9EB",
    # Das Protokoll ist im hellen Design hell. Früher war es fast
    # schwarz - darauf waren die dunklen Erfolgs- und Warnfarben kaum zu
    # lesen, und ein leeres Terminalfenster ist ohnehin der schwerste
    # Klotz auf der Seite.
    "log_bg": "#F7F9F9",
    "log_text": "#26343A",
    # Knopfflächen. Hell: etwas dunkler als das weiße Blatt, damit
    # sie sich abheben. Der Rand ist deutlich genug, um den Knopf auch
    # ohne Farbe als Knopf zu lesen.
    "button": "#E7ECEE",
    "button_hover": "#D6DEE1",
    # 3,75:1 gegen das weiße Blatt und 3,15:1 gegen die Knopffläche -
    # die Norm verlangt 3:1 für den Umriss eines Bedienelements.
    "button_border": "#78868D",
}

DARK: Dict[str, str] = {
    "bg": "#101416",
    "surface": "#191F22",
    "surface_alt": "#141A1C",
    "border": "#2A3337",
    "text": "#E4EAEC",
    "muted": "#8D9BA1",
    "accent": "#59B6C2",
    "accent_hover": "#7ACAD4",
    "accent_text": "#0B1416",
    "success": "#4FBF85",
    "warning": "#DFA44B",
    "danger": "#E8736A",
    "selection": "#1E2C30",
    "log_bg": "#0B0F11",
    "log_text": "#BFCCD0",
    # Dunkel: HELLER als die Karte (#191F22), nicht dunkler. Vorher
    # stand hier surface_alt (#141A1C) - der Knopf lag damit unter
    # seiner eigenen Karte und war kaum als Knopf zu erkennen.
    "button": "#2E393E",
    "button_hover": "#3C4A50",
    # 3,97:1 gegen die Karte. Mit dem alten #4A5A61 waren es 2,32:1 -
    # unter der Norm von 3:1, und man sah den Umriss kaum.
    "button_border": "#697F8A",
}


# Die Kästchen der Auswahlfelder als eingebettete Bilder.
#
# clam zeichnet dort ein festes Kreuz - "angehakt" sähe damit aus wie
# "durchgestrichen". Ein eigenes Bild löst das.
#
# Neu gezeichnet am 30.08.2026: Der Rand des leeren Kästchens war im
# dunklen Design #293135 auf einer Karte in #191F22 - Kontrast 1,26:1.
# Das ist kein Rand mehr, sondern eine Ahnung. Jetzt 3,59:1 im Dunkeln
# und 3,37:1 im Hellen, also über den 3:1, die die Norm für den
# Umriss eines Bedienelements verlangt. Angehakt wird außerdem
# gefüllt statt nur umrandet - so ist "an" auch aus dem Augenwinkel
# vom "aus" zu unterscheiden. Erzeugt wurden sie
# einmalig mit Pillow (vierfach gezeichnet und heruntergerechnet, daher
# die weichen Kanten); zur Laufzeit decodiert tkinter die PNG-Daten
# selbst, es kommt also keine Abhängigkeit hinzu.
HAKEN_PNG = {
    "LICHT_AUS":
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAABmUlEQVR42qVTu2rcUB"
        "A9M9JqV6wJignr0p+QMk3KfEsKmxQmjfESbmzHTpPFRSBFvsAf4MohZZr8QgjBrcBr"
        "IbNcSSvNSbG7kexgXOyBYWbuPcyLGaAD51yIR3CfI/cJe3uTeGp5P8syIFk+ZkCSJN"
        "jUJ+XZ2Vv/XwCSAkDejI/HydPkdRT2hrRGIMsEBEUDVvV8lt1kXz+fvDsBQBHhv5J2"
        "D47G5xeXTK+n9EXJoqzuiC9KptdTnl9ccvfgaNxtR3ac29g/naRZfluTrEnaA1Jn+W"
        "29fzpJd5zbACAKgFdp2hvGcT8eDAIASkJIykK3NgCNB4NgGMf9qzTtAWAIAGEU0czM"
        "yHY4IndGtfoyEmZmYRQRALTDEcHjkCV35SvWRBuA6DTwMLjkrvwQAOqqElVV7TRBsr"
        "Nnra0iUFWtq0pWFcj2aDSfeV/6omgAmMhiSRa6tQGYL4pm5n25PRrNAUjgnAs/HR4W"
        "z1+8jOaGV1vPNjXQQBozaZpW6rqRmzzXbz9+6q/ffz5++fD+u3MuXHuV1z4mrHvOfw"
        "H2JBuLAr83lwAAAABJRU5ErkJggg=="
    ,
    "LICHT_UEBER":
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAABr0lEQVR42qVTPWsUUR"
        "Q9585slp0NMgmsYhWw1MYf4V9IlSoWFoGwpM2CU4mNECy0sJA0Nukt8xPsg4IgQYgb"
        "2BkDOx+7896xmOy67iIp9sB53Mf94N3z7gUWkSQh7sJSDJcvOjrq4PuoDWQA4lvPrf"
        "1ou+LJSaGVAhIFsPu8P3iwHb+4197oei+S4sxtRt1Uk/GvUfZh/PHtKwICKSBJQgKI"
        "9g8He6dnurgaKs0LZUWp32XDrCiV5oUurobaOz1TtH844EI77O0ebO70j4eXaVZLqi"
        "X5/7C+TLN6p3887O0ebAKgAdB1nrW2ulE7jjqBB8x7UfqX3osesDjqBFvdqH2dZy0A"
        "ahQNW3Lee+c9DIAIkFySXyAA5z2c9x5hSwBgczUJriatgiTIv79nWBPzAhIk6c4ESZ"
        "AwD2w0qKcMzCwwg2/anR0LiY02gRkCM0M95ewF7EXxNB3nVZYXzgBvxmaKFmhGGeCz"
        "vHDpOK96UTwFwABJEhbv35STx083fpb1sycP71sYBKyc48Q5Vs6xrB3Lac0fo9Refj"
        "63L1+/vb759O58NoRrjfLay4R11/kPNwAg9JgBeogAAAAASUVORK5CYII="
    ,
    "LICHT_AN":
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACZ0lEQVR42qWTP4hUdx"
        "DHPzO/9+7t21331nCX6lA4USws0huCJoUgqYQUKYVE8KKCFgFJ8e6EBAwJcpEc5E8h"
        "KWJImSpdlIhIUoi1eCSH2BzK7nm7b9+9/c2kyF48TWHhVAMz35nvzJcv7IyiSHhZvN"
        "AjL9bnzp/PQ2dPRq/3fKHbJW6sVQ+vXCn/P8BdWFyUPf36E9FwSsxaZiYgkwXuquqo"
        "Dszit2vT6acsLjoirhRFgojv7dUXk3bnEu5zLrJbQ+hq0GkNOi0hdFV1tyJzSbtzaW"
        "+vvoiIUxSJADK7ULTytF7VEF7zOAZEwSfLQVXZKEe4m3XabSzGJ2Wdzq+vLA0SwHOv"
        "Ulwz3IOAIyI+wSdBeTwY8OGRN6nHUX/+866kKlnuVQq4AshU5oAJEN2J0RARkqD0hi"
        "WHD+zj8/dP8M6hg9QWUcEmGHZKItGdPE0RUTarirKK7Ht9hp/OfMC9tYd8dO1HspBg"
        "/kw93U6SIPTLEeeOvc2vH58lUaWZTfHD6ZMMqy3e++o7xtGYSgPb5z3HwNy908j4/r"
        "dbHH/jEL9cWKA3HDI/O8O7X35NbzCkkzeI5pPX7mDgW5WYuaYh8KjX59jlqzTShLcO"
        "7mfh2nVu319lupkztvgfzrcq2WYgpWR1LnVlENuNjI2y1BPL3zA/O8MfD/5idlebej"
        "wGwRABoSolq//VuyjC+srSpsCyNlshIqHVaEh/VMmd1b+lmTfERIQQBA1Bm60gsLy+"
        "srRJUYTAzZuGu/Tv/H5r19Myqup+M4tBqKZCqCxahdtIRUpUH1s1+mKtm37GjRtw9K"
        "i9spl4VTv/AxCTDfSUlBXgAAAAAElFTkSuQmCC"
    ,
    "DUNKEL_AUS":
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAABwElEQVR42qWTz2qTQR"
        "TFz5l8880XA2ki+IcuSugjuM0iIEJxU935Bi4kUrWLii4+KBSzKQoNLnwDwYW4c6E7"
        "tz5CCS6K/2pjIWYmsXNcpNEkVgrmB3czc+65l5l7gQnyPE9wCrMazgrubm8Xl5YvuW"
        "6nA1Qqo8NuF5VaDR9234fH6+v9vwwkkSTvtNoPh4Nw0//olQBSEEciCpCyM6WeTd2z"
        "J/ebWxolKWnkeULy51pr58H3/a+b716/QvAeNAaQjssQihEuy6r1ldXNtdZOJLnVyP"
        "OEAHir3S7Fz73dty+fn/3ycQ8uKxqNk8etkgi+H89dXMTl6ze+mfOl5afNZs8AULla"
        "s4MQXPC+4LKiIUljzFSQpMuKJnhfGITgytWaBSADAG4wFMlIGsxWnkQSSAOS0Q2GAg"
        "Dz+xIiIJyOMH7cKYP/xfz5T+qEsTgBHmsnDEJqKclIEeS/TUhCipBkQmo5NuDhQWeY"
        "Ohdclh0F34+SFGOcCkkKvh9dlh2lzoXDg84QAAuNPE9ebGz4+tVr6YXFpSv7n/YMQF"
        "rnaK2ltSlt6lgoJCxXqqa+smpKCwuP2vduvxkP0lyjPPcyYd51/gWA3esKl/LMHgAA"
        "AABJRU5ErkJggg=="
    ,
    "DUNKEL_UEBER":
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAB2ElEQVR42qVTv2uTUR"
        "Q9577vJWmSpzEOYu0gGaQolIKItCBfBP8F52wOHQoOXSo4BKqDm4ODuDjrvyCfYGkH"
        "FysIUiQoFDdL9KWa5Ov3rsPXpL+ggj1wlnfPvZd77rvAAcRJEuEfOKrhUcHdtbWJyb"
        "m5Ir52Dwcu1/B9fX3wan7+z7ECqkqSbL37+CDr9+71uz8rAKhQ5iIqAC3Vzu6YUvX5"
        "y1szK5onaRQnSURyt7W6sdz71ml/ePoEqfegMYDqXhtCswzWuXOzi0vt1upGILkSJ0"
        "lEqHLh7afK9u8fnfft5Xp38zOsOyOaZeDegKoAjUHqf4XalWncePhou14+33jWvLYj"
        "IFUbUzbt+WLqvSk4JxShWEtGOcVaUoQF5yT13qQ9X9TGlAWpAgCFoEoxgcZAQ9hve5"
        "AANATQGFBMKIT8UUZuKpTjmU+CKkbmHirwv5D9fVLHrp0EcrRWAEAEAEMhNWS58yJj"
        "4bFcEWiWQUMmQ8kFAlWys5XaqhtY57Kh90FD0JCmqrs5Q5qqhqBD74N1LrNVN2BnK4"
        "UqTdxsRq9v3+xfX7hfqE9fvdP9sikEaCsVRqWJnOUyjbWsTF6S2cUlKV+4+PhFPPMm"
        "bjajU3/lUx8TTnvOfwFBVPagzm2sYQAAAABJRU5ErkJggg=="
    ,
    "DUNKEL_AN":
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACRklEQVR42qWTO2uUUR"
        "CG33fm7Leb3agbI9EihQS8gihoZeFmQQsFS/0JNlp5Aa8kRMRCUtgo+BNcCyu1iO5n"
        "lFSClQgreEcjiAbdC7vfOWcsEmKiqIVTzo1nZt4BllilXnf4h/2aw18TDt2c6Stu6M"
        "vj9RxQXnDOAVhfRvtFp1s7vLvzWwMz4zjAxp3pc5okR2IIpRgjaTYfJ01ETFRbode7"
        "sfHAnkvjgJE0qdTrjqQ17j46UxxaNxFjHAY5oKplcW6VOLdKVctmNhC8Hy4OrZto3H"
        "10hqRV6nVHmPFQmpZcW15qkqwOvR4AyFJMM4PrK0KEMXqP0Ot98cU4UhsdbQlIyzmX"
        "MyBvMepCMUESJC1GJv0r+Pr+Pb6auiegqBnyOedyIE0AIOe9kYwA5utEATNYCMiV+v"
        "H5+TPMXB7D7NMnEOcAWMx5bwDglnCSIsg6bZACLRSgqmh9mkV6/jjW7tiJXcdOIPps"
        "2fUWZ40hwhVLaNy+hamTR2EhwHe7eHzxLJJSPyoTVyCqiFkG8uf1FwmoYr7dwsj+g3"
        "g3M42HF04hKfXj2/u32Dt5Ha5YQtZqwuXzMDNbRpA5RwISvUdxcA32TV5DyHp4M/0A"
        "u0+PY3DzVmStJkQXdmMmmXOcJzBjlqaZg3TFueA7HWihIHvGLuP7xw8Y3LQF3bmvEK"
        "eAIVIVDKGbeZ/BjFJJU61Vq02QV/PlAZUkUfOe+ZVlDm3bTguBmiSkOtI5zZdXK8ir"
        "tWq1WUlT/bOUQyBiJEX+KuX/fib87zv/ABcQG5DXWw29AAAAAElFTkSuQmCC"
    ,
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
        # Die Bilder müssen am Objekt hängen bleiben: Tkinter hält keine
        # eigene Referenz, und ein eingesammeltes PhotoImage hinterlässt
        # ein leeres Kästchen.
        self._bilder: Dict[str, tk.PhotoImage] = {}
        self._setup_fonts()
        self.apply()

    def _eigenes_kaestchen(self, st: ttk.Style, c: Dict[str, str]) -> None:
        """Ersetzt clams Kreuz durch ein gezeichnetes Häkchen.

        Schlägt irgendetwas daran fehl - eine ältere Tk-Fassung ohne
        PNG-Unterstützung etwa -, bleibt es beim eingebauten Aussehen.
        Ein hübscheres Kästchen ist es nicht wert, dass die App nicht
        startet.
        """
        vorsatz = "DUNKEL" if self.dark else "LICHT"
        try:
            for zustand in ("AUS", "UEBER", "AN"):
                self._bilder[zustand] = tk.PhotoImage(
                    master=self.root,
                    data=HAKEN_PNG[f"{vorsatz}_{zustand}"])

            st.element_create(
                "Haken.indicator", "image", self._bilder["AUS"],
                ("selected", self._bilder["AN"]),
                ("active", self._bilder["UEBER"]),
                border=0, sticky="", padding=(0, 0, 8, 0))
        except (tk.TclError, KeyError):
            return

        for stil, grund in (("TCheckbutton", c["surface"]),
                            ("Bg.TCheckbutton", c["bg"])):
            st.layout(stil, [
                ("Checkbutton.padding", {"sticky": "nswe", "children": [
                    ("Haken.indicator", {"side": "left", "sticky": ""}),
                    ("Checkbutton.focus", {"side": "left", "sticky": "w",
                                           "children": [
                                               ("Checkbutton.label",
                                                {"sticky": "nswe"})]})]})])
            st.configure(stil, background=grund, focuscolor=grund,
                         padding=(0, 3))

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
        # Ein sichtbarer Rand gehört dazu: Er trägt die Knopfform auch
        # dann, wenn Fläche und Untergrund einander ähneln - und beim
        # Darübergehen ändert sich die Fläche deutlich genug, um
        # zu zeigen, dass hier etwas anklickbar ist.
        st.configure("TButton", background=c["button"], foreground=c["text"],
                     borderwidth=1, relief="solid", padding=(14, 7),
                     bordercolor=c["button_border"], lightcolor=c["button"],
                     darkcolor=c["button"])
        st.map("TButton",
               background=[("pressed", c["button_border"]),
                           ("active", c["button_hover"]),
                           ("disabled", c["surface_alt"])],
               foreground=[("disabled", c["muted"])],
               bordercolor=[("disabled", c["border"]),
                            ("!disabled", c["button_border"])],
               lightcolor=[("active", c["button_hover"])],
               darkcolor=[("active", c["button_hover"])])

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

        st.configure("Small.TButton", background=c["button"], foreground=c["text"],
                     borderwidth=1, relief="solid", padding=(8, 4),
                     font=self.font_small, bordercolor=c["button_border"],
                     lightcolor=c["button"], darkcolor=c["button"])
        st.map("Small.TButton",
               background=[("pressed", c["button_border"]),
                           ("active", c["button_hover"]),
                           ("disabled", c["surface_alt"])],
               foreground=[("disabled", c["muted"])],
               bordercolor=[("disabled", c["border"]),
                            ("!disabled", c["button_border"])],
               lightcolor=[("active", c["button_hover"])],
               darkcolor=[("active", c["button_hover"])])

        # Eingabefelder
        st.configure("TEntry", fieldbackground=c["surface"], foreground=c["text"],
                     bordercolor=c["border"], lightcolor=c["border"],
                     darkcolor=c["border"], insertcolor=c["text"], padding=6)
        st.map("TEntry", bordercolor=[("focus", c["accent"])])

        # Bei "readonly" markiert ttk den Inhalt wie eine Textauswahl. Ohne die
        # folgenden Zuordnungen steht der Text dann weiß auf weiß, sobald das
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

        # Das Kästchen zeichnet clam selbst und kennt dafür genau diese
        # Stellschrauben (nachgefragt über element_options):
        # indicatorbackground ist die Füllung, indicatorforeground das
        # Häkchen, upper-/lowerbordercolor der Rahmen. Ohne Zutun sitzt
        # darin ein schwarzes Kreuz auf weißem Grund - neben allem
        # anderen ein Fremdkörper. Angehakt wird das Kästchen jetzt in
        # Akzentfarbe gefüllt, das Häkchen steht hell darauf.
        def kaestchen(stil: str, grund: str) -> None:
            st.configure(stil, background=grund, foreground=c["text"],
                         focuscolor=grund, padding=(0, 3),
                         indicatormargin=(0, 0, 7, 0),
                         indicatorbackground=c["surface"],
                         indicatorforeground=c["accent_text"],
                         upperbordercolor=c["border"],
                         lowerbordercolor=c["border"])
            st.map(stil,
                   background=[("active", grund)],
                   indicatorbackground=[
                       ("disabled", grund),
                       ("selected", c["accent"]),
                       ("active", c["selection"]),
                       ("!selected", c["surface"])],
                   indicatorforeground=[("selected", c["accent_text"])],
                   upperbordercolor=[("selected", c["accent"]),
                                     ("active", c["accent"]),
                                     ("!selected", c["border"])],
                   lowerbordercolor=[("selected", c["accent"]),
                                     ("active", c["accent"]),
                                     ("!selected", c["border"])])

        kaestchen("TCheckbutton", c["surface"])
        kaestchen("Bg.TCheckbutton", c["bg"])
        self._eigenes_kaestchen(st, c)

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
