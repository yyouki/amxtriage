"""Optional beginner-friendly desktop UI built with Python's standard library."""

from __future__ import annotations

import threading
from pathlib import Path
from queue import Empty, SimpleQueue

from amxtriage.analysis import analyze_logs, build_report
from amxtriage.errors import InputError
from amxtriage.localization import SUPPORTED_LANGUAGES
from amxtriage.render import render_report
from amxtriage.source import SourceIndex

GUI_MAX_INPUT_BYTES = 512 * 1024 * 1024
GUI_REPORT_TOP = 100
GUI_CONTEXT_RADIUS = 3

_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "title": "amxtriage — Server Log Analyzer",
        "log": "Server log",
        "browse": "Browse…",
        "source": "Pawn source folder (optional)",
        "folder": "Choose folder…",
        "language": "Interface language",
        "analyze": "Analyze log",
        "save": "Save report…",
        "ready": "Choose a server log to begin.",
        "running": "Analyzing log. Large files may take a while…",
        "done": "Analysis complete.",
        "choose_log": "Select a log file before analysis.",
        "no_file": "The selected path is not a regular file.",
        "error": "Analysis failed",
        "saved": "Report saved.",
        "save_error": "Could not save the report",
        "log_types": "Log files",
        "all_files": "All files",
        "report_hint": "Results appear here. Input logs are read only.",
        "unavailable": "This interface requires Tkinter. Install Tkinter or use the CLI.",
        "no_display": "No desktop display is available. Use a desktop session or the CLI.",
    },
    "id": {
        "title": "amxtriage — Penganalisis Log Server",
        "log": "Log server",
        "browse": "Pilih file…",
        "source": "Folder source Pawn (opsional)",
        "folder": "Pilih folder…",
        "language": "Bahasa antarmuka",
        "analyze": "Analisis log",
        "save": "Simpan laporan…",
        "ready": "Pilih log server untuk memulai.",
        "running": "Sedang menganalisis. File besar mungkin perlu waktu…",
        "done": "Analisis selesai.",
        "choose_log": "Pilih file log sebelum analisis.",
        "no_file": "Path yang dipilih bukan file biasa.",
        "error": "Analisis gagal",
        "saved": "Laporan disimpan.",
        "save_error": "Laporan tidak dapat disimpan",
        "log_types": "File log",
        "all_files": "Semua file",
        "report_hint": "Hasil akan muncul di sini. Log hanya dibaca, tidak diubah.",
        "unavailable": "Antarmuka ini memerlukan Tkinter. Pasang Tkinter atau gunakan CLI.",
        "no_display": "Layar desktop tidak tersedia. Gunakan sesi desktop atau CLI.",
    },
    "es": {
        "title": "amxtriage — Analizador de registros",
        "log": "Registro del servidor",
        "browse": "Examinar…",
        "source": "Carpeta de código Pawn (opcional)",
        "folder": "Elegir carpeta…",
        "language": "Idioma de la interfaz",
        "analyze": "Analizar registro",
        "save": "Guardar informe…",
        "ready": "Elige un registro para comenzar.",
        "running": "Analizando. Los archivos grandes pueden tardar…",
        "done": "Análisis completado.",
        "choose_log": "Selecciona un registro antes del análisis.",
        "no_file": "La ruta seleccionada no es un archivo normal.",
        "error": "Error de análisis",
        "saved": "Informe guardado.",
        "save_error": "No se pudo guardar el informe",
        "log_types": "Archivos de registro",
        "all_files": "Todos los archivos",
        "report_hint": "Los resultados aparecerán aquí. Los registros solo se leen.",
        "unavailable": "La interfaz necesita Tkinter. Instálalo o usa la CLI.",
        "no_display": "No hay pantalla de escritorio. Usa una sesión gráfica o la CLI.",
    },
}


