#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_remap.py —— 重映射后的独立验证（不依赖编译器）。

思路：Mojang 官方 client_mappings 里列出了 1.20.1 的**全部官方类名**。
遍历源码里所有 net.minecraft 引用（import、代码、注解字符串、描述符），
逐个核对是否真的存在——这样就能在不拉 Forge/MC 依赖的前提下发现：
  * 映射错误（把类换成了一个不存在的名字）
  * 残留的 Yarn 名字（应该被换掉却没换）
  * 畸形拼接（例如 net.minecraft.net.minecraft... 这类二次替换事故）

用法：
    python tools/verify_remap.py [--proguard <client.txt>] [--src src/main/java]
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
import tempfile
from typing import Dict, Iterable, List, Set, Tuple

REF_DOTTED = re.compile(r"net\.minecraft\.(?!forge)(?:[.\w$]*[A-Z][\w$]*)")
DESC_CLASS = re.compile(r"L(net/minecraft(?:/[A-Za-z_$][A-Za-z0-9_$]*)+);")


def load_mojang(proguard: pathlib.Path) -> Tuple[Set[str], Set[str]]:
    """返回 (全部官方类, 全部官方成员名)。成员名用于把 X.FIELD 这类静态字段访问与内部类区分开。"""
    classes: Set[str] = set()
    members: Set[str] = set()
    with proguard.open(encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("    "):
                s = line.strip()
                m = re.match(r"^(?:\d+:\d+:)?(.+?) (\S+)(?:\([^)]*\))? -> \S+$", s)
                if m:
                    members.add(m.group(2))
                continue
            if line.rstrip().endswith(":") and " -> " in line:
                classes.add(line.split(" -> ")[0].replace(".", "/"))
    return classes, members


def exists(classes: Set[str], name: str, dotted: bool) -> bool:
    """name 为点号形式或内部名形式；内部类分别尝试 $ 与 / 的连接方式。"""
    if dotted:
        parts = name.split(".")
        for i in range(len(parts) - 1, 0, -1):
            cand = "/".join(parts[:i]) + "$" + "$".join(parts[i:])
            if cand in classes:
                return True
        return name.replace(".", "/") in classes
    if name in classes:
        return True
    parts = name.split("/")
    for i in range(len(parts) - 1, 0, -1):
        cand = "/".join(parts[:i]) + "$" + "$".join(parts[i:])
        if cand in classes:
            return True
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proguard", default=str(pathlib.Path(tempfile.gettempdir()) / "mc-mappings" / "client.txt"))
    ap.add_argument("--src", default="src/main/java")
    args = ap.parse_args(argv)

    pg = pathlib.Path(args.proguard)
    if not pg.is_file():
        print(f"[错误] 找不到官方映射: {pg}", file=sys.stderr)
        return 2
    classes, member_names = load_mojang(pg)
    files = sorted(pathlib.Path(args.src).rglob("*.java"))

    refs: Dict[str, Set[str]] = {}
    descs: Dict[str, Set[str]] = {}
    deformities: List[str] = []
    for p in files:
        text = p.read_text(encoding="utf-8")
        for m in REF_DOTTED.finditer(text):
            refs.setdefault(m.group(0), set()).add(p.name)
        for line in text.splitlines():
            if line.count("net.minecraft") > 1:
                deformities.append(f"{p.name}: {line.strip()[:120]}")
        for m in DESC_CLASS.finditer(text):
            descs.setdefault(m.group(1), set()).add(p.name)

    bad_refs = sorted(r for r in refs if not exists(classes, r, True))
    bad_descs = sorted(d for d in descs if not exists(classes, d, False))

    # 追加：代码里「外层类.内部类」的限定引用是否还指向不存在的内部类
    QUALIFIED = re.compile(r"\b([A-Z][\w$]*)\.([A-Z][\w$]*)\b")
    stale_inner: List[str] = []
    for p in files:
        text = p.read_text(encoding="utf-8")
        imports = {}
        for m in re.finditer(r"import\s+(?:static\s+)?([\w.]+)\s*;", text):
            fqn = m.group(1)
            if fqn.startswith("net.minecraft.") and not fqn.startswith("net.minecraftforge."):
                imports[fqn.split(".")[-1]] = fqn.replace(".", "/")
        for m in QUALIFIED.finditer(text):
            outer, inner = m.group(1), m.group(2)
            base = imports.get(outer)
            if not base:
                continue
            if (base + "$" + inner) not in classes and (base + "/" + inner) not in classes \
                    and inner not in member_names:
                stale_inner.append(f"{p.name}: {outer}.{inner}")
    stale_inner = sorted(set(stale_inner))

    print(f"扫描 {len(files)} 个文件；官方类总数 {len(classes)}")
    print(f"  点号形式 net.minecraft 引用 {len(refs)} 种，其中不存在于官方映射 {len(bad_refs)} 种")
    for r in bad_refs[:40]:
        print(f"    X {r}   <- {', '.join(sorted(refs[r])[:2])}")
    print(f"  描述符里的类引用 {len(descs)} 种，其中不存在 {len(bad_descs)} 种")
    for d in bad_descs[:20]:
        print(f"    X L{d};   <- {', '.join(sorted(descs[d])[:2])}")
    print(f"  单行出现多个 net.minecraft 的畸形行: {len(deformities)} 行")
    for d in deformities[:10]:
        print(f"    ! {d}")
    print(f"  疑似失效的内部类限定引用: {len(stale_inner)} 处")
    for s in stale_inner[:20]:
        print(f"    X {s}")
    ok = not bad_refs and not bad_descs and not deformities and not stale_inner
    print("=== 验证通过 ===" if ok else "=== 发现问题（见上）===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
