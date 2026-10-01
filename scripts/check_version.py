#!/usr/bin/env python3
"""Fail when the four places a version number lives disagree.

The version appears in:

* ``pyproject.toml``      — what the package metadata says
* ``pybmap/__init__.py``  — what the library and About page report
* ``build/version_info.py`` — what Windows shows in file properties
* the git tag             — what the release is called

A mismatch is invisible until someone files a bug against "1.0.0" and the
binary reports something else. CI runs this on every push, and
``tests/test_version.py`` asserts the same thing so a local ``pytest`` run
catches it before the push.

Usage::

    python scripts/check_version.py            # compare the three files
    python scripts/check_version.py v1.2.3     # also compare a release tag
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(path):
    with open(os.path.join(ROOT, path), "r", encoding="utf-8") as handle:
        return handle.read()


def pyproject_version():
    text = _read("pyproject.toml")
    # Only the [project] table: the same key can appear under [tool.*].
    project = text.split("[project]", 1)[1].split("\n[", 1)[0]
    match = re.search(r'^\s*version\s*=\s*"([^"]+)"', project, re.M)
    if not match:
        raise SystemExit("pyproject.toml: no version under [project]")
    return match.group(1)


def library_version():
    match = re.search(r'^__version__\s*=\s*"([^"]+)"',
                      _read("pybmap/__init__.py"), re.M)
    if not match:
        raise SystemExit("pybmap/__init__.py: no __version__")
    return match.group(1)


def upstream_version():
    match = re.search(r'^UPSTREAM_VERSION\s*=\s*"([^"]+)"',
                      _read("pybmap/__init__.py"), re.M)
    return match.group(1) if match else "(missing)"


def resource_version():
    match = re.search(r'^VERSION\s*=\s*"([^"]+)"',
                      _read("build/version_info.py"), re.M)
    if not match:
        raise SystemExit("build/version_info.py: no VERSION")
    return match.group(1)


def _normalise(value):
    """Return the first three numeric components of a version string."""
    parts = re.findall(r"\d+", value)
    return tuple(int(p) for p in (parts + ["0", "0", "0"])[:3])


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    project = pyproject_version()
    library = library_version()
    resource = resource_version()

    print("pyproject.toml          %s" % project)
    print("pybmap.__version__      %s" % library)
    print("build/version_info.py   %s" % resource)
    print("pybmap.UPSTREAM_VERSION %s" % upstream_version())

    problems = []
    if _normalise(project) != _normalise(library):
        problems.append("pyproject.toml (%s) != pybmap.__version__ (%s)"
                        % (project, library))
    if _normalise(project) != _normalise(resource):
        problems.append("pyproject.toml (%s) != build/version_info.py (%s)"
                        % (project, resource))

    if argv:
        tag = argv[0].lstrip("vV")
        print("release tag             %s" % argv[0])
        if _normalise(tag) != _normalise(project):
            problems.append("tag %s != project version %s" % (argv[0], project))

    if problems:
        print("\nVersion mismatch:", file=sys.stderr)
        for problem in problems:
            print("  - %s" % problem, file=sys.stderr)
        print("\nUpdate every location above before releasing.", file=sys.stderr)
        return 1

    print("\nOK: all version numbers agree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
