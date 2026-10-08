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
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        sys.exit(f"字幕文件不存在：{src}")
    text = src.read_text(encoding="utf-8-sig", errors="replace")
    items = parse_ass(text) if src.suffix.lower() == ".ass" else parse_srt(text)

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
        print(f"共 {len(rows)} 条台词，说话人：")
        for n, k in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"  {n}  × {k}")
        return

    if not rows:
        sys.exit(f"一条台词都没解析出来：{src}\n"
                 f"  载入 {len(items)} 条字幕。常见原因：\n"
                 f"    1. 字幕文件是空的，或格式不是 .srt / .ass\n"
                 f"    2. 时间戳格式不认识（本工具认 00:01:23,000 和 0:00:01.00 两种）")

    dst = Path(args.output) if args.output else src.with_suffix(".txt")
    out = []
    for ts, spk, content in rows:
        out += [ts, spk, content, ""]
    dst.write_text("\n".join(out), encoding="utf-8")

    print(f"载入 {len(items)} 条字幕，写出 {len(rows)} 条 -> {dst}")
    if not args.speaker and rows:
        names = {}
        for _, s, _ in rows:
            names[s] = names.get(s, 0) + 1
        if len(names) == 1:
            print("  提示：只识别到一个说话人。若字幕本身带「名字：」前缀，"
                  "用 --speaker 指定角色名即可")


if __name__ == "__main__":
    main()
