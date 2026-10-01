#!/usr/bin/env python3
"""Publish this repository to GitHub, creating it if necessary.

A convenience wrapper around the two commands a first-time publish needs,
with the failure modes checked up front rather than discovered halfway
through. It never rewrites history and never force-pushes.

Usage::

    python scripts/publish.py                     # create + push, then show CI
    python scripts/publish.py --name my-fork
    python scripts/publish.py --public
    python scripts/publish.py --check             # report state, change nothing
    python scripts/publish.py --repo-url https://github.com/me/other.git

Requires the ``gh`` CLI (https://cli.github.com) for the create step. If it
is missing, the script prints the exact manual steps instead of failing: the
only thing ``gh`` saves you is clicking "New repository" once.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_NAME = "bosectl-win"
DEFAULT_OWNER = "liaoranqing"


def run(*args, capture=True, check=False):
    """Run a command in the repo root. Returns (code, stdout, stderr)."""
    result = subprocess.run(
        list(args), cwd=ROOT, text=True, check=False,
        capture_output=capture,
    )
    if check and result.returncode != 0:
        raise SystemExit("%s failed:\n%s" % (" ".join(args), result.stderr))
    return result.returncode, (result.stdout or ""), (result.stderr or "")


def have(command):
    code, _, _ = run(command, "--version")
    return code == 0


def git_state():
    """Return a dict describing the working tree."""
    code, out, _ = run("git", "rev-parse", "--is-inside-work-tree")
    if code != 0:
        raise SystemExit("Not a git repository. Run this from the project root.")

    _, branch, _ = run("git", "branch", "--show-current")
    _, dirty, _ = run("git", "status", "--porcelain")
    _, commits, _ = run("git", "rev-list", "--count", "HEAD")
    _, remote, _ = run("git", "remote", "get-url", "origin")

    return {
        "branch": branch.strip() or "(detached)",
        "dirty": [line for line in dirty.splitlines() if line.strip()],
        "commits": int(commits.strip() or 0),
        "remote": remote.strip(),
    }


def report(state, repo_url):
    print("仓库状态")
    print("  分支        %s" % state["branch"])
    print("  提交数      %d" % state["commits"])
    print("  未提交改动  %d" % len(state["dirty"]))
    print("  远程        %s" % (state["remote"] or repo_url))
    if state["dirty"]:
        print("\n未提交的改动：")
        for line in state["dirty"][:20]:
            print("  %s" % line)
        if len(state["dirty"]) > 20:
            print("  … 另有 %d 项" % (len(state["dirty"]) - 20))


def manual_steps(branch, owner="", name=DEFAULT_NAME):
    print("""
未找到 gh 命令行工具，请手动完成两步（约 20 秒）：

  1. 打开 https://github.com/new
       仓库名：%s
       可见性：按需选择
       不要勾选 "Add a README"（否则首次推送会冲突）

  2. 在项目目录执行：
       git push -u origin %s

推送后 GitHub Actions 会自动开始构建，几分钟后在
  https://github.com/%s/%s/actions
可以看到 CI、打包和产物。
""" % (name, branch, owner or "<你的账号>", name))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Create the GitHub repository if needed, then push.")
    parser.add_argument("--name", default=DEFAULT_NAME,
                        help="repository name (default: %s)" % DEFAULT_NAME)
    parser.add_argument("--owner", default=DEFAULT_OWNER,
                        help="account or organisation (default: %s)" % DEFAULT_OWNER)
    parser.add_argument("--public", action="store_true",
                        help="create a public repository (default: private)")
    parser.add_argument("--check", action="store_true",
                        help="report the state and exit without changing anything")
    parser.add_argument("--repo-url",
                        help="push to this URL instead of creating a repository")
    args = parser.parse_args(argv)

    repo_url = args.repo_url or "https://github.com/%s/%s.git" % (
        args.owner, args.name)
    state = git_state()
    report(state, repo_url)

    if args.check:
        return 0
    if state["commits"] == 0:
        raise SystemExit("Nothing to push: no commits yet.")
    if state["branch"] == "(detached)":
        raise SystemExit("HEAD is detached; check out a branch first.")

    if args.repo_url:
        if state["remote"] and state["remote"] != args.repo_url:
            run("git", "remote", "set-url", "origin", args.repo_url, check=True)
        elif not state["remote"]:
            run("git", "remote", "add", "origin", args.repo_url, check=True)
        head = ["git", "push", "-u", "origin", state["branch"]]
    elif have("gh"):
        code, _, err = run("gh", "auth", "status")
        if code != 0:
            print("\ngh 已安装但未登录。请先执行：gh auth login")
            manual_steps(state["branch"], args.owner, args.name)
            return 1
        visibility = "--public" if args.public else "--private"
        print("\n创建仓库并推送 …")
        code, out, err = run(
            "gh", "repo", "create",
            "%s/%s" % (args.owner, args.name) if args.owner else args.name,
            visibility, "--source=.", "--remote=origin",
            "--push", "--description",
            "Windows port of aaronsb/bosectl: control Bose headphones over "
            "BMAP, desktop GUI plus CLI, single-file EXE built on GitHub Actions.",
        )
        if code != 0:
            print((err or "").strip())
            print("\n创建失败。常见原因：仓库已存在（改用 git push 即可）、"
                  "或 gh 的授权范围不含该账号。")
            manual_steps(state["branch"], args.owner, args.name)
            return 1
        print(out.strip())
        print("\n推送完成。请到 Actions 页面查看构建：")
        print("  https://github.com/%s/%s/actions" % (args.owner, args.name))
        return 0
    else:
        # No gh, no explicit URL: make sure origin points where we intend
        # before pushing, so a fresh clone (which has no remote yet) does
        # not fail with "No configured push destination".
        if state["remote"] and state["remote"] != repo_url:
            run("git", "remote", "set-url", "origin", repo_url, check=True)
        elif not state["remote"]:
            run("git", "remote", "add", "origin", repo_url, check=True)
            print("\n已设置 origin → %s" % repo_url)
        head = ["git", "push", "-u", "origin", state["branch"]]

    print("\n执行：%s" % " ".join(head))
    code, out, err = run(*head, capture=False)
    if code != 0:
        print((err or "").strip())
        print("\n推送失败。若提示仓库不存在，请先在 https://github.com/new 创建，"
              "或在 https://github.com/settings/installations 给已连接的 "
              "GitHub App 授予仓库创建权限后重试。")
        manual_steps(state["branch"], args.owner, args.name)
        return 1
    print("\n推送成功。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
