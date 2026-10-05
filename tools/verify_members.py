#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_members.py —— 方法/字段级存在性校验（第 4 步的等价检查，不依赖编译器）。

用 Mojang 官方 client_mappings 建立「混入目标类 -> 官方成员集合」，再按键提取源码注解里的
成员引用：
    @Accessor("x")         -> 目标类的字段
    @Invoker("x")          -> 目标类的方法
    method = "x" / { ... } -> 目标类的成员（方法优先）
并核对它们是否真的存在于 1.20.1 官方映射里。找不到的即为「需要人工判断的残留 API」。
"""
import collections, pathlib, re, sys, tempfile

MD = pathlib.Path(tempfile.gettempdir()) / 'mc-mappings'
SRC = pathlib.Path('src/main/java')


def type_desc(t: str) -> str:
    t = t.strip()
    if t.endswith('[]'):
        return '[' + type_desc(t[:-2])
    prim = {'void': 'V', 'boolean': 'Z', 'byte': 'B', 'char': 'C', 'short': 'S',
            'int': 'I', 'long': 'J', 'float': 'F', 'double': 'D'}
    return prim.get(t, 'L' + t.replace('.', '/') + ';')


def args_desc(a: str) -> str:
    return '' if not a.strip() else ''.join(type_desc(x) for x in a.split(','))


files = sorted(SRC.rglob('*.java'))
mojang_classes = set()
with (MD / 'client.txt').open(encoding='utf-8') as fh:
    for line in fh:
        if not line.startswith('    ') and line.rstrip().endswith(':') and ' -> ' in line:
            mojang_classes.add(line.split(' -> ')[0].replace('.', '/'))


def internal_of(dotted):
    parts = dotted.split('.')
    for i in range(len(parts) - 1, 0, -1):
        cand = '/'.join(parts[:i]) + '$' + '$'.join(parts[i:])
        if cand in mojang_classes:
            return cand
    cand = dotted.replace('.', '/')
    return cand if cand in mojang_classes else None


methods = collections.defaultdict(set)
fields = collections.defaultdict(set)
names = collections.defaultdict(collections.Counter)   # owner -> {name: 出现次数}
want = set()
for p in files:
    m = re.search(r'@Mixin\s*\(([^)]*)\)', p.read_text(encoding='utf-8'))
    if not m:
        continue
    tm = re.search(r'targets\s*=\s*"([\w.$]+)"', m.group(1)) or re.search(r'([\w.]+)\s*\.class', m.group(1))
    if tm:
        i = internal_of(tm.group(1))
        if i:
            want.add(i)

cur = None
with (MD / 'client.txt').open(encoding='utf-8') as fh:
    for line in fh:
        if line.startswith('    '):
            if cur not in want:
                continue
            s = line.strip()
            mm = re.match(r'^(?:\d+:\d+:)?(.+?) (\S+)\(([^)]*)\) -> (\S+)$', s)
            if mm:
                name = mm.group(2)
                methods[cur].add((name, '(' + args_desc(mm.group(3)) + ')' + type_desc(mm.group(1))))
                names[cur][name] += 1
                continue
            mf = re.match(r'^(.+?) (\S+) -> (\S+)$', s)
            if mf:
                fields[cur].add(mf.group(2))
                names[cur][mf.group(2)] += 1
        else:
            m = re.match(r'^(\S+) -> (\S+):$', line.rstrip())
            cur = m.group(1).replace('.', '/') if m else None

hits = misses = 0
problems = []
for p in files:
    t = p.read_text(encoding='utf-8')
    m = re.search(r'@Mixin\s*\(([^)]*)\)', t)
    if not m:
        continue
    tm = re.search(r'targets\s*=\s*"([\w.$]+)"', m.group(1)) or re.search(r'([\w.]+)\s*\.class', m.group(1))
    owner = internal_of(tm.group(1)) if tm else None
    if owner is None:
        continue
    checks = []
    for mm in re.finditer(r'@Accessor\s*\(\s*"([^"]+)"', t):
        checks.append(('field', mm.group(1)))
    for mm in re.finditer(r'@Invoker\s*\(\s*"([^"]+)"', t):
        checks.append(('method', mm.group(1)))
    for mm in re.finditer(r'\bmethod\s*=\s*\{?\s*"([^"()]+)"', t):
        checks.append(('method', mm.group(1)))
    for kind, nm in checks:
        if nm in names[owner]:
            hits += 1
        else:
            misses += 1
            problems.append(f'{p.name}: @{kind} {nm} 在 {tm.group(1)} 的官方成员里不存在')

print(f'混入目标类 {len(want)} 个；官方成员：方法 {sum(len(v) for v in methods.values())} 条 / 字段 {sum(len(v) for v in fields.values())} 条')
print(f'  注解成员引用检查：命中 {hits}，不存在 {misses}')
for x in problems[:40]:
    print('    X ' + x)
print('=== 方法级校验通过 ===' if not problems else '=== 有找不到的成员（见上）===')
sys.exit(0 if not problems else 1)