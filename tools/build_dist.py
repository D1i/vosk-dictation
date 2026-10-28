#!/usr/bin/env python3
"""Сборка переносимой версии (zip) и установщика (setup.exe) Vosk Dictation.

Сборка не зависит от ОС (Linux или Windows), нужны:
  * встраиваемый Python для Windows — build/python-3.12.10-embed-amd64.zip
    (скачивается tools/fetch_python.bat);
  * пакеты для Windows: .venv/Lib/site-packages (после install.bat)
    или --uv (кросс-установка через uv);
  * модель models/vosk-model-small-ru-0.22 (после install.bat);
  * NSIS 3 (makensis) — путь через --makensis или переменную MAKENSIS.

Пример (Linux):
  NSISDIR=~/nsis/usr/share/nsis python3 tools/build_dist.py --makensis ~/nsis/usr/bin/makensis

Результат в dist/:
  VoskDictation-<версия>-setup.exe     установщик (для текущего пользователя, без админа)
  VoskDictation-<версия>-portable.zip  переносимая версия
  SHA256SUMS.txt
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = "1.0.0"
APP_FOLDER = "Vosk Dictation"
MODEL = "vosk-model-small-ru-0.22"
PY_VERSION = "3.12.10"

# что не берём из site-packages (верхний уровень)
SITE_SKIP_TOP = ("pip", "pip-*", "setuptools", "setuptools-*", "pkg_resources", "_distutils_hack",
                 "distutils-precedence.pth", "wheel", "wheel-*", "bin", "Scripts", "__pycache__",
                 "*.virtualenv", "_virtualenv.*")
SKIP_ANY = ("__pycache__", "*.pyc", "*.pyo")

PTH_TEMPLATE = """{zip_name}
.
Lib\\site-packages
..\\app

