"""Version consistency across every place a version number is written.

A release that says 1.0.0 on GitHub but 0.9.0 in the file properties dialog
is the kind of bug nobody notices until a user reports one. This test is the
fast local equivalent of ``scripts/check_version.py``.
"""

import os
import re
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
    "build/BoseCtl.spec", "build/bosectl.spec", "build/entry_gui.py",
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
