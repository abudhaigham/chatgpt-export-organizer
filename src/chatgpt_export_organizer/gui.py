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
        self.root.geometry("820x610")
        self.root.minsize(720, 520)
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.working = False
        self.archives: list[Path] = []

        self.workspace = tk.StringVar(value=str(default_workspace()))
        self.status = tk.StringVar(value="جاهز")
        self.export_chats = tk.BooleanVar(value=True)
        self.group_assets = tk.BooleanVar(value=True)
        self.restore_originals = tk.BooleanVar(value=True)

        outer = ttk.Frame(root, padding=18)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="منظّم تصدير ChatGPT", font=("Helvetica", 22, "bold")).pack(anchor="e")
        ttk.Label(
            outer,
            text="ضع حزمة OpenAI داخل صندوق الوارد، ثم افحصها وابدأ الاستيراد.",
        ).pack(anchor="e", pady=(4, 18))

        workspace_frame = ttk.LabelFrame(outer, text="مساحة العمل", padding=10)
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

        archive_frame = ttk.LabelFrame(outer, text="حزم ZIP الموجودة في صندوق الوارد", padding=10)
        archive_frame.pack(fill="both", expand=True, pady=12)
        self.archive_list = tk.Listbox(archive_frame, height=8, exportselection=False)
        self.archive_list.pack(fill="both", expand=True)
        ttk.Button(archive_frame, text="تحديث القائمة", command=self.refresh).pack(
            anchor="e", pady=(8, 0)
        )

        options = ttk.LabelFrame(outer, text="خيارات المعالجة", padding=10)
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

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=12)
        self.validate_button = ttk.Button(actions, text="فحص الحزمة", command=self.validate)
        self.validate_button.pack(side="right")
        self.run_button = ttk.Button(actions, text="بدء الاستيراد والتنظيم", command=self.run)
        self.run_button.pack(side="right", padx=8)
        ttk.Button(actions, text="فتح أحدث النتائج", command=self.open_latest_results).pack(
            side="left"
        )

        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.pack(fill="x")
        ttk.Label(outer, textvariable=self.status).pack(anchor="e", pady=(6, 4))
        self.log = tk.Text(outer, height=8, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True)

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        ensure_inbox_layout(Path(self.workspace.get()))
        self.refresh()
        self.root.after(150, self.poll_events)

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
                        self.messagebox.showinfo("اكتملت العملية", "تم الاستيراد والتنظيم بنجاح.")
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
