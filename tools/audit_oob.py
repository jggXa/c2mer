#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_oob.py —— 审计 remap 的「越界改名」（把非 Minecraft 的方法/字段改错），并可自动按原稿还原。

背景：token 式 remap 会把「全局唯一的 Yarn 成员名」替换到任何位置，包括
      Class.forName -> Class.byName、System.exit -> System.onServerExit、
      Queue.poll -> Queue.pop、AtomicBoolean.compareAndSet -> .replace 这类
      非 Minecraft 接收者上的同名调用。

做法（全部有据可依，不猜名字）：
  1. 以 remap 前的上游源码为 ground truth，逐文件取出「当前存在但原稿没有」的标识符 -> 候选改名点
  2. 解析该标识符的接收者（点号链的第一个标识符），判断接收者是否属于非 MC 包
     （java./javax./com.mojang./io.netty./org.slf4j./com.google./it.unimi./com.electronwill. ...
      或已知 JDK 类型名，或由这些包 import 进来的类型，或其声明类型如此）
  3. 非 MC 接收者 => B 类越界改名；--apply 时按原稿恢复成正确名字

用法：
  python tools/audit_oob.py --upstream "%TEMP%/c2me-up/c2me-base" [--apply]
"""
from __future__ import annotations

import argparse
import collections
import pathlib
import re
import sys
from typing import Dict, List, Optional, Set, Tuple

IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
NON_MC_ROOTS = ("java.", "javax.", "jdk.", "sun.", "com.sun.", "com.mojang.", "io.netty.",
                "org.slf4j.", "com.google.", "it.unimi.", "org.apache.", "com.electronwill.",
                "com.ibm.", "com.llamalad7.", "oshi.", "org.spongepowered.", "org.jetbrains.",
                "org.objectweb.", "io.reactivex.", "org.reactivestreams.", "com.github.")
JDK_TYPES = {
    "System", "Class", "String", "CharSequence", "Integer", "Long", "Double", "Float", "Boolean",
    "Byte", "Short", "Character", "Math", "StrictMath", "Objects", "Arrays", "Collections",
    "Optional", "List", "ArrayList", "LinkedList", "Map", "HashMap", "LinkedHashMap", "TreeMap",
    "Set", "HashSet", "LinkedHashSet", "TreeSet", "Queue", "Deque", "ArrayDeque", "PriorityQueue",
    "Iterator", "Iterable", "Collection", "Stream", "Collectors", "IntStream", "LongStream",
    "AtomicBoolean", "AtomicInteger", "AtomicLong", "AtomicReference", "AtomicIntegerArray",
    "CompletableFuture", "CompletionStage", "ExecutorService", "Executors", "Thread", "ThreadLocal",
    "StringBuilder", "StringBuffer", "StringJoiner", "Files", "Path", "Paths", "IOException",
    "DataOutputStream", "DataInputStream", "ByteBuffer", "Reference", "WeakReference", "Objects",
    "Supplier", "Consumer", "Function", "BiFunction", "Predicate", "BiConsumer", "Runnable",
    "Callable", "Comparable", "Comparator", "Iterator", "EnumSet", "EnumMap", "UUID", "Random",
}


def imports_of(text: str) -> Dict[str, str]:
    """简单名 -> 全限定名。"""
    out: Dict[str, str] = {}
    for m in re.finditer(r"import\s+(?:static\s+)?([\w.]+)\s*;", text):
        fqn = m.group(1)
        out[fqn.split(".")[-1]] = fqn
    return out


def local_types(text: str) -> Dict[str, str]:
    """变量名 -> 声明类型的简单名（粗解析，够用即可）。"""
    out: Dict[str, str] = {}
    for m in re.finditer(r"(?:^|[;{(\s])([A-Z][\w.]*(?:<[^;=()]*>)?(?:\[\])?)\s+(\w+)\s*[=;,)]", text):
        typ = m.group(1)
        typ = typ.split("<")[0].split(".")[-1].strip()
        out[m.group(2)] = typ
    return out


def is_non_mc_receiver(recv: str, imports: Dict[str, str], ltypes: Dict[str, str]) -> bool:
    if recv in JDK_TYPES or recv in ("System", "Class"):
        return True
    fqn = imports.get(recv)
    if fqn and fqn.startswith(NON_MC_ROOTS):
        return True
    t = ltypes.get(recv)
    if t:
        tfqn = imports.get(t)
        if t in JDK_TYPES or (tfqn and tfqn.startswith(NON_MC_ROOTS)):
            return True
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", required=True, help="remap 前的上游源码根（含 src/main/java）")
    ap.add_argument("--src", default="src/main/java")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    up_root = pathlib.Path(args.upstream) / "src/main/java"
    cur_root = pathlib.Path(args.src)
    if not up_root.is_dir():
        print(f"[错误] 找不到上游源码: {up_root}", file=sys.stderr)
        return 2

    findings: List[Tuple[str, int, str, str, str]] = []   # file, line, recv, new, old
    fixed_sites = 0
    for cur in sorted(cur_root.rglob("*.java")):
        rel = cur.relative_to(cur_root)
        up = up_root / rel
        if not up.is_file():
            continue
        ctext, utext = cur.read_text(encoding="utf-8"), up.read_text(encoding="utf-8")
        if ctext == utext:
            continue
        imports = imports_of(ctext)
        ltypes = local_types(ctext)
        # 原稿里出现过的标识符集合
        up_tokens = set(IDENT.findall(utext))
        # 逐行找「新名字 + 非 MC 接收者」
        new_lines = ctext.splitlines()
        for i, line in enumerate(new_lines):
            for m in IDENT.finditer(line):
                tok = m.group(0)
                if tok in up_tokens:
                    continue                       # 原稿里就有这个名字 -> 不是 remap 改出来的
                # 取接收者
                j = m.start() - 1
                if j < 0 or line[j] != ".":
                    continue                       # 不是成员访问（声明/局部名等）-> 跳过
                k = j - 1
                while k >= 0 and (line[k].isalnum() or line[k] in "_$"):
                    k -= 1
                recv = line[k + 1:j]
                if not recv or not is_non_mc_receiver(recv, imports, ltypes):
                    continue
                findings.append((str(rel), i + 1, recv, tok, line.strip()))

    print(f"== 越界改名审计（B 类）==  发现 {len(findings)} 处")
    by_recv = collections.Counter(f[2] for f in findings)
    for recv, n in by_recv.most_common():
        print(f"   接收者 {recv:20s} {n} 处")
    for rel, line, recv, tok, text in findings:
        print(f"   {rel}:{line}  {recv}.{tok}   | {text[:100]}")

    if args.apply and findings:
        print("\n[提示] --apply 需要先把该标识符映射回原稿名字，"
              "本工具只负责定位；请用 tools/restore_oob.py 或手工按上表还原。")
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
