"""Wiederverwendbare Bausteine der Oberfläche."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import ttk
from typing import Callable, Optional

from .theme import Theme


class Card(ttk.Frame):
    """Abgesetzter Kasten mit Titel - gliedert die Tabs optisch."""

    def __init__(self, master, theme: Theme, title: str = "",
                 subtitle: str = "", **kwargs) -> None:
        super().__init__(master, style="Card.TFrame", **kwargs)
        self.theme = theme
        self.body = self

        pad_top = 16
        if title:
            header = ttk.Frame(self, style="Card.TFrame")
            header.pack(fill="x", padx=18, pady=(16, 0))
            ttk.Label(header, text=title, style="Heading.TLabel").pack(anchor="w")
            if subtitle:
                ttk.Label(header, text=subtitle, style="Muted.TLabel",
                          wraplength=760, justify="left").pack(anchor="w", pady=(3, 0))
            pad_top = 12

        self.content = ttk.Frame(self, style="Card.TFrame")
        self.content.pack(fill="both", expand=True, padx=18, pady=(pad_top, 16))

    def separator(self) -> None:
        ttk.Frame(self.content, style="Separator.TFrame", height=1).pack(
            fill="x", pady=12)


class FormRow(ttk.Frame):
    """Beschriftung links, Eingabefeld rechts."""

    def __init__(self, master, theme: Theme, label: str, width: int = 15) -> None:
        super().__init__(master, style="Card.TFrame")
        self.pack(fill="x", pady=5)
        ttk.Label(self, text=label, style="Surface.TLabel", width=width,
                  anchor="w").pack(side="left", padx=(0, 10))
        self.field = ttk.Frame(self, style="Card.TFrame")
        self.field.pack(side="left", fill="x", expand=True)


class StatusBadge(ttk.Label):
    """Kurzer Zustandstext mit farblicher Bedeutung."""

    def __init__(self, master, theme: Theme, text: str = "") -> None:
        super().__init__(master, text=text, style="Muted.TLabel")
        self.theme = theme

    def set(self, text: str, kind: str = "muted") -> None:
        styles = {
            "muted": "Muted.TLabel",
            "ok": "Success.TLabel",
            "warn": "Warning.TLabel",
            "error": "Danger.TLabel",
        }
        self.configure(text=text, style=styles.get(kind, "Muted.TLabel"))


class LogView(ttk.Frame):
    """Fortlaufendes Protokoll mit Zeitstempel und Farbmarkierung."""

    def __init__(self, master, theme: Theme, height: int = 14) -> None:
        super().__init__(master, style="Card.TFrame")
        self.theme = theme
        c = theme.colors

        self.text = tk.Text(
            self, height=height, wrap="word", relief="flat", borderwidth=0,
            background=c["log_bg"], foreground=c["log_text"],
            insertbackground=c["log_text"], font=theme.font_mono,
            padx=12, pady=10, state="disabled",
        )
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)

        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.text.tag_configure("time", foreground=c["muted"])
        self.text.tag_configure("info", foreground=c["log_text"])
        self.text.tag_configure("ok", foreground=c["success"])
        self.text.tag_configure("warn", foreground=c["warning"])
        self.text.tag_configure("error", foreground=c["danger"])
        self.text.tag_configure("step", foreground=c["accent"])

    def append(self, message: str, kind: str = "info") -> None:
        self.text.configure(state="normal")
        stamp = datetime.now().strftime("%H:%M:%S")
        self.text.insert("end", f"{stamp}  ", ("time",))
        self.text.insert("end", message.rstrip() + "\n", (kind,))
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def dump(self) -> str:
        return self.text.get("1.0", "end")


def autowrap(label: ttk.Label, container: tk.Misc, padding: int = 40) -> None:
    """Lässt einen Text mit der Fensterbreite mitwachsen.

    Ohne das bleibt ein Label bei seiner fest eingestellten Zeilenbreite -
    beim Maximieren entsteht dann rechts eine grosse leere Fläche, und auf
    schmalen Fenstern ragt der Text hinaus.
    """
    def on_resize(event) -> None:
        breite = max(200, event.width - padding)
        if label.cget("wraplength") != breite:
            label.configure(wraplength=breite)

    container.bind("<Configure>", on_resize, add="+")


class ScrollablePage(ttk.Frame):
    """Ein Tab-Inhalt, der bei zu kleinem Fenster senkrecht scrollt.

    Tkinter blendet Inhalte, die nicht ins Fenster passen, einfach ab -
    ohne Hinweis und ohne Möglichkeit, sie zu erreichen. Deshalb liegt der
    Inhalt jedes Tabs in einem Canvas, der bei Bedarf scrollt. Die
    Bildlaufleiste erscheint nur, wenn sie gebraucht wird.
    """

    def __init__(self, master, theme: Theme, padding: tuple = (20, 18)) -> None:
        super().__init__(master, style="TFrame")
        self.theme = theme

        self.canvas = tk.Canvas(self, background=theme.color("bg"),
                                highlightthickness=0, borderwidth=0)
        self.scroll = ttk.Scrollbar(self, orient="vertical",
                                    command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._on_scroll_set)
        self.canvas.pack(side="left", fill="both", expand=True)

        self.content = ttk.Frame(self.canvas, style="TFrame")
        self._window = self.canvas.create_window(
            (0, 0), window=self.content, anchor="nw")
        self._padx, self._pady = padding

        self.content.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", lambda _e: self._bind_wheel(True))
        self.canvas.bind("<Leave>", lambda _e: self._bind_wheel(False))
        self._scroll_visible = False

    # -- Grösse und Sichtbarkeit ------------------------------------------
    def _on_scroll_set(self, first: str, last: str) -> None:
        noetig = not (float(first) <= 0.0 and float(last) >= 1.0)
        if noetig != self._scroll_visible:
            self._scroll_visible = noetig
            if noetig:
                self.scroll.pack(side="right", fill="y")
            else:
                self.scroll.pack_forget()
        self.scroll.set(first, last)

    def _on_content_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    # -- Mausrad -----------------------------------------------------------
    def _bind_wheel(self, active: bool) -> None:
        if active:
            self.canvas.bind_all("<MouseWheel>", self._on_wheel)
            self.canvas.bind_all("<Button-4>", self._on_wheel)
            self.canvas.bind_all("<Button-5>", self._on_wheel)
        else:
            self.canvas.unbind_all("<MouseWheel>")
            self.canvas.unbind_all("<Button-4>")
            self.canvas.unbind_all("<Button-5>")

    def _on_wheel(self, event) -> None:
        if not self._scroll_visible:
            return
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            delta = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(delta * 3, "units")

    def body(self) -> ttk.Frame:
        """Innerer Rahmen mit Rand - hier kommt der Tab-Inhalt hinein."""
        rahmen = ttk.Frame(self.content, style="TFrame")
        rahmen.pack(fill="both", expand=True, padx=self._padx, pady=self._pady)
        return rahmen


class ScrollableList(ttk.Frame):
    """Senkrecht scrollbarer Bereich für beliebige Widgets.

    Tkinter kann das nicht von Haus aus - nötig sind ein Canvas, ein
    inneres Frame und die Kopplung der Größen.
    """

    def __init__(self, master, theme: Theme) -> None:
        super().__init__(master, style="Card.TFrame")
        self.theme = theme

        self.canvas = tk.Canvas(self, background=theme.color("surface"),
                                highlightthickness=0, borderwidth=0)
        self.scroll = ttk.Scrollbar(self, orient="vertical",
                                    command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")

        self.inner = ttk.Frame(self.canvas, style="Card.TFrame")
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", lambda _e: self._bind_wheel(True))
        self.canvas.bind("<Leave>", lambda _e: self._bind_wheel(False))

    def _on_inner_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def _bind_wheel(self, active: bool) -> None:
        if active:
            self.canvas.bind_all("<MouseWheel>", self._on_wheel)
            self.canvas.bind_all("<Button-4>", self._on_wheel)
            self.canvas.bind_all("<Button-5>", self._on_wheel)
        else:
            self.canvas.unbind_all("<MouseWheel>")
            self.canvas.unbind_all("<Button-4>")
            self.canvas.unbind_all("<Button-5>")

    def _on_wheel(self, event) -> None:
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            delta = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(delta, "units")

    def clear(self) -> None:
        for child in self.inner.winfo_children():
            child.destroy()

    def scroll_to_top(self) -> None:
        self.canvas.yview_moveto(0.0)


class InfoBanner(ttk.Frame):
    """Auffälliger Hinweis oben in einem Tab."""

    def __init__(self, master, theme: Theme, text: str, kind: str = "info") -> None:
        super().__init__(master, style="Alt.TFrame")
        self.theme = theme
        colors = {
            "info": theme.color("accent"),
            "warn": theme.color("warning"),
            "error": theme.color("danger"),
            "ok": theme.color("success"),
        }
        bar = tk.Frame(self, background=colors.get(kind, theme.color("accent")), width=4)
        bar.pack(side="left", fill="y")

        self.label = ttk.Label(self, text=text, style="Muted.TLabel",
                               wraplength=820, justify="left")
        self.label.pack(side="left", fill="x", expand=True, padx=12, pady=10)
        autowrap(self.label, self, padding=44)

    def set_text(self, text: str) -> None:
        self.label.configure(text=text)


class BusyOverlay:
    """Sperrt Bedienelemente während eines Hintergrundvorgangs."""

    def __init__(self, *widgets: tk.Widget) -> None:
        self._widgets = widgets
        self._saved: dict = {}

    def enter(self) -> None:
        for widget in self._widgets:
            try:
                self._saved[widget] = widget.cget("state")
                widget.configure(state="disabled")
            except tk.TclError:
                pass

    def leave(self) -> None:
        for widget, state in self._saved.items():
            try:
                widget.configure(state=state)
            except tk.TclError:
                pass
        self._saved.clear()


def labeled_value(master, theme: Theme, label: str, value: str = "-") -> ttk.Label:
    """Zeile 'Bezeichnung: Wert' - gibt das Wert-Label zum Aktualisieren zurück."""
    row = ttk.Frame(master, style="Card.TFrame")
    row.pack(fill="x", pady=2)
    ttk.Label(row, text=label, style="Muted.TLabel", width=20,
              anchor="w").pack(side="left")
    value_label = ttk.Label(row, text=value, style="Mono.TLabel")
    value_label.pack(side="left", fill="x", expand=True)
    return value_label


def copy_to_clipboard(widget: tk.Misc, text: str) -> None:
    widget.clipboard_clear()
    widget.clipboard_append(text)
    widget.update_idletasks()


class MessageDialog(tk.Toplevel):
    """Meldungsfenster, aus dem sich der Text herauskopieren lässt.

    Die eingebauten `messagebox`-Fenster von Tkinter geben ihren Text nicht
    heraus - man kann ihn weder markieren noch kopieren. Bei einer
    Fehlermeldung mit Serverantwort ist das ärgerlich, weil sich damit
    schlecht nachfragen lässt. Deshalb dieses Fenster: Text markierbar,
    dazu ein Knopf, der alles in die Zwischenablage legt.
    """

    FARBEN = {"error": "danger", "warn": "warning", "ok": "success",
              "info": "accent"}

    def __init__(self, master, theme: Theme, title: str, message: str,
                 hint: str = "", kind: str = "info") -> None:
        super().__init__(master)
        self.theme = theme
        self.title(title)
        self.configure(bg=theme.color("bg"))
        self.transient(master.winfo_toplevel())
        self.resizable(True, True)

        self._volltext = message + (f"\n\n{hint}" if hint else "")

        rahmen = ttk.Frame(self, style="Card.TFrame")
        rahmen.pack(fill="both", expand=True, padx=16, pady=16)

        kopf = ttk.Frame(rahmen, style="Card.TFrame")
        kopf.pack(fill="x", padx=16, pady=(16, 0))
        balken = tk.Frame(kopf, background=theme.color(self.FARBEN.get(kind, "accent")),
                          width=4, height=22)
        balken.pack(side="left", fill="y", padx=(0, 10))
        ttk.Label(kopf, text=title, style="Heading.TLabel").pack(side="left")

        koerper = ttk.Frame(rahmen, style="Card.TFrame")
        koerper.pack(fill="both", expand=True, padx=16, pady=(10, 0))

        self.text = tk.Text(koerper, wrap="word", relief="flat", borderwidth=0,
                            background=theme.color("surface"),
                            foreground=theme.color("text"),
                            font=theme.font_body, padx=2, pady=2,
                            height=self._zeilen(), width=72)
        scroll = ttk.Scrollbar(koerper, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.text.insert("1.0", message + "\n")
        if hint:
            self.text.insert("end", "\n" + hint, ("hint",))
        self.text.tag_configure("hint", foreground=theme.color("muted"))
        # Nur lesen, aber weiterhin markier- und kopierbar.
        self.text.configure(state="normal")
        self.text.bind("<Key>", self._nur_kopieren)

        knoepfe = ttk.Frame(rahmen, style="Card.TFrame")
        knoepfe.pack(fill="x", padx=16, pady=16)
        self.btn_copy = ttk.Button(knoepfe, text="Text kopieren",
                                   command=self._kopieren)
        self.btn_copy.pack(side="left")
        ttk.Button(knoepfe, text="Schließen", style="Accent.TButton",
                   command=self.destroy).pack(side="right")

        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Control-c>", lambda _e: self._kopieren())
        self._zentrieren()
        self.after(50, self._greifen)

    # ------------------------------------------------------------------
    def _zeilen(self) -> int:
        zeilen = self._volltext.count("\n") + len(self._volltext) // 70 + 2
        return max(6, min(22, zeilen))

    def _nur_kopieren(self, event):
        """Tastatureingaben abweisen, Kopieren und Navigation erlauben."""
        erlaubt = ("c", "a", "C", "A")
        if event.state & 0x0004 and event.keysym in erlaubt:   # Strg
            return None
        if event.keysym in ("Up", "Down", "Left", "Right", "Prior", "Next",
                            "Home", "End", "Shift_L", "Shift_R", "Control_L",
                            "Control_R"):
            return None
        return "break"

    def _kopieren(self) -> None:
        copy_to_clipboard(self, self._volltext)
        self.btn_copy.configure(text="Kopiert")
        self.after(1500, lambda: self.btn_copy.configure(text="Text kopieren"))

    def _zentrieren(self) -> None:
        self.update_idletasks()
        eltern = self.master.winfo_toplevel()
        x = eltern.winfo_rootx() + (eltern.winfo_width() - self.winfo_width()) // 2
        y = eltern.winfo_rooty() + (eltern.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _greifen(self) -> None:
        try:
            self.grab_set()
            self.focus_set()
        except tk.TclError:
            pass


def show_error(parent, theme: Theme, title: str, message: str,
               hint: str = "") -> None:
    MessageDialog(parent, theme, title, message, hint, kind="error")


def show_warning(parent, theme: Theme, title: str, message: str,
                 hint: str = "") -> None:
    MessageDialog(parent, theme, title, message, hint, kind="warn")


def show_info(parent, theme: Theme, title: str, message: str,
              hint: str = "") -> None:
    MessageDialog(parent, theme, title, message, hint, kind="info")
