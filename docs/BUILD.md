# Building and releasing

Everything in this document runs on GitHub's runners. A local Windows
toolchain is optional — that is deliberate, since the point of the CI setup is
that a contributor on any machine can produce a shippable `.exe`.

## What gets built

| Artefact | Spec | Subsystem | Contents |
| --- | --- | --- | --- |
| `BoseCtl.exe` | `build/BoseCtl.spec` | windowed | the GUI, tkinter, customtkinter, theme assets, icon |
| `bosectl.exe` | `build/bosectl.spec` | console | the CLI only — tkinter and Pillow are excluded |

Both are **one-file**: a single portable `.exe` with no install step, at the
cost of a 2-3 s first-launch unpack. If you would rather have an instant start,
build the GUI as a directory instead by moving `a.binaries` / `a.datas` from the
`EXE(...)` call into a `COLLECT(...)` block; the result starts in well under a
second.

## Triggering a build

### First publish

The workflows do nothing until the repository exists on GitHub. One command
handles it:

```bash
python scripts/publish.py            # create (private) + push, then show the URL
python scripts/publish.py --public   # public instead of private
python scripts/publish.py --check    # report the git state, change nothing
```

With the [`gh` CLI](https://cli.github.com) installed and authenticated it
creates the repository and pushes; without it, it prints the two manual steps
(create on github.com, then `git push -u origin main`). It never
force-pushes.

The push itself is what starts CI — GitHub runs the workflows for commits
created through the API too, so there is nothing to kick off by hand.

### On GitHub (the normal path)

| Workflow | When | Result |
| --- | --- | --- |
| `ci.yml` | every push and PR | version check, full test suite (Windows 3.9/3.11/3.13, Linux, macOS), GUI smoke test, ruff |
| `build.yml` | every push and PR, or manual | both executables, smoke-tested, uploaded as workflow artifacts |
| `release.yml` | a `v*` tag is pushed, or manual with a tag | validated, built, verified, published as a GitHub Release |

To produce a downloadable build without releasing: **Actions → Build Windows
executables → Run workflow**. The artifacts appear on the run page.

To release:

```bash
# 1. Bump the version in all three files, then verify:
#      pyproject.toml, pybmap/__init__.py, build/version_info.py
python scripts/check_version.py

# 2. Add a "## [x.y.z]" section to CHANGELOG.md — release.yml uses it as the
#    release body.

# 3. Commit, tag, push.
git commit -am "Release v1.1.0"
git tag v1.1.0
git push origin main --tags
```

The validate job runs `scripts/check_version.py v1.1.0` first and fails the
whole run if the tag disagrees with the source. That is intentional: a release
whose asset reports a different version than its title is worse than no
release.

### Locally (optional)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt

python build/make_icon.py                   # regenerate build/icon.ico
pyinstaller --clean --noconfirm build/BoseCtl.spec
pyinstaller --clean --noconfirm build/bosectl.spec

dist\BoseCtl.exe --demo
dist\bosectl.exe --mock status
```

Requirements: Windows, Python 3.9+, and a Python that includes `tkinter` (the
python.org installer does; some minimal distributions do not — the CLI build
works regardless).

## What the pipelines actually verify

Packaging that only compiles is not packaging that works. The build workflow
asserts, on a real Windows runner:

1. **Both executables exist** and their sizes are reported.
2. **The console build runs** — `--version`, `--help`, `--mock status`,
   `--mock battery`, `--mock cnc 8`, `--mock quiet`, `--mock eq 3 0 -2`, each
   with exit code 0, and the status output must contain a battery line.
3. **The windowed build survives launch** — `BoseCtl.exe --demo` is started,
   left for 20 seconds, and must still be running. This catches the whole class
   of "works from source, crashes frozen" bugs: missing customtkinter theme
   JSON, a missing icon, a Tcl path problem.
4. **Checksums match** — `SHA256SUMS` is re-verified in a separate job.
5. **The version resource is present and correct** — `bosectl.exe`'s
   `FileVersion` must start with `pybmap.__version__`.
6. **`BoseCtl.exe` is genuinely windowed** — the PE subsystem field is read
   directly out of the header and must be `IMAGE_SUBSYSTEM_WINDOWS_GUI` (2).
   A console subsystem here means every double-click flashes a black box.

The GUI itself is additionally covered by `tests/test_gui_smoke.py`, which runs
on every push: it creates the real window, connects to the in-memory mock
device, visits all six pages, toggles the appearance twice, checks the status
tiles populated, and round-trips `set_cnc(7)` → `cnc()`.

## Packaging notes

**Why a version resource.** Without it, Windows shows no version in the file
properties dialog and `Get-FileHash`-based release verification has nothing to
check against. `build/version_info.py` is the single source for the resource and
`scripts/check_version.py` keeps it in step with the library.

**Why UPX is off.** UPX reliably trips a handful of antivirus heuristics, and
the size saving is not worth an unsigned binary that half the users cannot
launch.

**Why two executables instead of one.** Windows fixes the console/windowed
subsystem at link time. A single binary would either flash a console for GUI
users or swallow the CLI's output. Each also benefits from excluding the other's
dependencies: the CLI build drops tkinter, customtkinter, darkdetect and Pillow,
which cuts it to a couple of megabytes.

**Why the icon is generated in CI.** `build/make_icon.py` rasterises at
1024 px and downsamples with LANCZOS, which produces cleaner small-size edges
than a hand-placed glyph. `build/icon.ico` and `build/icon.png` are therefore
build artefacts and are not committed — both packaging jobs run the generator
first. That also means the released icon can never be a stale `.ico` that no
longer matches the script. (Pillow's ICO writer needs the sizes passed via
`sizes=`; handing it frames through `append_images`, the GIF idiom, silently
produces a single 16 px image. `tests/test_version.py` pins the frame list.)

**Code signing.** The executables are unsigned, so SmartScreen warns on first
run. If you fork this and want signed builds, add a signing step after
`pyinstaller` using `signtool` and a certificate secret; nothing else needs to
change.

## Troubleshooting CI

| Symptom | Cause |
| --- | --- |
| `check_version.py` fails | A version was bumped in one place only. Run it locally for the exact mismatch. |
| `ModuleNotFoundError: tkinter` | The runner's Python lacks tkinter. `actions/setup-python` includes it; a custom interpreter may not. |
| GUI smoke test skips | Tk could not initialise. Expected on headless runners; the job still passes, but watch for it becoming the norm — it would mean the GUI is no longer exercised. |
| `BoseCtl.exe exited during startup` | Usually a missing data file. Check that `collect_data_files("customtkinter")` still resolves and that `build/icon.ico` is present. |
| Release fails on "tag does not match" | Tag it after bumping the three version locations, not before. |
| `verify` job: checksum mismatch | The `.sha256` file was written with a different format. It must be `<hash>  <name>` on one line. |
