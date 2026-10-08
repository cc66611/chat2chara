#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
json2png.py — 把角色卡 JSON 打包成 PNG 卡（SillyTavern 里直接拖进去就能用）

原理：PNG 卡的「图像」其实是一张普通图片，角色卡数据以 base64 塞在图片的
      tEXt 文本块里。SillyTavern 读卡时：先找 ccv3 块（V3），找不到再找
      chara 块（V2）。本脚本两个块都写，新旧版本都能读。

只用到 Python 标准库（zlib / struct / base64）。

用法：
    python json2png.py -i 角色卡.json -o 角色卡.png --avatar 头像.png
    python json2png.py -i 角色卡.json -o 角色卡.png        # 没有头像图时生成渐变占位图

注意：头像经由微信等应用转发会被重新压缩，text 块会丢，卡就废了。
      发 PNG 卡请用原始文件，或者发 JSON。
"""
import argparse
import base64
import json
import struct
import sys
import zlib
from pathlib import Path

# ---- 输出语言（--lang zh|en，默认 zh）----
LANG = "zh"


def T(zh, en=None, **kw):
    """面向用户的文案。默认返回中文；--lang en 时返回英文（没给英文就回退中文）。"""
    s = en if (LANG == "en" and en) else zh
    return s.format(**kw) if kw else s


SIG = b"\x89PNG\r\n\x1a\n"


def _chunk(tp, data):
    return (struct.pack(">I", len(data)) + tp + data
            + struct.pack(">I", zlib.crc32(tp + data) & 0xFFFFFFFF))


def text_chunk(keyword, value):
    """构造一个 tEXt 块（keyword\0text）。"""
    payload = keyword.encode("latin-1") + b"\x00" + value.encode("latin-1")
    return _chunk(b"tEXt", payload)


def solid_gradient_png(w=400, h=600):
    """没给头像时，生成一张竖向渐变占位图（纯标准库，不依赖 Pillow）。"""
    top, bot = (58, 78, 120), (26, 32, 48)
    rows = []
    for y in range(h):
        t = y / max(1, h - 1)
        rgb = bytes(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
        rows.append(b"\x00" + rgb * w)          # filter type 0 + 一行像素
    raw = b"".join(rows)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)   # 8bit RGB
    return SIG + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b"")


def to_v3(card):
    """把 V2 卡转成 V3 信封：字段不动，只改 spec 标记。

    V3 设计上向后兼容 V2，所以只带 V2 字段的 V3 卡是合法的。
    """
    out = dict(card)
    out["spec"] = "chara_card_v3"
    out["spec_version"] = "3.0"
    return out


def embed(png_bytes, pairs):
    """把若干 (keyword, text) 插到 IEND 之前。"""
    iend = png_bytes.rindex(b"IEND") - 4
    if iend < 8:
        sys.exit(T("这个 PNG 不完整（找不到 IEND）", "This PNG is incomplete (no IEND chunk found)"))
    extra = b"".join(text_chunk(k, v) for k, v in pairs)
    return png_bytes[:iend] + extra + png_bytes[iend:]


def main():
    ap = argparse.ArgumentParser(description="角色卡 JSON → PNG 卡")
    ap.add_argument("-i", "--input", required=True, help="角色卡 JSON")
    ap.add_argument("-o", "--output", required=True, help="输出的 PNG 路径")
    ap.add_argument("--avatar", default="", help="头像图片（PNG）。不给就生成渐变占位图")
    ap.add_argument("--lang", choices=["zh", "en"], default="zh",
                    help="输出语言：zh（默认）中文 / en English")
    args = ap.parse_args()
    global LANG
    LANG = args.lang

    src = Path(args.input)
    if not src.exists():
        sys.exit(T("角色卡文件不存在：{p}", "Character card file not found: {p}", p=src))
    try:
        card = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(T("这不是合法的 JSON：{p}\n  第 {ln} 行第 {col} 列 —— {msg}",
                   "Not valid JSON: {p}\n  At line {ln}, column {col} — {msg}",
                   p=src, ln=e.lineno, col=e.colno, msg=e.msg))

    if args.avatar:
        av = Path(args.avatar)
        if not av.exists():
            sys.exit(T("头像文件不存在：{p}", "Avatar file not found: {p}", p=av))
        base = av.read_bytes()
        if not base.startswith(SIG):
            sys.exit(T("头像不是 PNG：{p}\n  提示：先用画图/PS 另存为 PNG 再试。",
                       "The avatar is not a PNG: {p}\n  Tip: re-save it as PNG first.",
                       p=av))
    else:
        base = solid_gradient_png()
        print(T("未提供头像，已生成渐变占位图（可用 --avatar 换成自己的图）",
                "No avatar given; generated a gradient placeholder (use --avatar to supply your own)."))

    v2_json = json.dumps(card, ensure_ascii=False, separators=(",", ":"))
    v3_json = json.dumps(to_v3(card), ensure_ascii=False, separators=(",", ":"))
    out = embed(base, [
        ("chara", base64.b64encode(v2_json.encode("utf-8")).decode("ascii")),
        ("ccv3", base64.b64encode(v3_json.encode("utf-8")).decode("ascii")),
    ])

    dst = Path(args.output)
    dst.write_bytes(out)
    name = (card.get("data") or card).get("name", "(未命名)")
    print(T("已写出：{p}", "Written: {p}", p=dst))
    print(T("  角色：{n}", "  Character: {n}", n=name))
    print(T("  chara 块（V2）：{a} 字符 → base64 后 {b} 字符",
            "  chunk 'chara' (V2): {a} chars -> {b} after base64",
            a=len(v2_json), b=len(base64.b64encode(v2_json.encode()))))
    print(T("  ccv3  块（V3）：{a} 字符", "  chunk 'ccv3'  (V3): {a} chars", a=len(v3_json)))
    print(T("  用法：把这个 PNG 拖进 SillyTavern 的角色列表即可。",
            "  Usage: drag this PNG into the SillyTavern character list."))


if __name__ == "__main__":
    main()
