#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_oob.py —— 用上游原稿做“同位置模糊匹配”，定点还原被 remap 越界改坏的非 MC 成员名。

判定链（每一步都有依据，不猜）：
  1) 该 token 在上游同一文件里**不出现**（不是原稿就有的名字）
  2) 它的接收者链根是**非 MC**（JDK/第三方库 import、已知 JDK 类型、或声明类型为非 MC 的局部变量；字符串字面量按 String）
  3) 把当前行里的该 token 换成捕获组后，在上游同一文件里**恰好匹配到一行** -> 那一行对应位置的标识符就是原名
满足三条才还原；否则只报告，交给人工/编译结果。
"""
import pathlib, re, sys

NON_MC_ROOTS = ("java.", "javax.", "jdk.", "sun.", "com.sun.", "com.mojang.", "io.netty.",
                "org.slf4j.", "com.google.", "it.unimi.", "org.apache.", "com.electronwill.",
                "com.ibm.", "com.llamalad7.", "oshi.", "org.spongepowered.", "org.jetbrains.",
                "org.objectweb.", "io.reactivex.", "org.reactivestreams.")
JDK_TYPES = {"System","Class","String","CharSequence","Integer","Long","Double","Float","Boolean",
    "Byte","Short","Character","Math","StrictMath","Objects","Arrays","Collections","Optional",
    "List","ArrayList","LinkedList","Map","HashMap","LinkedHashMap","TreeMap","Set","HashSet",
    "LinkedHashSet","TreeSet","Queue","Deque","ArrayDeque","PriorityQueue","Iterator","Iterable",
    "Collection","Stream","Collectors","AtomicBoolean","AtomicInteger","AtomicLong","AtomicReference",
    "CompletableFuture","CompletionStage","ExecutorService","Executors","Thread","ThreadLocal",
    "StringBuilder","StringBuffer","Files","Path","Paths","IOException","DataOutputStream",
    "DataInputStream","ByteBuffer","Supplier","Consumer","Function","BiFunction","Predicate",
    "BiConsumer","Runnable","Callable","Comparable","Comparator","UUID","Random"}
IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")

SRC = pathlib.Path('src/main/java')
UP = pathlib.Path(sys.argv[2]) / 'src/main/java'
APPLY = '--apply' in sys.argv
assert UP.is_dir(), f'找不到上游源码: {UP}'

def imports_of(t):
    return {m.group(1).split('.')[-1]: m.group(1) for m in re.finditer(r"import\s+(?:static\s+)?([\w.]+)\s*;", t)}

def local_types(t):
    out = {}
    for m in re.finditer(r"(?:^|[;{(\s])([A-Z][\w.]*(?:<[^;=()]*>)?(?:\[\])?)\s+(\w+)\s*[=;,)]", t):
        out[m.group(2)] = m.group(1).split('<')[0].split('.')[-1].strip()
    return out

def non_mc(recv, imports, ltypes):
    if recv in JDK_TYPES:
        return True
    fqn = imports.get(recv)
    if fqn and fqn.startswith(NON_MC_ROOTS):
        return True
    tt = ltypes.get(recv)
    if tt:
        if tt in JDK_TYPES:
            return True
        tf = imports.get(tt)
        if tf and tf.startswith(NON_MC_ROOTS):
            return True
    return False

fixed, review = [], []
for p in sorted(SRC.rglob('*.java')):
    rel = p.relative_to(SRC)
    up = UP / rel
    if not up.is_file():
        continue
    text, utext = p.read_text(encoding='utf-8'), up.read_text(encoding='utf-8')
    up_tokens = set(IDENT.findall(utext))
    up_lines = utext.splitlines()
    imports, ltypes = imports_of(text), local_types(text)
    lines = text.splitlines()
    changed = False
    for i, line in enumerate(lines):
        if '.' not in line:
            continue
        for m in IDENT.finditer(line):
            tok = m.group(0)
            if tok in up_tokens:
                continue
            j = m.start() - 1
            if j < 0 or line[j] != '.':
                continue
            k = j - 1
            if k >= 0 and line[k] == '"':
                root = 'String'
            else:
                while k >= 0 and (line[k].isalnum() or line[k] in "_$."):
                    k -= 1
                root = line[k+1:j].split('.')[0]
            if not root or not non_mc(root, imports, ltypes):
                continue
            stripped = line.strip()
            pre, post = stripped[:stripped.index(tok)], stripped[stripped.index(tok)+len(tok):]
            pat = re.escape(pre) + r"(\w+)" + re.escape(post)
            hits = [l for l in up_lines if re.search(pat, l.strip())]
            if len(hits) == 1:
                old = re.search(pat, hits[0].strip()).group(1)
                if old != tok:
                    fixed.append((str(rel), i+1, root, tok, old))
                    lines[i] = line.replace('.' + tok, '.' + old, 1)
                    changed = True
                    break
            else:
                review.append((str(rel), i+1, root, tok, len(hits)))
    if changed and APPLY:
        p.write_text('\n'.join(lines) + ('\n' if text.endswith('\n') else ''), encoding='utf-8')

print(f"== 越界改名还原 ==  可还原 {len(fixed)} 处，需人工 {len(review)} 处（APPLY={APPLY}）")
for rel, ln, root, new, old in fixed:
    print(f"   [还原] {rel}:{ln}   {root}.{new} -> {root}.{old}")
for rel, ln, root, tok, n in review:
    print(f"   [待定] {rel}:{ln}   {root}.{tok}  （上游匹配 {n} 行）")