def analyze_for_gui(log_path: str, *, language: str = "en", source_dir: str | None = None) -> str:
    """Analyze one local log with conservative defaults and return a plain-text report."""
    if language not in SUPPORTED_LANGUAGES:
        raise InputError(f"unsupported language: {language}")
    target = Path(log_path).expanduser()
    if not target.is_file():
        raise InputError(f"not a readable regular log file: {str(target)!r}")
    result = analyze_logs([str(target)], max_input_bytes=GUI_MAX_INPUT_BYTES)
    source_index = SourceIndex(source_dir) if source_dir else None
    report = build_report(
        result,
        top=GUI_REPORT_TOP,
        source_index=source_index,
        context_radius=GUI_CONTEXT_RADIUS if source_index else 0,
    )
    return render_report(report, "text", language=language)


def launch_gui(language: str = "en", start_dir: str | None = None) -> int:
    """Open the optional desktop interface; all analysis uses the existing core."""
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as error:
        raise InputError(_LABELS.get(language, _LABELS["en"])["unavailable"]) from error
    if language not in SUPPORTED_LANGUAGES:
        language = "en"
    try:
        root = tk.Tk()
    except tk.TclError as error:
        raise InputError(_LABELS[language]["no_display"]) from error

    root.title(_LABELS[language]["title"])
    root.geometry("1000x720")
    root.minsize(720, 480)
    frame = ttk.Frame(root, padding=12)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(1, weight=1)
    frame.rowconfigure(4, weight=1)

    log_var = tk.StringVar(root)
    source_var = tk.StringVar(root)
    language_var = tk.StringVar(root, value=language)
    status_var = tk.StringVar(root, value=_LABELS[language]["ready"])
    log_label = ttk.Label(frame)
    log_label.grid(row=0, column=0, sticky="w", padx=(0, 8), pady=5)
    ttk.Entry(frame, textvariable=log_var).grid(row=0, column=1, sticky="ew", pady=5)
    log_button = ttk.Button(frame, command=lambda: choose_log())
    log_button.grid(row=0, column=2, padx=(8, 0), pady=5)
    source_label = ttk.Label(frame)
    source_label.grid(row=1, column=0, sticky="w", padx=(0, 8), pady=5)
    ttk.Entry(frame, textvariable=source_var).grid(row=1, column=1, sticky="ew", pady=5)
    source_button = ttk.Button(frame, command=lambda: choose_source())
    source_button.grid(row=1, column=2, padx=(8, 0), pady=5)
    language_label = ttk.Label(frame)
    language_label.grid(row=2, column=0, sticky="w", padx=(0, 8), pady=5)
    language_select = ttk.Combobox(
        frame, textvariable=language_var, values=("en", "id", "es"), state="readonly", width=10
    )
    language_select.grid(row=2, column=1, sticky="w", pady=5)

    actions = ttk.Frame(frame)
    actions.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 10))
    analyze_button = ttk.Button(actions, command=lambda: run_analysis())
    analyze_button.pack(side="left")
    save_button = ttk.Button(actions, command=lambda: save_report(), state="disabled")
    save_button.pack(side="left", padx=(8, 0))

    report_frame = ttk.Frame(frame)
    report_frame.grid(row=4, column=0, columnspan=3, sticky="nsew")
    report_frame.rowconfigure(0, weight=1)
    report_frame.columnconfigure(0, weight=1)
    report_text = tk.Text(report_frame, wrap="none", font=("TkFixedFont", 10), state="disabled")
    scroll_y = ttk.Scrollbar(report_frame, orient="vertical", command=report_text.yview)
    scroll_x = ttk.Scrollbar(report_frame, orient="horizontal", command=report_text.xview)
    report_text.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
    report_text.grid(row=0, column=0, sticky="nsew")
    scroll_y.grid(row=0, column=1, sticky="ns")
    scroll_x.grid(row=1, column=0, sticky="ew")
    ttk.Label(frame, textvariable=status_var, anchor="w").grid(
        row=5, column=0, columnspan=3, sticky="ew", pady=(10, 0)
    )
    last_report: list[str] = [""]
    busy = [False]
    pending_results: SimpleQueue[tuple[str | None, str | None]] = SimpleQueue()

    def choose_log() -> None:
        labels = _LABELS[language_var.get()]
        selected = filedialog.askopenfilename(
            title=labels["log"],
            initialdir=start_dir or None,
            filetypes=((labels["log_types"], "*.log *.txt *.gz"), (labels["all_files"], "*")),
        )
        if selected:
            log_var.set(selected)

    def choose_source() -> None:
        labels = _LABELS[language_var.get()]
        selected = filedialog.askdirectory(
            title=labels["source"], initialdir=start_dir or None, mustexist=True
        )
        if selected:
            source_var.set(selected)

    def update_language(_event: object | None = None) -> None:
        labels = _LABELS.get(language_var.get(), _LABELS["en"])
        root.title(labels["title"])
        log_label.configure(text=labels["log"])
        log_button.configure(text=labels["browse"])
        source_label.configure(text=labels["source"])
        source_button.configure(text=labels["folder"])
        language_label.configure(text=labels["language"])
        analyze_button.configure(text=labels["analyze"])
        save_button.configure(text=labels["save"])
        if not busy[0]:
            status_var.set(labels["done"] if last_report[0] else labels["ready"])

    def finish(report: str | None, error_message: str | None) -> None:
        busy[0] = False
        analyze_button.configure(state="normal")
        if report is not None:
            last_report[0] = report
            report_text.configure(state="normal")
            report_text.delete("1.0", "end")
            report_text.insert("1.0", report)
            report_text.configure(state="disabled")
            save_button.configure(state="normal")
            status_var.set(_LABELS[language_var.get()]["done"])
        else:
            status_var.set(_LABELS[language_var.get()]["ready"])
            if error_message:
                messagebox.showerror(
                    _LABELS[language_var.get()]["error"], error_message, parent=root
                )

    def run_analysis() -> None:
        if busy[0]:
            return
        selected = log_var.get().strip()
        labels = _LABELS[language_var.get()]
        if not selected:
            messagebox.showinfo(labels["title"], labels["choose_log"], parent=root)
            return
        if not Path(selected).expanduser().is_file():
            messagebox.showerror(labels["error"], labels["no_file"], parent=root)
            return
        selected_language = language_var.get()
        selected_source = source_var.get().strip() or None
        busy[0] = True
        analyze_button.configure(state="disabled")
        status_var.set(_LABELS[selected_language]["running"])

        def work() -> None:
            try:
                report = analyze_for_gui(
                    selected, language=selected_language, source_dir=selected_source
                )
                error_message = None
            except (InputError, OSError) as error:
                report = None
                error_message = str(error)
            except Exception as error:
                report = None
                error_message = f"{type(error).__name__}: {error}"
            pending_results.put((report, error_message))

        threading.Thread(target=work, name="amxtriage-gui-analysis", daemon=True).start()

    def save_report() -> None:
        if not last_report[0]:
            return
        labels = _LABELS[language_var.get()]
        selected = filedialog.asksaveasfilename(
            title=labels["save"],
            defaultextension=".txt",
            filetypes=((labels["all_files"], "*.txt"), (labels["all_files"], "*")),
        )
        if not selected:
            return
        try:
            Path(selected).write_text(last_report[0], encoding="utf-8")
        except OSError as error:
            messagebox.showerror(labels["save_error"], str(error), parent=root)
            return
        status_var.set(labels["saved"])

    def poll_results() -> None:
        try:
            while True:
                finish(*pending_results.get_nowait())
        except Empty:
            pass
        root.after(100, poll_results)

    language_select.bind("<<ComboboxSelected>>", update_language)
    root.after(100, poll_results)
    report_text.configure(state="normal")
    report_text.insert("1.0", _LABELS[language]["report_hint"])
    report_text.configure(state="disabled")
    update_language()
    root.mainloop()
    return 0
