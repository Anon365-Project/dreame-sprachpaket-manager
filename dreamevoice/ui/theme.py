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
    # Das Protokoll ist im hellen Design hell. Frueher war es fast
    # schwarz - darauf waren die dunklen Erfolgs- und Warnfarben kaum zu
    # lesen, und ein leeres Terminalfenster ist ohnehin der schwerste
    # Klotz auf der Seite.
    "log_bg": "#F7F9F9",
    "log_text": "#26343A",
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
}


# Die Kaestchen der Auswahlfelder als eingebettete Bilder.
#
# clam zeichnet dort ein festes Kreuz - "angehakt" saehe damit aus wie
# "durchgestrichen". Ein eigenes Bild loest das. Erzeugt wurden sie
# einmalig mit Pillow (vierfach gezeichnet und heruntergerechnet, daher
# die weichen Kanten); zur Laufzeit decodiert tkinter die PNG-Daten
# selbst, es kommt also keine Abhaengigkeit hinzu.
HAKEN_PNG = {
    "LICHT_AUS":
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAABBUlEQVR4nKXTwUrDQB"
        "AG4H9mY1BLsEcxT7Av4sV38uBT+CJefJEFLxUlxd4qoVpidn+ZJZWeatP8sGFJ5hsm"
        "ISsAQFJEhLZvmuYyxtn5mp/UthW7l6qKc7kS5zbbuq6/9o3sNiGEm7Ka358V7pYpzW"
        "KMAjA3AITOOYrq5qePz127fvDeL83CLovV6nqx/HjnkbFaM7mB5eX17XF4tiWZ/llW"
        "QzNmixBCVRTuzl4LQGnz4nCshmbMKskSxMURcD9ixqymlAgwYXSYzOpfx/HJRjExup"
        "vnBJuNqqoAcsIkkq2KSAfB98gpaMaseu/bvo9Pw0fphkaHltWIGbOTf+XJhykXTDnO"
        "vx9iTUvyd7ZWAAAAAElFTkSuQmCC"
    ,
    "LICHT_UEBER":
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAABi0lEQVR4nKWTvS8EUR"
        "TFz70zs7O7omAjRLClQqPxL2iIikqnUBCJRkkmlGoi1CoqofEPKESiUSgXkSiWQtiP"
        "Me/K2Y9kIyssN7nzknfPb+bdefcIamECCB+w6cUsMkka7yVDHHMLCAJDNiMoeWU53X"
        "+3FsaHmUDEhpfXBouVeCOf65lMeV6Xc05YqElhpqpWTZK3wsDqeS4MNu935JGs8E35"
        "pai/opXLrfm5oemxUWQCH8pSnQfM4MxQij9wenOL9cOjh9CFE4Xd6AmUZBdW9g4urs"
        "zMymbmfsgytWTIqs3MdI/05qZmx8fMOaQS58TM2iZr1FBLhqyPN02FgZfxVEUV1EGa"
        "R/8SinpX1JIhq/ACq7WI3we1ZMhqY++bb7YPaVkU/wxtnqrTFpqLIon5z7TTFsiQ9d"
        "HlqpU4KSXO8Ro5dd/2xWHiwFNLhqzKycnr3XPx7Pj6htdY9VRNRNoma9RQS4asbzDp"
        "S0fR+uHRFIDfjHLIUe5L90YF0Audmqn40jDTdtNMNcmf7fwJwjEp7oIXDfMAAAAASU"
        "VORK5CYII="
    ,
    "LICHT_AN":
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACgElEQVR4nK2TP2gUQR"
        "TGvzezt3t7t5coUUSNBBUtBEEQCxEDggiCIAYURRsb/ySNiilUMKcQCxW00KCCWgiC"
        "nYVVGhFLQQQhWEYTlSMxJpe73dvd2Xny9hKJtvpgmdmZ+b335r1vCGLMBCKW6eqhoZ"
        "Kuo6i8mG0ck6wpz2Mbe5R1oPX92rVwKUOLk3UDg2uU510lpn3MtpyvyycmzuUwqSYT"
        "j9o4vj5x/9Y32SeAqedidRWy7J0u+t02bol3ofCHkfgByC0ia0WT0HrH59vVmgKIYd"
        "KqwCZsxGwMs7XMVkbDnBmGzdgaw2mSchY1Y1X0u4URlroGBytB4oyRdtZyZvJ8/wwt"
        "CTFcx4GjFWabIfu+D2vSrw3XbFFeGLoA+eB2zvQXX9AaU/MNnN+/F68uDqDT92GyjA"
        "jkC6uU68qFbV5tIqQm++3E0Rq1+jxO7dmN/r29mGmEaJkUmggMWGHVYksECuMEXZUy"
        "4tTkketRhF2bN+LmsT58+l7D8ZHHSEwGRardRgmKhbTDJMb29T14c+UCTvbuxPjUD6"
        "xe1olnZ08iShL0P32OmWaIkuvC5l1qm7PYZ4lYq9fxbXYOw0cO5m07sG0rVgRlHL33"
        "GO/HJ7CyEiDNDEg5bW1IBjZJiK1VrnYwMf0Th+48wIcvkxg+fBA7N23ApRcvMfpxDC"
        "tyOFta35x14lIpKSSILDMHfhFzUYQTI09Q7TuA6fkmHr1+i2WlvPJLRcUAR8KS/Pec"
        "u/xA++XTptmItVKuRJKCSleCoienF9QpukXilAIvi5oPP9+9cUbKSXAKVZGnUw48Vo"
        "oKhQItrwTUEZQJWhMpTSSj41AOi5SdQlXY//GY/u05/wJyT2RtqaGOGgAAAABJRU5E"
        "rkJggg=="
    ,
    "DUNKEL_AUS":
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAABVklEQVR4nKWTzWoCQQ"
        "zHk8zsh24r4qXQehe8FfHiA/TUZyriM7WXPoCXRXoTvNtCLyIWdT9mJiU79gNqi9Y/"
        "ZBk2/18mhAmCFwIAy6HXu61vgyJWesPWGPkPSmu2po61Mswmk/vNdwY/Dp3rwWWo4c"
        "46e8PsEmZA9DmpzIgStFakHgsDo9nT+EVYlE+3379AVmmeZ+1svQbmqpkfQkSIkwSi"
        "KJ4z2v40TV/Jt6GHRZ63V4tFboxhZ+3ekJx4xCtMxXYGg3PKyulqubxyxvhr/hIzk9"
        "bQaDafXRx0CcsyBOYacDWPwyRe5pqwRErJuNzB8NdAnLDkK/ppH6UdQ3CiyLfjH9FR"
        "2jHkrJWBHN8Jc8USB0EBiFtAPLwL8SJuhaXZePxGSj/UkzO01hYsz/CXEIlHvMJUrN"
        "RjMMMwiuaNVivSWiMptTckJx7xCvO5C6cuk5/pP9f5HdHw9v68WyTEAAAAAElFTkSu"
        "QmCC"
    ,
    "DUNKEL_UEBER":
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAABrUlEQVR4nKWTvUoDQR"
        "DHZzabTc6gFjGKGgI2gg+gb6AQAkELwUYEC/EpJPgCVjYWgp1goQghoLWNVqnsgx9o"
        "EFGJd7lcbuS/S8RC8esPezu3O7/Zub0ZJkiEiVlgrl1LXyZD6eDpScKXZ8aa6R+Q9O"
        "Agt1oU7Izz60eGe8bS0cmYN5rf8Jt3c90gyBARC/ZguOCSSKdbXm7kxL+92tyfn7sB"
        "y3isVM9Huh5fNGrH+cZpjaQbgSKyOSGCPZE4oakwW6RCsXyV8GV6rzRzp23qZ/VK4/"
        "AgX9/eanvZIWMzJLGcsxHDvdW3t0Iiyk8sLFaIeV2tXjb7/eZ9qXFaEy+bNSqZZNaa"
        "lcbshrM1Yw8+8AUDVnekbeIw9CSKXKIiNt3P1FuFLxiwysSxsFKx/eafipnAgFXuj7"
        "jb/o16jKJ/SrmMXBH9Rj1GhUqxxLH66uI+lQiBAauTnArbxvistY3AqK2vT3U1obUo"
        "Y3ywancq9+LlhquF2SL7Dw9h3OmIRJHEEWY3nB0J9uADXzBgte2F6nmlUCyXUGHflf"
        "Lk0nIKpUyPQeW9F/7XTO5S/tzOb95RF8KtByZeAAAAAElFTkSuQmCC"
    ,
    "DUNKEL_AN":
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACeUlEQVR4nKVTS2gUQR"
        "B93T3/NZvdNeSjuQUP6kUxoihIQAioKB5z05Ofo+TmgkSjKPjBixD1ILkFL3rwE+JB"
        "0cVvLgoqQfSUBASzaza7Mzuf7paa7IYEjymomZ7pfvWqXlUzkGnNwJim5anpaU9Gjh"
        "OUKzo26oz+mUlGu4U8E1ajca+/31+NYa3F0OOpTdzLXADYoJYyA6UoYhqAARqcayZE"
        "HdBTyq9fmjg+OE9YRo8TT191xab1yW7L9ka1GoXHf6YpHIO1oQ3hUnXWjKPd40cGfn"
        "NiD7kYsbPZ3qBcDlUcaRXHa1zSW8rUg4WF0M629xImLeFYqdTmLapvwjI2qygmljTt"
        "NcYYVBxDKwXT8zRlKGM557fzbZwHgQVoF3q53jTVVaaSBE57DjOPHuLl+XOIfR9ggk"
        "p3CctNKTUD1DJWgxnGShAtJZxcHj8nn+DL+H042RyEaab7DFoRlqcHSWitYdg2otoS"
        "uGlCyQSG5+HP96/4ePsaOrZux77zF8ENCqCgm6XyFrOwbZR/zGDy7En8evEcmc4eNC"
        "pllC4XYTgu9g4X0w4kYSPVpGVGq89KSti5PDJdPfhw62oqyOy7N6jNz+HgjTvI9W1B"
        "uPgXXIhlXZu95rEQjDHGSeVMZxcGrtxE945deHt9FHPvS9gzXET3zn5E1UVw0qc1Fk"
        "2soVw30pEKuBA68X1qE/YXR/H5wRjcQgf6Dh1FVK+BNZmb9CRbQFhG30PPXo+5+fxp"
        "GiQoZRET1a2UQhL4a0ZDa0TuxoIdVCp3Jw4fOMNplG0lR8JqddbNF2xhOwycsyRsMB"
        "VHTFgW46bZdIu5hYJNZwmzchfWd5nWeZ3/AUMgZxRMI8fqAAAAAElFTkSuQmCC"
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

        # Das Kaestchen zeichnet clam selbst und kennt dafuer genau diese
        # Stellschrauben (nachgefragt ueber element_options):
        # indicatorbackground ist die Fuellung, indicatorforeground das
        # Haekchen, upper-/lowerbordercolor der Rahmen. Ohne Zutun sitzt
        # darin ein schwarzes Kreuz auf weissem Grund - neben allem
        # anderen ein Fremdkoerper. Angehakt wird das Kaestchen jetzt in
        # Akzentfarbe gefuellt, das Haekchen steht hell darauf.
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
