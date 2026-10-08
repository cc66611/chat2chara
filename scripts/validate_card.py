#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_card.py — 角色卡 JSON 校验 + 结构统计

改卡之后必跑。它检查：
  - JSON 是否合法
  - 是否 chara_card_v2 规范
  - 关键字段是否非空
  - first_mes / mes_example 的回复行数（对应「行数控制」那条铁律）
  - 世界书条目数量与触发词

用法：
    python validate_card.py -i card.json
    python validate_card.py -i card.json -o report.txt
"""
import argparse
import json
from pathlib import Path


def count_lines(s):
    return len([x for x in (s or "").split("\n") if x.strip()])


def main():
    ap = argparse.ArgumentParser(description="校验 SillyTavern 角色卡")
    ap.add_argument("-i", "--input", required=True, help="角色卡 JSON")
    ap.add_argument("-o", "--output", help="报告输出路径（默认打印）")
    ap.add_argument("--max-lines", type=int, default=6,
                    help="first_mes 行数上限告警阈值")
    ap.add_argument("--max-example-lines", type=int, default=5,
                    help="示例回复行数上限告警阈值")
    args = ap.parse_args()

    L = []
    warn = []

    try:
        card = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except Exception as e:
        msg = f"JSON 解析失败：{e}"
        if args.output:
            Path(args.output).write_text(msg, encoding="utf-8")
        raise SystemExit(msg)

    spec = card.get("spec", "")
    d = card.get("data", card)

    L.append("=== 角色卡校验报告 ===")
    L.append(f"spec: {spec or '(未声明)'}")
    if spec != "chara_card_v2":
        warn.append("spec 不是 chara_card_v2，SillyTavern 可能不识别")
    L.append(f"name: {d.get('name', '(空)')}")
    L.append("")

    # 必填字段
    L.append("--- 字段检查 ---")
    for field in ("name", "description", "personality", "scenario",
                  "first_mes", "mes_example"):
        val = d.get(field, "")
        n = len(val) if isinstance(val, str) else 0
        flag = "OK" if n > 0 else "空！"
        if n == 0:
            warn.append(f"字段 {field} 为空")
        L.append(f"  {field:<16} {n:>6} 字符  [{flag}]")

    phi = d.get("post_history_instructions", "")
    L.append(f"  {'post_history_instructions':<16} {len(phi):>6} 字符  "
             f"[{'OK' if phi else '空（建议填写，这是最强的行为控制器）'}]")
    if not phi:
        warn.append("post_history_instructions 为空，行为控制力会明显下降")
    L.append("")

    # 行数检查（铁律一）
    L.append("--- 行数检查（铁律一：模型会模仿示例的行数）---")
    fm = count_lines(d.get("first_mes", ""))
    L.append(f"  first_mes 非空行数：{fm}")
    if fm > args.max_lines:
        warn.append(f"first_mes 有 {fm} 行，超过 {args.max_lines} 行，"
                    f"模型会学着一次输出这么多")

    examples = d.get("mes_example", "")
    groups = examples.split("{{user}}")
    idx = 0
    for g in groups:
        if "{{char}}" not in g:
            continue
        reply = g.split("{{char}}", 1)[1]
        n = count_lines(reply)
        idx += 1
        flag = ""
        if n > args.max_example_lines:
            flag = "  ← 超长，会导致抢戏"
            warn.append(f"示例 {idx} 回复 {n} 行，超过 {args.max_example_lines} 行")
        L.append(f"  示例 {idx} 回复行数：{n}{flag}")
    if idx == 0:
        warn.append("mes_example 里没有找到 {{char}} 回复，格式可能不对")
    L.append("")

    # 世界书
    book = d.get("character_book", {})
    entries = book.get("entries", []) if isinstance(book, dict) else []
    L.append("--- 世界书 ---")
    L.append(f"  条目数：{len(entries)}")
    for i, e in enumerate(entries, 1):
        keys = e.get("keys", [])
        content = e.get("content", "")
        L.append(f"    {i:>2}. 触发词 {keys} ({len(content)} 字符)")
    if len(entries) == 0:
        warn.append("世界书为空，建议加 8-15 条覆盖典型场景")
    L.append("")

    # 备选开场白
    alts = d.get("alternate_greetings", [])
    L.append(f"--- alternate_greetings: {len(alts)} 条 ---")
    for i, a in enumerate(alts, 1):
        L.append(f"    {i}. {count_lines(a)} 行")
    L.append("")

    if warn:
        L.append("=== 需要关注 ===")
        for w in warn:
            L.append(f"  ! {w}")
    else:
        L.append("=== 全部检查通过 ===")

    report = "\n".join(L)
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"OK -> {args.output}")
        print(f"告警 {len(warn)} 条")
    else:
        print(report)


if __name__ == "__main__":
    main()
