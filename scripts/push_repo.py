#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""push_repo.py — GitHub推送执行器（git push + fine-grained PAT）

为什么独立成模块：publish_to_github.py 负责「产出→暂存→manifest」，
本模块负责「manifest → 远端」。两者解耦后，定时任务即使推送失败也
不会污染产出链路，且推送逻辑可单独 dry-run 验证。

推送机制（关键安全点）：
  · 令牌存于 ~/.config/gh-ip/token（权限 600），**永不进入命令行参数、
    remote URL、.git/config 或任何日志**。
  · 认证通过 `git -c http.https://github.com/.extraheader="Authorization: Basic ..."`
    单次注入，只对该次命令生效。
  · 远端 URL 始终保持 `https://github.com/<owner>/<repo>.git` 无凭证形态。
  · GIT_ASKPASS 在非交互 shell 下不会被 git 触发（实测 macOS git 2.50），
    故不采用。

幂等性：使用 `git commit --allow-empty` 前先检测工作区是否有变化；
内容一致则跳过提交，返回 0（不产生空提交噪声）。
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path

TOKEN_FILE = Path(os.environ.get("GH_IP_TOKEN_FILE",
                                 Path.home() / ".config/gh-ip/token"))
# 本地工作副本（与 _stage 分离，避免把构建产物当git 仓库）
WORK_ROOT = Path("/Users/lianghaizhen/WorkBuddy/2026-10-14-10-29-45"
                  "/github-ip-plan/_git_pulse")
COMMIT_AUTHOR_NAME = "seaquake97"
COMMIT_AUTHOR_EMAIL = "seaquake97@users.noreply.github.com"


class PushError(RuntimeError):
    """推送失败（网络/认证/冲突）。"""


def read_token() -> str:
    """读取令牌；缺失或过短立即报错，绝不静默降级。"""
    if not TOKEN_FILE.exists():
        raise PushError(
            f"令牌文件不存在: {TOKEN_FILE}\n"
            f"  创建方式: mkdir -p {TOKEN_FILE.parent} && chmod 700 {TOKEN_FILE.parent}\n"
            f"            echo -n '<你的 fine-grained PAT>' > {TOKEN_FILE} && chmod 600 {TOKEN_FILE}")
    tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if len(tok) < 20:
        raise PushError(f"令牌内容异常（长度 {len(tok)}），请检查 {TOKEN_FILE}")
    return tok


def _auth_header(token: str) -> str:
    raw = f"x-access-token:{token}".encode("utf-8")
    return "Authorization: Basic " + base64.b64encode(raw).decode("ascii")


def _git(args: list[str], token: str | None = None, cwd: Path | None = None) -> str:
    """执行 git；token 非空时以 extraheader 方式单次注入认证。"""
    cmd = ["git", "-C", str(cwd or WORK_ROOT)]
    if token:
        cmd += ["-c", f"http.https://github.com/.extraheader={_auth_header(token)}"]
    cmd += args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise PushError((r.stderr or r.stdout).strip()[:600])
    return r.stdout


def verify_token(token: str, owner: str) -> str:
    """校验令牌身份与 owner 是否匹配，防止推到别人账号。"""
    import json
    import urllib.error
    import urllib.request
    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {token}",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "daily-decision-engine-publisher"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise PushError(f"令牌校验失败 HTTP {e.code}（令牌可能已过期或被撤销）")
    login = data.get("login", "")
    if login.lower() != owner.lower():
        raise PushError(f"令牌身份({login}) 与 --owner({owner}) 不符，拒绝推送")
    return login


