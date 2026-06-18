import argparse
import re
import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


TARGET_SECTOR = "0x00070000"
TARGET_FA_SIZE = "BSP_PARTITION___BL_0_S_H_SIZE + BSP_PARTITION___BL_0_S_I_SIZE"


def patch_bsp_linker_info(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"找不到檔案: {path}"

    text = path.read_text(encoding="utf-8")
    original = text

    text, sector_count = re.subn(
        r"#define RM_MCUBOOT_LARGEST_SECTOR 0x[0-9A-Fa-f]+",
        f"#define RM_MCUBOOT_LARGEST_SECTOR {TARGET_SECTOR}",
        text,
        count=1,
    )

    text, fa_count = re.subn(
        r"\.fa_size\s*=\s*BSP_PARTITION___BL_0_S_H_SIZE\s*\+\s*BSP_PARTITION___BL_0_S_I_SIZE(?:\s*\+\s*BSP_PARTITION_FLASH_CPU0_C_SIZE)?\s*,",
        f".fa_size      = {TARGET_FA_SIZE},",
        text,
        count=1,
    )

    if sector_count == 0:
        return False, f"未找到 RM_MCUBOOT_LARGEST_SECTOR: {path}"
    if fa_count == 0:
        return False, f"未找到 FLASH_AREA_0S fa_size: {path}"

    if text != original:
        path.write_text(text, encoding="utf-8")
        return True, f"已修正: {path}"
    return True, f"已是正確值: {path}"


def run_patch(paths: list[Path]) -> tuple[bool, list[str]]:
    messages = []
    ok = True
    for path in paths:
        success, msg = patch_bsp_linker_info(path)
        messages.append(msg)
        ok = ok and success
    return ok, messages


def build_default_targets(root_dir: Path) -> list[Path]:
    return [
        root_dir / "sleep_mcu_cnn_0416_init" / "cnn_mcu_v3" / "cnn_ota_bl" / "Debug" / "bsp_linker_info.h",
        root_dir
        / "sleep_mcu_cnn_0416_init"
        / "cnn_mcu_v3"
        / "mcu_cnn"
        / "sil_ultra_slow_jogging - 20260109-Ver01.006"
        / "Debug"
        / "bsp_linker_info.h",
    ]


class FlashmapFixerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("TinyOL Flashmap Fixer")
        self.root.geometry("920x470")

        self.root_var = tk.StringVar()
        self.file_vars = [tk.StringVar(), tk.StringVar()]
        self.log_var = tk.StringVar(value="請選擇或確認兩個 bsp_linker_info.h 路徑。")

        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="專案資料夾").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(frame, textvariable=self.root_var, width=95).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(frame, text="Browse...", command=self.pick_root).grid(row=0, column=2)
        ttk.Button(frame, text="帶入預設檔案", command=self.fill_from_root).grid(row=0, column=3, padx=(8, 0))

        ttk.Label(frame, text="BL bsp_linker_info.h").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(frame, textvariable=self.file_vars[0], width=95).grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Button(frame, text="Browse...", command=lambda: self.pick_file(0)).grid(row=1, column=2)

        ttk.Label(frame, text="APP bsp_linker_info.h").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Entry(frame, textvariable=self.file_vars[1], width=95).grid(row=2, column=1, sticky="ew", padx=8)
        ttk.Button(frame, text="Browse...", command=lambda: self.pick_file(1)).grid(row=2, column=2)

        ttk.Button(frame, text="套用修正", command=self.apply_fix).grid(row=3, column=1, sticky="w", pady=12)

        ttk.Label(frame, text="修正內容").grid(row=4, column=0, sticky="nw", pady=(10, 4))
        summary = tk.Text(frame, height=6, width=100)
        summary.grid(row=4, column=1, columnspan=3, sticky="nsew")
        summary.insert(
            "1.0",
            "1. 可先選 RESTCN 專案資料夾，再按「帶入預設檔案」\n"
            "2. 將 RM_MCUBOOT_LARGEST_SECTOR 強制改成 0x00070000\n"
            "3. 將 FLASH_AREA_0S.fa_size 強制改成 header + slot2 payload\n"
            "4. 避免 FSP re-gen 後再次把 FLASH_CPU0_C 併進 secondary slot\n",
        )
        summary.configure(state="disabled")

        ttk.Label(frame, text="結果").grid(row=5, column=0, sticky="nw", pady=(10, 4))
        self.log_text = tk.Text(frame, height=8, width=100)
        self.log_text.grid(row=5, column=1, columnspan=3, sticky="nsew")
        self.log_text.insert("1.0", self.log_var.get())
        self.log_text.configure(state="disabled")

        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)

    def pick_root(self):
        path = filedialog.askdirectory(title="選擇 RESTCN 專案資料夾")
        if path:
            self.root_var.set(path)

    def fill_from_root(self):
        root_text = self.root_var.get().strip()
        if not root_text:
            messagebox.showwarning("TinyOL Flashmap Fixer", "請先選擇專案資料夾。")
            return

        targets = build_default_targets(Path(root_text))
        self.file_vars[0].set(str(targets[0]))
        self.file_vars[1].set(str(targets[1]))

    def pick_file(self, index: int):
        path = filedialog.askopenfilename(
            title="選擇 bsp_linker_info.h",
            filetypes=[("Header Files", "*.h"), ("All Files", "*.*")],
        )
        if path:
            self.file_vars[index].set(path)

    def set_log(self, messages: list[str]):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("1.0", "\n".join(messages))
        self.log_text.configure(state="disabled")

    def apply_fix(self):
        paths = [Path(var.get().strip()) for var in self.file_vars if var.get().strip()]
        if len(paths) != 2:
            messagebox.showwarning("TinyOL Flashmap Fixer", "請先選擇兩個 bsp_linker_info.h。")
            return

        ok, messages = run_patch(paths)
        self.set_log(messages)
        if ok:
            messagebox.showinfo("TinyOL Flashmap Fixer", "修正完成。")
        else:
            messagebox.showerror("TinyOL Flashmap Fixer", "部分修正失敗，請看結果視窗。")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fix TinyOL flashmap after FSP re-gen.")
    parser.add_argument(
        "--file",
        dest="files",
        action="append",
        help="指定要修正的 bsp_linker_info.h，可重複帶兩次。",
    )
    parser.add_argument(
        "--root",
        dest="root",
        help="指定 RESTCN repo 根目錄，自動帶出兩個預設檔案。",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="只跑命令列模式，不開 GUI。",
    )
    return parser.parse_args()


def run_cli(args: argparse.Namespace) -> int:
    paths: list[Path] = []
    if args.files:
        paths = [Path(item) for item in args.files]
    elif args.root:
        paths = build_default_targets(Path(args.root))

    if len(paths) != 2:
        print("請提供兩個 --file，或提供一個 --root。", file=sys.stderr)
        return 1

    ok, messages = run_patch(paths)
    for msg in messages:
        print(msg)
    return 0 if ok else 1


def run_gui(default_paths: list[Path] | None = None):
    root = tk.Tk()
    app = FlashmapFixerApp(root)
    if default_paths and len(default_paths) == 2:
        app.root_var.set(str(default_paths[0].parents[4]))
        app.file_vars[0].set(str(default_paths[0]))
        app.file_vars[1].set(str(default_paths[1]))
    root.mainloop()


def main():
    args = parse_args()
    default_paths = build_default_targets(Path(args.root)) if args.root else None

    if args.no_gui:
        raise SystemExit(run_cli(args))

    run_gui(default_paths)


if __name__ == "__main__":
    main()