# Vosk Dictation: site-packages and the app folder are listed above
import site
"""


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def matches(name: str, patterns) -> bool:
    import fnmatch
    return any(fnmatch.fnmatchcase(name.lower(), p.lower()) for p in patterns)


def copytree(src: Path, dst: Path, skip_top=(), skip_any=SKIP_ANY) -> int:
    count = 0
    for dirpath, dirnames, filenames in os.walk(src):
        rel = Path(dirpath).relative_to(src)
        top = rel == Path(".")
        dirnames[:] = sorted(d for d in dirnames
                             if not matches(d, skip_any) and not (top and matches(d, skip_top)))
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for fn in sorted(filenames):
            if matches(fn, skip_any) or (top and matches(fn, skip_top)):
                continue
            shutil.copy2(Path(dirpath) / fn, dst / rel / fn)
            count += 1
    return count


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def human(n: float) -> str:
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} ТБ"


def dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


# --------------------------------------------------------------------- stage
def stage_python(zip_path: Path, dst: Path) -> str:
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dst)
    pths = sorted(dst.glob("python3*._pth"))
    if len(pths) != 1 or not (dst / "pythonw.exe").exists():
        raise SystemExit(f"{zip_path.name}: не похоже на встраиваемый Python для Windows")
    tag = pths[0].stem                      # python312
    text = PTH_TEMPLATE.format(zip_name=f"{tag}.zip").replace("\n", "\r\n")
    pths[0].write_bytes(text.encode("utf-8"))
    return tag


def stage_site_packages_copy(src: Path, dst: Path, tag: str) -> None:
    if not src.is_dir():
        raise SystemExit(f"нет папки с пакетами: {src}")
    abi = "cp" + tag.replace("python", "")
    if not list(src.glob(f"*{abi}-win_amd64.pyd")):
        raise SystemExit(f"{src}: пакеты не для {abi}-win_amd64 (нужна та же версия Python, что и встраиваемая)")
    n = copytree(src, dst, skip_top=SITE_SKIP_TOP)
    log(f"site-packages: скопировано {n} файлов из {src}")


def stage_site_packages_uv(dst: Path, tag: str) -> None:
    uv = shutil.which("uv")
    if not uv:
        raise SystemExit("uv не найден (pip install uv)")
    ver = tag.replace("python", "")
    pyver = f"{ver[0]}.{ver[1:]}"
    cmd = [uv, "pip", "install", "--target", str(dst), "--python-platform", "x86_64-pc-windows-msvc",
           "--python-version", pyver, "--no-compile", "-r", str(ROOT / "requirements.txt")]
    log("uv: " + " ".join(cmd))
    subprocess.run(cmd, check=True)
    for name in os.listdir(dst):
        if matches(name, SITE_SKIP_TOP):
            p = dst / name
            shutil.rmtree(p) if p.is_dir() else p.unlink()


def build_stage(args, stage: Path) -> None:
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    tag = stage_python(args.python_zip, stage / "python")
    log(f"Python: {args.python_zip.name} ({tag})")
    site = stage / "python" / "Lib" / "site-packages"
    site.mkdir(parents=True)
    if args.uv:
        stage_site_packages_uv(site, tag)
    else:
        stage_site_packages_copy(args.site_packages, site, tag)

    n = copytree(ROOT / "app", stage / "app")
    log(f"app: {n} файлов")
    model = args.model
    if not (model / "am" / "final.mdl").is_file():
        raise SystemExit(f"модель не найдена: {model}")
    n = copytree(model, stage / "models" / MODEL)
    log(f"модель: {n} файлов, {human(dir_size(stage / 'models'))}")
    (stage / "tests").mkdir()
    shutil.copy2(ROOT / "tests" / "test_ru.wav", stage / "tests" / "test_ru.wav")
    for name in ("README.txt", "diagnose.bat"):
        shutil.copy2(ROOT / "packaging" / "dist" / name, stage / name)


def run_makensis(makensis: str, script: Path, defines: dict) -> None:
    cmd = [makensis, "-V2", "-INPUTCHARSET", "UTF8"]
    cmd += [f"-D{k}={v}" for k, v in defines.items()]
    cmd.append(str(script))
    log("makensis: " + script.name)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-4000:])
        print(r.stderr[-4000:])
        raise SystemExit(f"makensis завершился с кодом {r.returncode}")
    warnings = [line for line in r.stdout.splitlines() if "warning" in line.lower()]
    for w in warnings[:20]:
        log("  " + w.strip())


def build_zip(stage: Path, out: Path) -> None:
    tmp = out.with_suffix(".zip.part")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dirpath, dirnames, filenames in os.walk(stage):
            dirnames.sort()
            rel = Path(dirpath).relative_to(stage)
            for fn in sorted(filenames):
                p = Path(dirpath) / fn
                arc = (Path(APP_FOLDER) / rel / fn).as_posix()
                z.write(p, arc)
    with zipfile.ZipFile(tmp) as z:
        bad = z.testzip()
        if bad:
            raise SystemExit(f"архив повреждён: {bad}")
    tmp.replace(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Сборка установщика и переносимой версии")
    ap.add_argument("--python-zip", type=Path,
                    default=ROOT / "build" / f"python-{PY_VERSION}-embed-amd64.zip")
    ap.add_argument("--site-packages", type=Path, default=ROOT / ".venv" / "Lib" / "site-packages")
    ap.add_argument("--uv", action="store_true", help="поставить пакеты через uv вместо копирования")
    ap.add_argument("--model", type=Path, default=ROOT / "models" / MODEL)
    ap.add_argument("--makensis", default=os.environ.get("MAKENSIS") or shutil.which("makensis"))
    ap.add_argument("--work", type=Path, default=Path(tempfile.gettempdir()) / "vosk-dictation-build",
                    help="временная папка сборки")
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    ap.add_argument("--version", default=VERSION)
    ap.add_argument("--skip-zip", action="store_true")
    ap.add_argument("--skip-installer", action="store_true")
    ap.add_argument("--stage-only", action="store_true",
                    help="только собрать папку программы (для сборки по шагам)")
    ap.add_argument("--reuse-stage", action="store_true",
                    help="взять готовую папку программы из прошлого запуска --stage-only")
    args = ap.parse_args()

    if not args.python_zip.is_file():
        raise SystemExit(f"нет {args.python_zip} — запустите tools/fetch_python.bat")
    if not args.makensis:
        raise SystemExit("не найден makensis (NSIS 3): укажите --makensis")

    t0 = time.monotonic()
    stage = args.work / APP_FOLDER
    marker = args.work / ".stage-complete"
    if args.reuse_stage:
        if not marker.is_file():
            raise SystemExit(f"нет готовой папки программы в {args.work} — сначала --stage-only")
        log(f"беру готовую папку программы: {stage}")
    else:
        if marker.exists():
            marker.unlink()
        build_stage(args, stage)
        launcher = stage / f"{APP_FOLDER}.exe"
        run_makensis(args.makensis, ROOT / "packaging" / "launcher.nsi", {
            "OUTFILE": str(launcher), "ICON": str(stage / "app" / "assets" / "icon.ico"),
            "VERSION": args.version})
        marker.write_text(args.version, encoding="utf-8")
    log(f"папка программы: {human(dir_size(stage))}")
    if args.stage_only:
        log(f"готово за {time.monotonic() - t0:.0f} c")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    base = f"VoskDictation-{args.version}"
    outputs = []
    if not args.skip_zip:
        zip_path = args.out / f"{base}-portable.zip"
        log(f"архив: {zip_path.name}")
        build_zip(stage, zip_path)
        outputs.append(zip_path)
    if not args.skip_installer:
        exe_path = args.out / f"{base}-setup.exe"
        tmp_exe = args.work / exe_path.name
        size_mb = (dir_size(stage) + (1 << 20) - 1) >> 20
        run_makensis(args.makensis, ROOT / "packaging" / "installer.nsi", {
            "STAGE": str(stage), "OUTFILE": str(tmp_exe), "VERSION": args.version,
            "SIZE_MB": str(size_mb)})
        shutil.copyfile(tmp_exe, exe_path)
        outputs.append(exe_path)

    for p in outputs:
        log(f"{p.name}: {human(p.stat().st_size)}")
    # контрольные суммы всех готовых файлов в dist/
    sums = [f"{sha256(p)}  {p.name}" for p in sorted(args.out.glob(f"{base}-*"))
            if p.suffix in (".exe", ".zip")]
    if sums:
        (args.out / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
        for line in sums:
            log("sha256 " + line)
    log(f"готово за {time.monotonic() - t0:.0f} c")
    return 0


if __name__ == "__main__":
    sys.exit(main())