def sync_stage(stage_docs: Path, dest_docs: Path) -> tuple[int, int]:
    """把 _stage/docs 同步到本地 git 工作副本的 docs/。

    返回 (新增或更新文件数, 删除文件数)。
    """
    if not stage_docs.is_dir():
        raise PushError(f"暂存目录不存在: {stage_docs}")
    added = removed = 0
    # 删除目标中源已不存在的文件（如某天被重跑清空）
    for p in sorted(dest_docs.rglob("*"), reverse=True):
        if p.is_file():
            rel = p.relative_to(dest_docs)
            if not (stage_docs / rel).exists():
                p.unlink()
                removed += 1
    for p in sorted(stage_docs.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(stage_docs)
        dst = dest_docs / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if (not dst.exists()) or dst.read_bytes() != p.read_bytes():
            shutil.copy2(p, dst)
            added += 1
    return added, removed


def ensure_repo(work: Path, owner: str, repo: str, branch: str) -> bool:
    """确保工作副本是 git 仓库且远端已配置。返回是否新建。"""
    created = False
    if not (work / ".git").exists():
        if not work.exists():
            work.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "-C", str(work), "init", "-q", "-b", branch],
                       check=True, capture_output=True)
        created = True
    remote_url = f"https://github.com/{owner}/{repo}.git"
    r = subprocess.run(["git", "-C", str(work), "remote"], capture_output=True, text=True)
    if "origin" in r.stdout:
        _git(["remote", "set-url", "origin", remote_url], cwd=work)
    else:
        _git(["remote", "add", "origin", remote_url], cwd=work)
    return created


def push(stage: Path, owner: str, repo: str, branch: str, message: str,
         dry_run: bool = False, skip_verify: bool = False) -> int:
    """执行推送。返回 0 成功（含无变化幂等跳过）。"""
    stage_docs = stage / "docs"
    work = WORK_ROOT

    token = read_token()
    if not skip_verify:
        login = verify_token(token, owner)
        print(f"  [认证] 令牌身份 {login} ✓")

    added, removed = sync_stage(stage_docs, work / "docs")
    print(f"  [同步] docs/ 更新 {added} 个文件"
          + (f"，删除 {removed} 个" if removed else ""))

    if dry_run:
        pending = _git(["status", "--porcelain"], cwd=work)
        print(f"  [dry-run] 待提交 {len([l for l in pending.splitlines() if l.strip()])} 项")
        return 0

    if not _head_exists(work):
        _git(["add", "-A"], cwd=work)
        _git(["-c", f"user.name={COMMIT_AUTHOR_NAME}",
              "-c", f"user.email={COMMIT_AUTHOR_EMAIL}",
              "commit", "-q", "-m", message], cwd=work)
        print(f"  [提交] {message}（首次提交）")
    else:
        status = _git(["status", "--porcelain"], cwd=work)
        if not status.strip():
            print("  [幂等] 工作区无变化，跳过提交（不产生空提交）")
            return 0
        _git(["add", "-A"], cwd=work)
        _git(["-c", f"user.name={COMMIT_AUTHOR_NAME}",
              "-c", f"user.email={COMMIT_AUTHOR_EMAIL}",
              "commit", "-q", "-m", message], cwd=work)
        print(f"  [提交] {message}")

    _git(["push", "-u", "origin", branch], cwd=work, token=token)
    sha = _git(["rev-parse", "--short", "HEAD"], cwd=work).strip()
    print(f"  [推送] → https://github.com/{owner}/{repo}/commit/{sha}")
    return 0


def _head_exists(work: Path) -> bool:
    r = subprocess.run(["git", "-C", str(work), "rev-parse", "--verify", "HEAD"],
                       capture_output=True, text=True)
    return r.returncode == 0


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="GitHub 推送执行器")
    ap.add_argument("--stage", required=True)
    ap.add_argument("--owner", default="seaquake97")
    ap.add_argument("--repo", default="daily-market-pulse")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--message", required=True)
    ap.add_argument("--dry-run", action="store_true",
                    help="只同步与校验身份，不 commit/push")
    ap.add_argument("--skip-verify", action="store_true")
    args = ap.parse_args()

    try:
        work = WORK_ROOT
        ensure_repo(work, args.owner, args.repo, args.branch)
        rc = push(Path(args.stage), args.owner, args.repo, args.branch,
                  args.message, dry_run=args.dry_run, skip_verify=args.skip_verify)
    except PushError as e:
        print(f"❌ 推送失败: {e}", file=sys.stderr)
        return 6
    return rc


if __name__ == "__main__":
    sys.exit(main())