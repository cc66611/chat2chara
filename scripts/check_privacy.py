#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_privacy.py — 发布前隐私自检

push 之前跑一次：扫一遍**将要交给 git 的文件**，看有没有夹带
真实聊天记录痕迹、本机路径、手机号、密钥之类的东西。

只扫会被提交的文件——被 .gitignore 忽略的不扫（那些本来也进不了仓库）。

用法：
    python check_privacy.py
    python check_privacy.py --path D:\\chat2chara
退出码：0 = 干净；1 = 有命中，先处理再提交。
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

# ---- 输出语言（--lang zh|en，默认 zh）----
LANG = "zh"


def T(zh, en=None, **kw):
    """面向用户的文案。默认返回中文；--lang en 时返回英文（没给英文就回退中文）。"""
    s = en if (LANG == "en" and en) else zh
    return s.format(**kw) if kw else s


LABEL_EN = {
    "手机号": "phone number", "身份证": "national ID", "邮箱": "email",
    "微信号": "WeChat ID", "本机路径": "local path",
    "IP 地址": "IP address", "疑似密钥": "possible secret",
}

RULES = [
    ("手机号",   re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("身份证",   re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    ("邮箱",     re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")),
    ("微信号",   re.compile(r"wxid_[A-Za-z0-9_]{4,}")),
    ("本机路径", re.compile(r"[A-Za-z]:\\\\Users\\\\[^\\\\\s\"']+|/(?:Users|home)/[A-Za-z0-9._-]+")),
    ("IP 地址",  re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")),
    ("疑似密钥", re.compile(r"(?:sk|pk)-[A-Za-z0-9]{16,}")),
]

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vscode"}
BIN_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".svg",
           ".mp3", ".mp4", ".wav", ".zip", ".gz", ".tar", ".7z", ".rar",
           ".exe", ".dll", ".so", ".pyc", ".pdf", ".woff", ".woff2", ".ttf", ".bin"}
MAX_BYTES = 2 * 1024 * 1024
# 脚本自己带正则字面量，必须跳过
SELF = {"check_privacy.py"}


def tracked_files(root: Path):
    """列出会进 git 的文本文件。"""
    cands = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.name in SELF:
            continue
        if p.suffix.lower() in BIN_EXT:
            continue
        try:
            if p.stat().st_size > MAX_BYTES:
                continue
        except OSError:
            continue
        cands.append(p)

    rel = [str(p.relative_to(root)).replace("\\", "/") for p in cands]
    ignored = set()
    try:
        r = subprocess.run(["git", "-C", str(root), "check-ignore", "--stdin"],
                           input="\n".join(rel), capture_output=True,
                           text=True, timeout=60)
        ignored = {l.strip() for l in r.stdout.split("\n") if l.strip()}
    except Exception:
        pass
    return [(p, rr) for p, rr in zip(cands, rel) if rr not in ignored]


def main():
    ap = argparse.ArgumentParser(description="发布前隐私自检")
    ap.add_argument("--path", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--lang", choices=["zh", "en"], default="zh",
                    help="输出语言：zh（默认）中文 / en English")
    args = ap.parse_args()
    global LANG
    LANG = args.lang
    root = Path(args.path).resolve()

    items = tracked_files(root)
    print(T("=== 隐私自检：{n} 个文件（已排除 .gitignore 忽略的）===",
            "=== Privacy scan: {n} files (those ignored by .gitignore are excluded) ===",
            n=len(items)))

    hits = []
    for p, rel in items:
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").split("\n")
        except Exception:
            continue
        for i, line in enumerate(lines, 1):
            for label, rx in RULES:
                for m in rx.finditer(line):
                    hits.append((rel, i, label, m.group(0)[:60]))

    if not hits:
        print(T("✓ 未发现可疑内容。", "✓ Nothing suspicious found."))
        return 0

    print(T("\n✗ 发现 {n} 处，逐条确认后再提交：\n",
            "\n✗ {n} hit(s) found — confirm each one before committing:\n", n=len(hits)))
    for rel, i, label, val in hits:
        print(f"  [{T(label, LABEL_EN.get(label))}] {rel}:{i}  {val}")
    print(T("\n如果这些是示例数据里的假信息，请确认它确实不指向任何真实的人。",
            "\nIf these are fake values inside demo data, just make sure they do not point at a real person."))
    return 1


if __name__ == "__main__":
    sys.exit(main())
