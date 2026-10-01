"""Version consistency across every place a version number is written.

A release that says 1.0.0 on GitHub but 0.9.0 in the file properties dialog
is the kind of bug nobody notices until a user reports one. This test is the
fast local equivalent of ``scripts/check_version.py``.
"""

import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(relative):
    with open(os.path.join(ROOT, relative), encoding="utf-8") as handle:
        return handle.read()


def _components(text):
    return tuple(int(part) for part in re.findall(r"\d+", text)[:3])


def test_pyproject_version_matches_library():
    import pybmap
    project = _read("pyproject.toml").split("[project]", 1)[1].split("\n[", 1)[0]
    declared = re.search(r'^\s*version\s*=\s*"([^"]+)"', project, re.M).group(1)
    assert _components(declared) == _components(pybmap.__version__)


def test_windows_resource_version_matches_library():
    import pybmap
    declared = re.search(r'^VERSION\s*=\s*"([^"]+)"',
                         _read("build/version_info.py"), re.M).group(1)
    assert _components(declared) == _components(pybmap.__version__)


def test_upstream_version_is_recorded():
    import pybmap
    assert re.fullmatch(r"\d+\.\d+\.\d+", pybmap.UPSTREAM_VERSION)


def test_check_version_script_passes():
    """The CI gate itself must be green on a clean checkout."""
    import subprocess
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "check_version.py")],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_version_script_rejects_a_bad_tag():
    import subprocess
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "check_version.py"),
         "v99.0.0"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 1
    assert "99.0.0" in result.stderr


@pytest.mark.parametrize("relative", [
    "LICENSE", "NOTICE", "README.md", "requirements.txt",
    "requirements-dev.txt", ".gitignore", ".gitattributes",
    "pyproject.toml", "cli.py", "bosectl.py",
])
def test_repository_essentials_exist(relative):
    assert os.path.isfile(os.path.join(ROOT, relative)), relative


@pytest.mark.parametrize("relative", [
    "build/BoseCtl-window.spec", "build/bosectl-console.spec", "build/entry_gui.py",
    "build/entry_cli.py", "build/make_icon.py",
    "build/version_info.py",
    ".github/workflows/ci.yml", ".github/workflows/build.yml",
    ".github/workflows/release.yml",
    "docs/ARCHITECTURE.md", "docs/BUILD.md", "docs/USAGE.md",
    "docs/WINDOWS-PORT.md",
])
def test_packaging_and_docs_exist(relative):
    assert os.path.isfile(os.path.join(ROOT, relative)), relative


def test_icon_generator_produces_a_multi_resolution_ico(tmp_path):
    """The .ico is a build artefact, so what matters is that it generates.

    Pillow's ICO writer emits a single 16 px frame if you pass frames via
    ``append_images`` (the GIF idiom) instead of relying on ``sizes``. The
    file still opens and still looks fine to a casual check, so this asserts
    the frame list rather than mere existence.
    """
    pytest.importorskip("PIL", reason="Pillow is a build-time dependency")

    # Run the generator against a temporary directory so the working tree is
    # not touched, then check every advertised size is really present.
    script = os.path.join(ROOT, "build", "make_icon.py")
    source = open(script, encoding="utf-8").read()
    source = source.replace(
        'OUT_DIR = os.path.dirname(os.path.abspath(__file__))',
        'OUT_DIR = %r' % str(tmp_path))

    namespace = {"__name__": "make_icon_test", "__file__": script}
    exec(compile(source, script, "exec"), namespace)
    namespace["main"]()

    from PIL import Image
    ico = tmp_path / "icon.ico"
    assert ico.is_file()
    with Image.open(ico) as image:
        sizes = sorted(image.info.get("sizes", []))
    assert (16, 16) in sizes
    assert (256, 256) in sizes
    assert len(sizes) >= 5, sizes
    assert (tmp_path / "icon.png").is_file()


# ── repository layout ────────────────────────────────────────────────────────

def _tracked_paths():
    """Every path git knows about, or None when git is unavailable."""
    try:
        result = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return [line for line in result.stdout.splitlines() if line.strip()]


def test_no_tracked_paths_collide_by_letter_case():
    """Guards the worst kind of cross-platform trap in a Windows-first repo.

    Windows and macOS filesystems are case-insensitive, so two tracked paths
    that differ only in case are *one file* there. Git stores one of them and
    silently drops the other, so the checkout is missing a file that Linux —
    where the paths really are distinct — then cannot find.

    That is exactly how this repository once shipped a broken build: the two
    PyInstaller specs were named ``BoseCtl.spec`` and ``bosectl.spec``, so
    Windows saw a single file. Both packaging jobs ran the same spec, and the
    library test suite failed only on ubuntu-latest.

    Note that walking the working tree cannot detect this — on a
    case-insensitive filesystem only one of the two files is visible at all.
    The git index is the only place the collision exists, so it is what this
    asserts on.
    """
    tracked = _tracked_paths()
    if tracked is None:
        pytest.skip("git is not available")

    seen = {}
    collisions = {}
    for path in tracked:
        key = path.lower()
        if key in seen:
            collisions.setdefault(key, [seen[key]]).append(path)
        else:
            seen[key] = path

    assert not collisions, (
        "these paths differ only by letter case, so whichever loses is missing "
        "from every Windows and macOS checkout: %r" % collisions)


