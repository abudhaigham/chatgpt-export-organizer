"""Small local desktop interface for controlled ChatGPT export imports."""

from __future__ import annotations

import contextlib
import io
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from .inbox import default_workspace, ensure_inbox_layout, incoming_archives, inspect_archive

APP_COLORS = {
    "navy": "#0B1F33",
    "navy_soft": "#153852",
    "teal": "#10A37F",
    "teal_dark": "#087A60",
    "canvas": "#F3F7F9",
    "card": "#FFFFFF",
    "border": "#D7E2E8",
    "text": "#163047",
    "muted": "#607789",
    "success": "#DDF7EE",
}


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


class OrganizerWindow:
    def __init__(self, root: Any) -> None:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk

        self.tk = tk
        self.ttk = ttk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.root = root
        self.root.title("ChatGPT Export Organizer")
        self.root.geometry("980x760")
        self.root.minsize(820, 680)
        self.root.configure(background=APP_COLORS["canvas"])
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.working = False
        self.archives: list[Path] = []

        self.workspace = tk.StringVar(value=str(default_workspace()))
        self.status = tk.StringVar(value="جاهز")
        self.export_chats = tk.BooleanVar(value=True)
        self.group_assets = tk.BooleanVar(value=True)
        self.restore_originals = tk.BooleanVar(value=True)
        self.extract_assets = tk.BooleanVar(value=True)

        self.configure_styles()

        header = tk.Frame(root, background=APP_COLORS["navy"], height=104)
        header.pack(fill="x")
        header.pack_propagate(False)
        brand = tk.Frame(header, background=APP_COLORS["navy"])
        brand.pack(fill="both", expand=True, padx=24, pady=12)
        logo = tk.Canvas(
            brand,
            width=72,
            height=72,
            background=APP_COLORS["navy"],
            highlightthickness=0,
        )
        logo.pack(side="right", padx=(18, 0))
        logo.create_oval(5, 5, 67, 67, fill=APP_COLORS["teal"], outline="")
        logo.create_text(36, 36, text="CO", fill="white", font=("Helvetica", 17, "bold"))
        heading = tk.Frame(brand, background=APP_COLORS["navy"])
        heading.pack(side="right", fill="both", expand=True)
        tk.Label(
            heading,
            text="منظّم تصدير ChatGPT",
            background=APP_COLORS["navy"],
            foreground="white",
            font=("Helvetica", 25, "bold"),
            anchor="e",
        ).pack(fill="x")
        tk.Label(
            heading,
            text="استيراد آمن • تنظيم ذكي • خصوصية محلية",
            background=APP_COLORS["navy"],
            foreground="#C8D8E4",
            font=("Helvetica", 13),
            anchor="e",
        ).pack(fill="x", pady=(7, 0))

        outer = ttk.Frame(root, padding=(20, 12), style="Canvas.TFrame")
        outer.pack(fill="both", expand=True)

        workspace_frame = ttk.LabelFrame(
            outer, text="  1  مساحة العمل  ", padding=10, style="Card.TLabelframe"
        )
        workspace_frame.pack(fill="x")
        ttk.Entry(workspace_frame, textvariable=self.workspace).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(workspace_frame, text="اختيار…", command=self.choose_workspace).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(workspace_frame, text="فتح صندوق الوارد", command=self.open_incoming).pack(
            side="left", padx=(8, 0)
        )

        archive_frame = ttk.LabelFrame(
            outer,
            text="  2  اختر حزمة ZIP من صندوق الوارد  ",
            padding=10,
            style="Card.TLabelframe",
        )
        archive_frame.pack(fill="both", expand=True, pady=8)
        self.archive_list = tk.Listbox(
            archive_frame,
            height=4,
            exportselection=False,
            background="#F8FBFC",
            foreground=APP_COLORS["text"],
            selectbackground=APP_COLORS["teal"],
            selectforeground="white",
            highlightbackground=APP_COLORS["border"],
            highlightcolor=APP_COLORS["teal"],
            highlightthickness=1,
            borderwidth=0,
            font=("Helvetica", 12),
            activestyle="none",
        )
        self.archive_list.pack(fill="both", expand=True)
        ttk.Button(archive_frame, text="تحديث القائمة", command=self.refresh).pack(
            anchor="e", pady=(5, 0)
        )

        options = ttk.LabelFrame(
            outer, text="  3  خيارات المعالجة  ", padding=10, style="Card.TLabelframe"
        )
        options.pack(fill="x")
        ttk.Checkbutton(
            options, text="إنشاء ملفات المحادثات JSON وPDF", variable=self.export_chats
        ).pack(anchor="e")
        ttk.Checkbutton(
            options, text="تجميع المرفقات حسب المحادثات", variable=self.group_assets
        ).pack(anchor="e")
        ttk.Checkbutton(
            options,
            text="استعادة أسماء المرفقات الأصلية",
            variable=self.restore_originals,
        ).pack(anchor="e")
        ttk.Checkbutton(
            options,
            text="استخراج الصور والملفات وتنظيمها حسب النوع",
            variable=self.extract_assets,
        ).pack(anchor="e")

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=8)
        self.validate_button = ttk.Button(
            actions, text="فحص سلامة الحزمة", command=self.validate, style="Secondary.TButton"
        )
        self.validate_button.pack(side="right")
        self.run_button = ttk.Button(
            actions,
            text="بدء الاستيراد والتنظيم",
            command=self.run,
            style="Primary.TButton",
        )
        self.run_button.pack(side="right", padx=8)
        ttk.Button(actions, text="فتح أحدث النتائج", command=self.open_latest_results).pack(
            side="left"
        )

        self.progress = ttk.Progressbar(
            outer, mode="indeterminate", style="Accent.Horizontal.TProgressbar"
        )
        self.progress.pack(fill="x")
        self.status_label = tk.Label(
            outer,
            textvariable=self.status,
            background=APP_COLORS["success"],
            foreground=APP_COLORS["teal_dark"],
            font=("Helvetica", 11, "bold"),
            anchor="e",
            padx=12,
            pady=7,
        )
        self.status_label.pack(fill="x", pady=(6, 6))
        self.log = tk.Text(
            outer,
            height=5,
            wrap="word",
            state="disabled",
            background="#10283D",
            foreground="#D8E7F0",
            insertbackground="white",
            highlightthickness=0,
            borderwidth=0,
            padx=12,
            pady=10,
            font=("Menlo", 10),
        )
        self.log.pack(fill="both", expand=True)

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        ensure_inbox_layout(Path(self.workspace.get()))
        self.refresh()
        self.root.after(150, self.poll_events)

    def configure_styles(self) -> None:
        style = self.ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Canvas.TFrame", background=APP_COLORS["canvas"])
        style.configure("TFrame", background=APP_COLORS["canvas"])
        style.configure(
            "TButton",
            background=APP_COLORS["card"],
            foreground=APP_COLORS["text"],
            bordercolor=APP_COLORS["border"],
        )
        style.map("TButton", background=[("active", "#E7F0F3")])
        style.configure(
            "TEntry",
            fieldbackground=APP_COLORS["card"],
            foreground=APP_COLORS["text"],
            bordercolor=APP_COLORS["border"],
        )
        style.configure(
            "Card.TLabelframe",
            background=APP_COLORS["card"],
            bordercolor=APP_COLORS["border"],
            relief="solid",
        )
        style.configure(
            "Card.TLabelframe.Label",
            background=APP_COLORS["canvas"],
            foreground=APP_COLORS["teal_dark"],
            font=("Helvetica", 12, "bold"),
        )
        style.configure(
            "TCheckbutton",
            background=APP_COLORS["card"],
            foreground=APP_COLORS["text"],
            padding=(2, 2),
        )
        style.map("TCheckbutton", background=[("active", APP_COLORS["card"])])
        style.configure(
            "Primary.TButton",
            background=APP_COLORS["teal"],
            foreground="white",
            bordercolor=APP_COLORS["teal_dark"],
            font=("Helvetica", 12, "bold"),
            padding=(18, 10),
        )
        style.map(
            "Primary.TButton",
            background=[("active", APP_COLORS["teal_dark"]), ("disabled", "#9CBAB2")],
            foreground=[("disabled", "#EAF3F0")],
        )
        style.configure(
            "Secondary.TButton",
            background=APP_COLORS["card"],
            foreground=APP_COLORS["text"],
            bordercolor=APP_COLORS["border"],
            font=("Helvetica", 11),
            padding=(14, 9),
        )
        style.configure(
            "Accent.Horizontal.TProgressbar",
            background=APP_COLORS["teal"],
            troughcolor=APP_COLORS["border"],
        )

    def selected_archive(self) -> Path | None:
        selection = self.archive_list.curselection()
        if not selection:
            self.messagebox.showwarning("لم تُحدد حزمة", "حدد حزمة ZIP من القائمة أولًا.")
            return None
        return self.archives[selection[0]]

    def choose_workspace(self) -> None:
        chosen = self.filedialog.askdirectory(
            title="اختر مساحة عمل ChatGPT Export Organizer",
            initialdir=self.workspace.get(),
        )
        if chosen:
            self.workspace.set(chosen)
            ensure_inbox_layout(Path(chosen))
            self.refresh()

    def open_path(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            self.messagebox.showinfo("المسار", str(path))

    def open_incoming(self) -> None:
        self.open_path(ensure_inbox_layout(Path(self.workspace.get()))["incoming"])

    def open_latest_results(self) -> None:
        workspace = Path(self.workspace.get()).expanduser()
        latest = workspace / "LATEST_IMPORT.txt"
        if not latest.exists():
            self.messagebox.showinfo("لا توجد نتائج", "لم يُسجّل استيراد حديث بعد.")
            return
        try:
            import_root = Path(latest.read_text(encoding="utf-8").strip())
        except OSError as error:
            self.messagebox.showerror("تعذر فتح النتائج", str(error))
            return
        results = import_root / "results"
        if not results.is_dir():
            self.messagebox.showerror("تعذر فتح النتائج", f"المجلد غير موجود:\n{results}")
            return
        self.open_path(results)

    def refresh(self) -> None:
        self.archives = incoming_archives(Path(self.workspace.get()))
        self.archive_list.delete(0, self.tk.END)
        for archive in self.archives:
            self.archive_list.insert(
                self.tk.END, f"{archive.name}  —  {human_size(archive.stat().st_size)}"
            )
        if len(self.archives) == 1:
            self.archive_list.selection_set(0)
        self.status.set(f"عدد الحزم في صندوق الوارد: {len(self.archives)}")

    def set_working(self, value: bool, message: str) -> None:
        self.working = value
        state = "disabled" if value else "normal"
        self.validate_button.configure(state=state)
        self.run_button.configure(state=state)
        self.status.set(message)
        self.status_label.configure(
            background="#FFF3D6" if value else APP_COLORS["success"],
            foreground="#8A5A00" if value else APP_COLORS["teal_dark"],
        )
        if value:
            self.progress.start(12)
        else:
            self.progress.stop()

    def append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert(self.tk.END, text.rstrip() + "\n")
        self.log.see(self.tk.END)
        self.log.configure(state="disabled")

    def validate(self) -> None:
        archive = self.selected_archive()
        if archive is None or self.working:
            return
        self.set_working(True, "جارٍ فحص جميع محتويات الحزمة…")

        def worker() -> None:
            inspection = inspect_archive(archive)
            self.events.put(("validation", inspection))

        threading.Thread(target=worker, daemon=True).start()

    def run(self) -> None:
        archive = self.selected_archive()
        if archive is None or self.working:
            return
        if self.restore_originals.get() and not self.group_assets.get():
            self.messagebox.showwarning(
                "خيار غير متوافق", "استعادة الأسماء الأصلية تتطلب تجميع المرفقات."
            )
            return
        command = [
            "--process-inbox",
            archive.name,
            "--workspace",
            str(Path(self.workspace.get()).expanduser()),
            "--import-name",
            archive.stem,
            "--recursive",
            "--quiet",
        ]
        if self.group_assets.get():
            command.append("--group")
        if self.restore_originals.get():
            command.append("--restore-originals")
        if self.export_chats.get():
            command.append("--export-chats")
        if self.extract_assets.get():
            command.append("--extract-assets")
        self.set_working(True, "جارٍ التحقق والاستيراد والتنظيم…")
        self.append_log(f"بدأت معالجة: {archive.name}")

        def worker() -> None:
            from .cli import main as cli_main

            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                returncode = cli_main(command)
            result = {
                "returncode": returncode,
                "stdout": stdout.getvalue(),
                "stderr": stderr.getvalue(),
            }
            self.events.put(("run", result))

        threading.Thread(target=worker, daemon=True).start()

    def poll_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                self.set_working(False, "جاهز")
                if kind == "validation":
                    if payload.valid:
                        self.append_log(
                            f"PASS — {Path(payload.path).name} — {human_size(payload.size)}\n"
                            f"SHA-256: {payload.sha256}"
                        )
                        self.messagebox.showinfo("الحزمة سليمة", "اكتمل فحص ZIP بنجاح.")
                    else:
                        self.append_log(f"FAIL — {payload.error}")
                        self.messagebox.showerror("الحزمة غير صالحة", payload.error)
                elif kind == "run":
                    if payload["stdout"]:
                        self.append_log(payload["stdout"])
                    if payload["stderr"]:
                        self.append_log(payload["stderr"])
                    self.refresh()
                    if payload["returncode"] == 0:
                        self.status.set("اكتملت العملية بنجاح")
                        self.messagebox.showinfo(
                            "اكتملت العملية",
                            "تم الاستيراد والتنظيم بنجاح.\n\n"
                            "تنبيه: لا يتضمن تصدير OpenAI علاقة موثوقة بين "
                            "المحادثات والمشاريع؛ لذلك حُفظت جميع المحادثات معًا "
                            "دون تخمين تصنيف المشروع.",
                        )
                    else:
                        self.status.set("توقفت العملية بسبب خطأ")
                        self.messagebox.showerror(
                            "تعذر إكمال العملية", "راجع سجل العملية الظاهر في النافذة."
                        )
        except queue.Empty:
            pass
        self.root.after(150, self.poll_events)

    def close(self) -> None:
        if self.working:
            self.messagebox.showwarning("المعالجة جارية", "انتظر حتى تنتهي العملية قبل الإغلاق.")
            return
        self.root.destroy()


def main() -> int:
    try:
        import tkinter as tk
    except ImportError:
        print("Error: the desktop interface requires Python with Tk support.", file=sys.stderr)
        return 2
    root = tk.Tk()
    OrganizerWindow(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
