#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
srt2txt.py — 字幕文件（.srt / .ass）→ 管道标准 txt

用途：把动画 / 影视 / 广播剧字幕里的台词，变成「某个角色的语料」，
      再交给 analyze.py / sample.py 走同一条管道。

只做格式转换。不涉及视频、加密，或任何平台数据。

用法：
    python srt2txt.py -i ep01.srt -o ep01.txt --date 2024-01-01
    python srt2txt.py -i ep01.ass --date 2024-01-01
    python srt2txt.py -i ep01.srt --speaker 星野      # 整份字幕都算这个角色
    python srt2txt.py -i ep01.srt --list-speakers     # 先看有哪些说话人
"""
import argparse
import re
import sys
from pathlib import Path

# ---- 输出语言（--lang zh|en，默认 zh）----
LANG = "zh"


def T(zh, en=None, **kw):
    """面向用户的文案。默认返回中文；--lang en 时返回英文（没给英文就回退中文）。
    两种语言都用 {name} 形式的占位符，参数走 kw；没有 kw 就不做格式化。"""
    s = en if (LANG == "en" and en) else zh
    return s.format(**kw) if kw else s


SPK_RE = re.compile(r"^\s*([^：:（(]{1,16})\s*[：:]\s*(.+)$")


def strip_ass_tags(s):
    """去掉 ASS 的样式标签与换行标记。"""
    s = re.sub(r"\{[^}]*\}", "", s)          # {\pos(10,10)}、{\c&H...} 之类
    s = s.replace("\\N", " ").replace("\\n", " ")
    return s.strip()


def parse_srt(text):
    text = text.replace("\r\n", "\n")
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [l for l in block.split("\n") if l.strip()]
        if len(lines) < 2:
            continue
        ti = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if ti is None:
            continue
        raw_t = lines[ti].split("-->")[0].strip()
        body = " ".join(lines[ti + 1:]).strip()
        if body:
            out.append((raw_t, body))
    return out


def parse_ass(text):
    out = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if not line.startswith("Dialogue:"):
            continue
        parts = line[len("Dialogue:"):].split(",", 9)
        if len(parts) < 10:
            continue
        raw_t = parts[1].strip()
        name = parts[4].strip()          # ASS 的 Name 字段，有时用来标说话人
        body = strip_ass_tags(parts[9])
        if body:
            out.append((raw_t, f"{name}：{body}" if name else body))
    return out


def norm_time(raw, date):
    """00:01:23,000 / 0:00:01.00 → YYYY-MM-DD HH:MM:SS"""
    m = re.match(r"(\d+):(\d{2}):(\d{2})", raw.strip())
    if not m:
        return ""
    return f"{date} {int(m.group(1)):02d}:{int(m.group(2)):02d}:{m.group(3)}"


def main():
    ap = argparse.ArgumentParser(description="字幕文件 → 管道标准 txt")
    ap.add_argument("-i", "--input", required=True, help="字幕文件（.srt / .ass）")
    ap.add_argument("-o", "--output", help="输出 txt（默认与输入同目录同名）")
    ap.add_argument("--date", default="2024-01-01",
                    help="给这一集打的日期（默认 2024-01-01）。多集一起处理时，用它能画出集数曲线")
    ap.add_argument("--speaker", default="",
                    help="整份字幕都算这个角色的台词（字幕没有「名字：」前缀时用）")
    ap.add_argument("--list-speakers", action="store_true",
                    help="只列出有哪些说话人，不转换")
    ap.add_argument("--lang", choices=["zh", "en"], default="zh",
                    help="输出语言：zh（默认）中文 / en English")
    args = ap.parse_args()
    global LANG
    LANG = args.lang

    src = Path(args.input)
    if not src.exists():
        sys.exit(T("字幕文件不存在：{p}", "Subtitle file not found: {p}", p=src))
    text = src.read_text(encoding="utf-8-sig", errors="replace")
    items = parse_ass(text) if src.suffix.lower() == ".ass" else parse_srt(text)

    if not items:
        raise SystemExit(T(
            "在这个文件里没找到任何字幕条目：{p}\n"
            "  它看起来不是字幕文件。字幕的每一条都有一行时间轴，长这样：\n"
            "      00:00:01,000 --> 00:00:03,500\n"
            "  如果你手上是聊天记录（三行一组：时间 / 发言人 / 内容），"
            "请改用 json2txt.py，它才是处理聊天记录的。",
            "No subtitle entries found in this file: {p}\n"
            "  It doesn't look like a subtitle file. Every subtitle has a timestamp line like this:\n"
            "      00:00:01,000 --> 00:00:03,500\n"
            "  If you have a chat log (three lines per message: time / speaker / content), "
            "use json2txt.py instead — that's the script for chat logs.",
            p=src))

    rows = []
    for raw_t, body in items:
        m = SPK_RE.match(body)
        if m and not args.speaker:
            spk, content = m.group(1).strip(), m.group(2).strip()
        else:
            spk, content = (args.speaker or "(未知)"), body
        ts = norm_time(raw_t, args.date)
        if ts and content:
            rows.append((ts, spk, content))

    if args.list_speakers:
        counts = {}
        for _, s, _ in rows:
            counts[s] = counts.get(s, 0) + 1
        print(T("共 {n} 条台词，说话人：", "{n} lines, speakers:", n=len(rows)))
        for n, k in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"  {n}  × {k}")
        return

    if not rows:
        sys.exit(T("一条台词都没解析出来：{p}\n"
                   "  载入 {n} 条字幕。常见原因：\n"
                   "    1. 字幕文件是空的，或格式不是 .srt / .ass\n"
                   "    2. 时间戳格式不认识（本工具认 00:01:23,000 和 0:00:01.00 两种）",
                   "No dialogue lines parsed: {p}\n"
                   "  Read {n} subtitle entries. Common causes:\n"
                   "    1. The subtitle file is empty, or its format is not .srt / .ass\n"
                   "    2. Unrecognized timestamp format (this tool accepts 00:01:23,000 and 0:00:01.00)",
                   p=src, n=len(items)))

    dst = Path(args.output) if args.output else src.with_suffix(".txt")
    out = []
    for ts, spk, content in rows:
        out += [ts, spk, content, ""]
    dst.write_text("\n".join(out), encoding="utf-8")

    print(T("载入 {a} 条字幕，写出 {b} 条 -> {d}", "Read {a} subtitle entries, wrote {b} -> {d}",
            a=len(items), b=len(rows), d=dst))
    if not args.speaker and rows:
        names = {}
        for _, s, _ in rows:
            names[s] = names.get(s, 0) + 1
        if len(names) == 1:
            print(T("  提示：只识别到一个说话人。若字幕本身没有「名字：」前缀，"
                  "用 --speaker 指定角色名即可",
                  "  Tip: only one speaker detected. If the subtitles carry no \"Name: \" prefix, "
                  "use --speaker to assign the whole file to one character."))


if __name__ == "__main__":
    main()