def test_build_specs_have_distinct_names():
    """A narrower, louder version of the check above for the two build specs.

    Spelled out separately because these two files are the ones the release
    pipeline depends on, and because the failure mode is silent.
    """
    names = [name for name in os.listdir(os.path.join(ROOT, "build"))
             if name.endswith(".spec")]
    lowered = [name.lower() for name in names]
    assert len(set(lowered)) == len(lowered), (
        "build/*.spec names collide on a case-insensitive filesystem: %r" % names)
    assert len(names) >= 2, names


@pytest.mark.parametrize("spec", [
    "build/BoseCtl-window.spec",
    "build/bosectl-console.spec",
])
def test_build_specs_are_valid_python(spec):
    """PyInstaller specs are Python, but nothing else ever compiles them.

    ``compileall`` only looks at ``.py`` files and nothing imports a spec, so a
    syntax error in one survives every local check and only appears when the
    packaging job runs — which, for a tagged release, is after the tag exists.

    The specs also carry the one setting that cannot be tested by running the
    build locally on this machine: whether the binary is windowed or console.
    """
    source = open(os.path.join(ROOT, spec), encoding="utf-8").read()
    compile(source, spec, "exec")          # raises SyntaxError on corruption


def test_windowed_spec_is_windowed_and_console_spec_is_console():
    """Swapping the two spec bodies would produce an EXE that flashes a console.

    The two specs are near-identical apart from this, so an easy mistake is to
    paste one over the other. Both the entry script and the subsystem are
    checked.
    """
    gui = open(os.path.join(ROOT, "build", "BoseCtl-window.spec"),
               encoding="utf-8").read()
    cli = open(os.path.join(ROOT, "build", "bosectl-console.spec"),
               encoding="utf-8").read()

    assert 'entry_gui.py' in gui and 'entry_gui' not in cli
    assert 'entry_cli.py' in cli and 'entry_cli' not in gui
    assert 'console=False' in gui.replace(" ", "")
    assert 'console=True' in cli.replace(" ", "")

    # The GUI has to bundle customtkinter's theme assets; the CLI must not,
    # or it would carry tkinter and Pillow along with it. (Matching on the
    # excludes list rather than on the word, which the docstrings also use.)
    assert "collect_data_files" in gui
    assert "collect_data_files" not in cli
    assert '"customtkinter"' in cli
    assert "excludes = [" in cli


# ── build outputs must be distinguishable on a case-insensitive filesystem ───

def _spec_executables():
    """Map each build spec to the .exe name it will produce."""
    build_dir = os.path.join(ROOT, "build")
    produced = {}
    for filename in sorted(os.listdir(build_dir)):
        if not filename.endswith(".spec"):
            continue
        source = open(os.path.join(build_dir, filename), encoding="utf-8").read()
        match = re.search(r'^\s*name="([^"]+)"', source, re.M)
        if match:
            produced[filename] = match.group(1) + ".exe"
    return produced


def _workflow_source(name):
    path = os.path.join(ROOT, ".github", "workflows", name)
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_build_outputs_do_not_collide_by_letter_case():
    """The two .exe names must differ by more than letter case.

    ``BoseCtl.exe`` and ``bosectl.exe`` lower-case to the same string, so on
    Windows and macOS they are one file. Downloading both from a Release into
    one folder — or merging both CI artefacts into one directory, as the
    verify job does — silently overwrites one with the other. That is what
    broke the checksum step, and it would have hit users identically.
    """
    produced = _spec_executables()
    assert len(produced) >= 2, produced
    lowered = [value.lower() for value in produced.values()]
    assert len(set(lowered)) == len(lowered), (
        "these build outputs collide on a case-insensitive filesystem, so one "
        "will silently overwrite the other: %r" % produced)


@pytest.mark.parametrize("workflow", ["build.yml", "release.yml"])
def test_workflow_artifact_names_do_not_collide_by_letter_case(workflow):
    names = re.findall(r"^\s*artifact:\s*(\S+)", _workflow_source(workflow), re.M)
    lowered = [name.lower() for name in names]
    assert len(set(lowered)) == len(lowered), (workflow, names)


@pytest.mark.parametrize("workflow", ["build.yml", "release.yml"])
def test_workflows_only_reference_artefacts_the_specs_build(workflow):
    """A rename that misses one workflow step should fail here, not in CI.

    These paths are spelled out in a dozen places across two workflows; the
    only thing that keeps them honest is an assertion that every
    ``dist/<name>.exe`` mentioned actually comes out of a spec.
    """
    produced = set(_spec_executables().values())
    referenced = set(re.findall(r"dist/([A-Za-z0-9_.-]+\.exe)",
                                _workflow_source(workflow)))
    assert referenced, workflow
    assert referenced <= produced, (
        "%s references executables no spec builds: %r"
        % (workflow, sorted(referenced - produced)))
