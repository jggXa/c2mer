#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
remap_src.py —— 把 Java 源码从 Yarn 命名重映射到 Mojang 官方命名（Forge official 通道）。

映射链（与工具 aw2at.py 共用 Step/Chain 结构）：
    named(Yarn)  --yarn.tiny(reverse)-->  intermediary  --intermediary.tiny(reverse)-->  official(混淆)
                 --client.txt(ProGuard)-->  Mojang(去混淆)

处理四类映射点（刻意不做“整文件正则替换”）：
  1. import 的类名：完全限定名精确替换（无歧义）
  2. 代码里的标识符：
       * 类名（依据本文件 import 出来的 MC 简单名）
       * 方法名 / 字段名 —— 只替换「在整个 MC 命名空间里映射唯一」的名字，
         并且跳过本文件自己声明（非 @Shadow/@Overwrite）的名字，避免误改我们自己的成员
  3. @Shadow / @Overwrite 声明的成员名：属于 MC 成员，按 mixin 目标类解析后替换
  4. 注解字符串参数：@Mixin(targets=)、@Accessor、@Invoker、@Inject/Redirect/ModifyXxx 的
     method=、@At 的 target= 等；按 mixin 目标类解析成员名，并处理 $ 与 . 的差异

用法：
    python tools/remap_src.py --report                    # 只统计，不改文件
    python tools/remap_src.py --check-mixin               # 单独检查 @Mixin(targets="...")
    python tools/remap_src.py --apply                     # 原地改写
    python tools/remap_src.py --selftest                  # 自测
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import aw2at  # noqa: E402  （复用 Step / Chain / remap_desc / parse_tiny）

IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
# 代码/字符串里的完全限定 MC 类名（点号形式）
FQN_DOTTED = re.compile(r"net\.minecraft(?:\.[A-Za-z_$][A-Za-z0-9_$]*)+")
# 描述符或 target 字符串里的内部名形式
# 注意：不能加 \b —— 描述符里是 Lnet/minecraft/...;，L 与 n 之间没有词边界
FQN_INTERNAL = re.compile(r"net/minecraft(?:/[A-Za-z_$][A-Za-z0-9_$]*)+")

MIXIN_TARGETS = re.compile(r'@Mixin\s*\(([^)]*)\)', re.S)
# 「包路径式点号链」：小写包名开头、大写类名结尾（如 net.minecraft.world.level.Level）
# 链内不做 token 替换，避免包名分量被成员名映射误伤
PROTECTED_CHAIN = re.compile(r"(?:[a-z][\w$]*\.)+[A-Z][\w$]*")
# 代码里「外层类.内部类」的限定引用（两个大写开头的简单名用点连接）
QUALIFIED_INNER = re.compile(r"\b([A-Z][\w$]*)\.([A-Z][\w$]*)\b")
TARGETS_STR = re.compile(r'targets\s*=\s*"([^"]+)"')
TARGETS_ARR = re.compile(r'targets\s*=\s*\{([^}]*)\}')
MEMBER_ANNOTATIONS = ("Accessor", "Invoker")
METHOD_STRING_ANNOTATIONS = ("Inject", "Redirect", "ModifyVariable", "ModifyArg", "ModifyArgs", "ModifyConstant", "WrapOperation", "WrapMethod", "At", "Slice")


# ---------------------------------------------------------------------------
# ProGuard 官方映射（Mojang client.txt）：混淆 -> Mojang
# ---------------------------------------------------------------------------
def parse_proguard(path: pathlib.Path, keep_owners: Optional[Set[str]] = None,
                   keep_names: Optional[Set[str]] = None) -> aw2at.Step:
    """解析 Mojang client.txt。

    keep_owners / keep_names 用来做过滤：client.txt 有 70 万类、数百万成员，全量建表会吃掉数 GB 内存；
    只保留「源码引用到的属主」与「候选成员名」相关的条目即可（类名映射仍全量保留）。
    """
    step = aw2at.Step("official", "mojang")
    mojang_to_obf: Dict[str, str] = {}
    blocks: List[Tuple[str, List[str]]] = []
    cur: Optional[List[str]] = None
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            if not line.startswith("    "):
                # 类行: <Mojang 名> -> <混淆名>:
                m = re.match(r"^(\S+) -> (\S+):$", line)
                if not m:
                    continue
                mojang, obf = m.group(1), m.group(2)
                mojang_to_obf[mojang] = obf
                step.class_map[obf.replace(".", "/")] = mojang.replace(".", "/")
                cur = [obf.replace(".", "/"), []]
                blocks.append((cur[0], cur[1]))
            elif cur is not None:
                cur[1].append(line.strip())

    # 反向表只用构建一次（成员循环里逐行重建会退化成 O(N²)）
    mojang_to_obf_internal = {k.replace(".", "/"): v.replace(".", "/") for k, v in mojang_to_obf.items()}

    for owner_obf, members in blocks:
        if keep_owners is not None and owner_obf not in keep_owners:
            # 属主不相关：只可能因为「候选成员名」而需要保留，交给下面的逐个判断
            pass
        for mem in members:
            m = re.match(r"^(?:\d+:\d+:)?(.+?) (\S+)\(([^)]*)\) -> (\S+)$", mem)
            if m:  # 方法
                ret, name, args, obf_name = m.group(1), m.group(2), m.group(3), m.group(4)
                if name == "<init>":
                    continue
                if keep_names is not None and obf_name not in keep_names and \
                        (keep_owners is None or owner_obf not in keep_owners):
                    continue
                desc_mojang = "(" + _args_to_desc(args, mojang_to_obf) + ")" + _type_to_desc(ret, mojang_to_obf)
                desc_obf = aw2at.remap_desc(desc_mojang, mojang_to_obf_internal)
                step.method_map[(owner_obf, desc_obf, obf_name)] = name
                continue
            m = re.match(r"^(.+?) (\S+) -> (\S+)$", mem)
            if m:  # 字段
                ftype, _name, obf_name = m.group(1), m.group(2), m.group(3)
                if keep_names is not None and obf_name not in keep_names and \
                        (keep_owners is None or owner_obf not in keep_owners):
                    continue
                desc_mojang = _type_to_desc(ftype, mojang_to_obf)
                desc_obf = aw2at.remap_desc(desc_mojang, mojang_to_obf_internal)
                step.field_map[(owner_obf, desc_obf, obf_name)] = _name
    return step


def _type_to_desc(t: str, mojang_to_obf: Dict[str, str]) -> str:
    t = t.strip()
    if t.endswith("[]"):
        return "[" + _type_to_desc(t[:-2], mojang_to_obf)
    prim = {"void": "V", "boolean": "Z", "byte": "B", "char": "C", "short": "S",
            "int": "I", "long": "J", "float": "F", "double": "D"}
    if t in prim:
        return prim[t]
    return "L" + t.replace(".", "/") + ";"


def _args_to_desc(args: str, mojang_to_obf: Dict[str, str]) -> str:
    if not args.strip():
        return ""
    # 形如 java.util.Map,int  —— 逗号分隔且不嵌套泛型（官方映射里没有泛型）
    return "".join(_type_to_desc(a, mojang_to_obf) for a in args.split(","))


# ---------------------------------------------------------------------------
# 重命名器
# ---------------------------------------------------------------------------
class Renamer:

    def __init__(self, chain: aw2at.Chain, yarn_step: aw2at.Step,
                 referenced: Optional[Set[str]] = None,
                 candidates: Optional[Set[str]] = None) -> None:
        self.chain = chain
        self.class_map: Dict[str, str] = {}          # yarn internal -> mojang internal
        self.method_by_name: Dict[str, Set[str]] = {}
        self.field_by_name: Dict[str, Set[str]] = {}
        self.member_by_owner: Dict[Tuple[str, str], Set[str]] = {}   # (yarn owner internal, name) -> mojang names
        self.member_desc_by_owner: Dict[Tuple[str, str, str], str] = {}
        self.unmapped_classes: List[str] = []
        # 官方(Mojang)类集合，由 main 在解析 client.txt 后注入；用于识别“已经是官方名”的引用
        self.mojang_classes: Set[str] = set()

        # yarn_step = parse_tiny(yarn, reverse=True)：方向为 named -> intermediary，
        # 因此它的键就是 Yarn(named) 侧的名字，值才是 intermediary。
        for (y_owner, y_desc, y_name) in yarn_step.method_map:
            if referenced is not None and y_owner not in referenced and \
                    (candidates is not None and y_name not in candidates):
                continue
            got = chain.remap_member(y_owner, y_desc, y_name, "method")
            if got is None:
                continue
            _m_owner, _m_desc, m_name = got
            self.method_by_name.setdefault(y_name, set()).add(m_name)
            self.member_by_owner.setdefault((y_owner, y_name), set()).add(m_name)
            self.member_desc_by_owner[(y_owner, y_name, y_desc)] = m_name
        for (y_owner, y_desc, y_name) in yarn_step.field_map:
            if referenced is not None and y_owner not in referenced and \
                    (candidates is not None and y_name not in candidates):
                continue
            got = chain.remap_member(y_owner, y_desc, y_name, "field")
            if got is None:
                continue
            _, _, m_name = got
            self.field_by_name.setdefault(y_name, set()).add(m_name)
            self.member_by_owner.setdefault((y_owner, y_name), set()).add(m_name)
        for y_cls in yarn_step.class_map:
            m_cls = chain.remap_class(y_cls)
            if m_cls == y_cls and y_cls.startswith("net/minecraft"):
                self.unmapped_classes.append(y_cls)
            self.class_map[y_cls] = m_cls

    # ---------------------------------------------------------------- 查询
    def map_class_internal(self, internal: str) -> Optional[str]:
        """internal 用 / 分隔（内部类用 $）；返回 Mojang internal，未映射返回 None。"""
        if internal in self.class_map:
            return self.class_map[internal]
        return None

    def resolve_dotted(self, fqn: str) -> Optional[Tuple[str, str]]:
        """把源码里的点号形式解析成 (yarn internal, mojang internal)（处理内部类 $ 与 . 差异）。"""
        parts = fqn.split(".")
        for split in range(len(parts), 1, -1):
            pkg = "/".join(parts[:split])
            inner = "$".join(parts[split:])
            cand = pkg + ("$" + inner if inner else "")
            if cand in self.class_map:
                return cand, self.class_map[cand]
        return None

    def map_member(self, owner_internal: Optional[str], name: str, kind: str) -> Optional[str]:
        """按属主解析成员名；属主未知或该属主下不唯一/未映射时返回 None。"""
        if owner_internal is not None:
            names = self.member_by_owner.get((owner_internal, name))
            if names and len(names) == 1:
                return next(iter(names))
            return None
        table = self.method_by_name if kind == "method" else self.field_by_name
        names = table.get(name)
        if names and len(names) == 1:
            return next(iter(names))
        return None

    def is_mojang_class(self, fqn: str) -> bool:
        """判断点号形式的名字是否已经是官方(Mojang)类（用于区分“未映射”与“本来就不是 MC 类”）。"""
        if fqn.replace(".", "/") in self.mojang_classes:
            return True
        parts = fqn.split(".")
        for i in range(len(parts) - 1, 0, -1):
            cand = "/".join(parts[:i]) + "$" + "$".join(parts[i:])
            if cand in self.mojang_classes:
                return True
        return False

    def global_member(self, name: str) -> Optional[str]:
        """全局唯一的方法/字段名（无论属主都映射到同一个官方名）才返回，否则 None。"""
        for table in (self.method_by_name, self.field_by_name):
            names = table.get(name)
            if names is not None:
                if len(names) == 1:
                    return next(iter(names))
                return None
        return None


# ---------------------------------------------------------------------------
# 源码扫描 / 改写
# ---------------------------------------------------------------------------
def to_source_fqn(mojang_internal: str) -> str:
    """Mojang internal -> 源码点号形式（内部类用 . 连接）。"""
    return mojang_internal.replace("$", ".").replace("/", ".")


def split_code(text: str) -> List[Tuple[str, str]]:
    """切成 (类型, 内容) 片段：code / str / char / line_comment / block_comment。"""
    out: List[Tuple[str, str]] = []
    i, n, buf = 0, len(text), []
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            if buf:
                out.append(("code", "".join(buf)))
                buf = []
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(("line_comment", text[i:j]))
            i = j
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            if buf:
                out.append(("code", "".join(buf)))
                buf = []
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(("block_comment", text[i:j]))
            i = j
        elif c == '"':
            if buf:
                out.append(("code", "".join(buf)))
                buf = []
            j, esc = i + 1, False
            while j < n:
                if esc:
                    esc = False
                elif text[j] == "\\":
                    esc = True
                elif text[j] == '"':
                    j += 1
                    break
                j += 1
            out.append(("str", text[i:j]))
            i = j
        elif c == "'":
            if buf:
                out.append(("code", "".join(buf)))
                buf = []
            j, esc = i + 1, False
            while j < n:
                if esc:
                    esc = False
                elif text[j] == "\\":
                    esc = True
                elif text[j] == "'":
                    j += 1
                    break
                j += 1
            out.append(("char", text[i:j]))
            i = j
        else:
            buf.append(c)
            i += 1
    if buf:
        out.append(("code", "".join(buf)))
    return out


DECL = re.compile(r"(?:^|[;{}])\s*(?:@\w+(?:\([^)]*\))?\s*)*"
                  r"(?:[\w<>\[\],.?]+\s+)+(\w+)\s*(?:\(|;|=)")


def declared_names(text: str) -> Tuple[Set[str], Set[str], Set[str]]:
    """返回 (本文件声明的成员名, @Shadow/@Overwrite 声明的成员名, @Unique 声明的成员名)。

    注意：@Shadow/@Overwrite 与普通声明会同时被 DECL 正则命中，所以必须单独跟踪 @Unique，
    不能用 shadow_like - normal 来求"强制改名集合"（那会把 @Shadow 的意图抵消掉）。
    """
    normal: Set[str] = set()
    overwrite: Set[str] = set()
    unique: Set[str] = set()
    for m in re.finditer(r"@(Shadow|Overwrite|Unique)\b", text):
        tag = m.group(1)
        seg = text[m.end():m.end() + 400]
        dm = re.search(r"(\w+)\s*(?:\(|;|=)", seg)
        if not dm:
            continue
        if tag == "Unique":
            unique.add(dm.group(1))
            normal.add(dm.group(1))
        else:
            overwrite.add(dm.group(1))
    for m in DECL.finditer(text):
        normal.add(m.group(1))
    return normal, overwrite, unique


def remap_descriptor_classes(desc: str, renamer: Renamer, stats: Dict[str, int]) -> str:
    def sub(m: re.Match) -> str:
        internal = m.group(1)
        mapped = renamer.map_class_internal(internal)
        if mapped:
            stats["desc_class"] += 1
            return "L" + mapped + ";"
        return m.group(0)
    return re.sub(r"L([^;]+);", sub, desc)


def remap_string_payload(s: str, owner_internal: Optional[str], renamer: Renamer,
                         stats: Dict[str, int], findings: List[str], where: str) -> str:
    """处理注解字符串：类名 + 方法/字段名 + 描述符。"""
    # 1) 内部名/点号类名
    def cls_sub(m: re.Match) -> str:
        raw = m.group(0)
        dotted = raw.replace("/", ".")
        got = renamer.resolve_dotted(dotted)
        if got:
            stats["str_class"] += 1
            return got[1] if "/" in raw else to_source_fqn(got[1])
        return raw
    s = FQN_INTERNAL.sub(cls_sub, s)
    s = FQN_DOTTED.sub(cls_sub, s)

    # 2) 形如 name(desc)ret / name(desc) / name
    m = re.fullmatch(r"\s*([\w$<>]+)\s*(\([^)]*\))?\s*(.*)", s, re.S)
    if not m:
        return s
    name, desc, tail = m.group(1), m.group(2) or "", m.group(3) or ""
    if name in ("<init>", "<clinit>"):
        new_desc = remap_descriptor_classes(desc, renamer, stats) if desc else desc
        return name + new_desc + tail
    if re.fullmatch(r"[\w$]+", name):
        kind = "method" if desc else "field"
        mapped = renamer.map_member(owner_internal, name, kind)
        if mapped is None:
            # 属主已知但按属主查不到（例如 @Accessor 只有名字、拿不到描述符）：
            # 回退到「全局唯一」映射，并单独计数以便复核
            mapped = renamer.map_member(owner_internal, name, "method" if kind == "field" else "field")
        if mapped is None:
            g = renamer.global_member(name)
            if g:
                stats["str_member_global"] = stats.get("str_member_global", 0) + 1
                mapped = g
        if mapped is None and (name in renamer.method_by_name or name in renamer.field_by_name):
            cands = sorted((renamer.member_by_owner.get((owner_internal, name)) or set())
                           | (renamer.method_by_name.get(name) or set())
                           | (renamer.field_by_name.get(name) or set()))
            findings.append(f"{where}: 成员 {name} 无法唯一映射（候选官方名: {', '.join(cands)}）")
        if mapped:
            stats["str_member"] += 1
            name = mapped
    if desc:
        desc = remap_descriptor_classes(desc, renamer, stats)
    return name + desc + tail


ANNOTATION_ARG = re.compile(r'(@(?:' + "|".join(MEMBER_ANNOTATIONS + METHOD_STRING_ANNOTATIONS) + r')\s*\([^)]*?)((?:method|target|value|at)\s*=\s*)?"([^"]*)"')


def _mixin_target_name(text: str) -> Optional[str]:
    mt = MIXIN_TARGETS.search(text)
    if not mt:
        return None
    body = mt.group(1)
    ts = TARGETS_STR.search(body)
    if ts:
        return ts.group(1)
    cm = re.search(r"([\w.]+)\s*\.class", body)
    return cm.group(1) if cm else None


def build_simple_index(text: str, renamer: "Renamer") -> Dict[str, str]:
    """从（原始）文本的 import 建立 简单名 -> Yarn internal 的索引。"""
    idx: Dict[str, str] = {}
    for m in re.finditer(r"import\s+(?:static\s+)?([\w.]+)\s*;", text):
        got = renamer.resolve_dotted(m.group(1))
        if got:
            idx[m.group(1).split(".")[-1]] = got[0]
    return idx


def annotation_spans(text: str) -> List[Tuple[int, int]]:
    """返回所有注解的 [start, end) 跨度（括号配对，跳过字符串），用于定位注解参数里的字符串。"""
    spans: List[Tuple[int, int]] = []
    for m in re.finditer(r"@(\w+)", text):
        i = text.find("(", m.end())
        if i < 0:
            continue
        depth, j = 0, i
        while j < len(text):
            c = text[j]
            if c == '"':
                j += 1
                while j < len(text) and text[j] != '"':
                    if text[j] == "\\":
                        j += 1
                    j += 1
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        spans.append((m.start(), min(j + 1, len(text))))
    return spans


def resolve_source_class(name: Optional[str], simple_index: Dict[str, str],
                         renamer: "Renamer") -> Optional[str]:
    """把源码里的类引用（全限定名，或依赖 import 的简单名/内部类写法）解析成 Yarn internal。"""
    if not name:
        return None
    got = renamer.resolve_dotted(name)
    if got:
        return got[0]
    parts = name.split(".")
    base = simple_index.get(parts[0])
    if base is None:
        return None
    cand = base + ("$" + "$".join(parts[1:]) if len(parts) > 1 else "")
    return cand if cand in renamer.class_map else None


ACCESSOR_DECL = re.compile(
    r"@(Accessor|Invoker)\s*(?:\(\s*([^)]*)\))?\s*(?:[\w<>\[\],.\s]+?)\s+([\w$]+)\s*\(")
ACCESSOR_PREFIXES = ("get", "set", "is")


def decapitalize(name: str) -> str:
    """等价于 java.beans.Introspector#decapitalize：前两个字符都是大写时保持不变
    （全大写常量如 BLENDING_CHUNK_DISTANCE_THRESHOLD 不能被改成 bLENDING_...）。"""
    if len(name) >= 2 and name[1].isupper():
        return name
    return name[:1].lower() + name[1:]


def split_prefixed_name(name: str, prefixes: Sequence[str]) -> Tuple[str, str]:
    for p in prefixes:
        if name.startswith(p) and len(name) > len(p) and name[len(p)].isupper():
            return p, name[len(p):]
    return "", name


def split_accessor_name(name: str) -> Tuple[str, str]:
    """getChunkManager -> ("get", "ChunkManager")；不符合 get/set/is 约定则返回 ("", name)。"""
    return split_prefixed_name(name, ACCESSOR_PREFIXES)


def collect_accessor_renames(files: Iterable[pathlib.Path], renamer: "Renamer",
                             root: pathlib.Path) -> Tuple[Dict[str, Dict[str, str]],
                                                          Dict[str, str], List[str]]:
    """预扫描所有文件：@Accessor / @Invoker 不带值时，方法名编码了目标字段/方法名，
    必须一起改名（声明与调用点都要改，所以先收集成全局表）。

    返回 (每文件改名表, 全局改名表, 告警)
    """
    per_file: Dict[str, Dict[str, str]] = {}
    global_map: Dict[str, str] = {}
    ambiguous: Set[str] = set()
    findings: List[str] = []
    for p in files:
        text = p.read_text(encoding="utf-8")
        simple_index = build_simple_index(text, renamer)
        owner = resolve_source_class(_mixin_target_name(text), simple_index, renamer)
        if owner is None:
            continue
        local: Dict[str, str] = {}
        for m in ACCESSOR_DECL.finditer(text):
            kind, value, name = m.group(1), (m.group(2) or "").strip(), m.group(3)
            if value.startswith('"'):
                continue                      # 显式写了成员名，方法名可随意，无需改
            if kind == "Invoker":
                # Mixin 约定：@Invoker 方法名以 invoke 开头时，去掉前缀并 decapitalize 才是目标方法名
                prefix, rest = split_prefixed_name(name, ("invoke",))
                target = decapitalize(rest) if prefix else name
                mt = renamer.map_member(owner, target, "method") or renamer.global_member(target)
                if mt is None:
                    mapped = None
                else:
                    mapped = (prefix + mt[:1].upper() + mt[1:]) if prefix else mt
            else:
                prefix, rest = split_accessor_name(name)
                field = decapitalize(rest)
                mapped_field = renamer.map_member(owner, field, "field") or renamer.global_member(field)
                mapped = (prefix + mapped_field[:1].upper() + mapped_field[1:]) if mapped_field else None
            if not mapped or mapped == name:
                if mapped is None:
                    findings.append(f"{p.relative_to(root).as_posix()}: @{kind} {name} "
                                    f"推导出的目标无法映射（需人工确认）")
                continue
            local[name] = mapped
            prev = global_map.get(name)
            if prev is not None and prev != mapped:
                ambiguous.add(name)
            global_map[name] = mapped
        if local:
            per_file[str(p)] = local
    for name in ambiguous:
        global_map.pop(name, None)
        findings.append(f"访问器方法名 {name} 在不同文件里映射结果不一致，已跳过（需人工确认）")
    return per_file, global_map, findings


def process_file(path: pathlib.Path, renamer: Renamer, root: pathlib.Path,
                 stats: Dict[str, int], findings: List[str],
                 accessor_local: Optional[Dict[str, str]] = None,
                 accessor_global: Optional[Dict[str, str]] = None) -> Tuple[str, bool]:
    accessor_local = accessor_local or {}
    accessor_global = accessor_global or {}
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(root).as_posix()
    original = text

    # ---- 0) 先用原始文本解析 import 与 @Mixin 属主（后面的解析都以此为依据）----
    simple_index = build_simple_index(original, renamer)
    owner_internal = resolve_source_class(_mixin_target_name(original), simple_index, renamer)
    if _mixin_target_name(original) is not None:
        stats["mixin_class_resolved"] += 1 if owner_internal else 0
        if owner_internal is None:
            findings.append(f"{rel}: @Mixin 目标 {_mixin_target_name(original)} 未能解析为 MC 类")

    # ---- 1) import 的类名 -------------------------------------------------
    imports: Dict[str, str] = {}      # yarn 简单名 -> Mojang 简单名（注意：存“简单名”，不能存完整路径）
    def import_sub(m: re.Match) -> str:
        prefix, fqn, semi = m.group(1), m.group(2), m.group(3)
        got = renamer.resolve_dotted(fqn)
        if got:
            _, mojang = got
            stats["import"] += 1
            mapped_fqn = to_source_fqn(mojang)
            imports[fqn.split(".")[-1]] = mapped_fqn.split(".")[-1]   # 代码里用的是简单名
            return f"{prefix}{mapped_fqn}{semi}"
        if fqn.startswith("net.minecraft.") and not renamer.is_mojang_class(fqn):
            # 已经是官方名的 import 不算问题（例如二次运行时，或本来就是 Mojang 类）
            findings.append(f"{rel}: import 未能映射: {fqn}")
        return m.group(0)
    text = re.sub(r"(import\s+(?:static\s+)?)([\w.]+)(\s*;)", import_sub, text)

    # ---- 1.5) @Mixin(<类引用>.class)：整体重映射，保证内部类 $ 与 . 也对 ---
    def mixin_class_sub(m: re.Match) -> str:
        head, ref = m.group(1), m.group(2)
        name = ref[: -len(".class")].strip()
        got = resolve_source_class(name, simple_index, renamer)
        if got:
            stats["mixin_class_remapped"] = stats.get("mixin_class_remapped", 0) + 1
            return head + to_source_fqn(renamer.class_map[got]) + ".class"
        return m.group(0)
    text = re.sub(r"(@Mixin\s*\([^)]*?)([\w.]+\s*\.class)", mixin_class_sub, text)

    # ---- 1.6) @Accessor/@Invoker 的方法声明名（不带值时由方法名推导目标）----
    if accessor_local:
        def acc_sub(m: re.Match) -> str:
            name = m.group(3)
            if name not in accessor_local:
                return m.group(0)
            stats["accessor_decl"] = stats.get("accessor_decl", 0) + 1
            s, e = m.start(3) - m.start(0), m.end(3) - m.start(0)
            whole = m.group(0)
            return whole[:s] + accessor_local[name] + whole[e:]
        text = ACCESSOR_DECL.sub(acc_sub, text)

    # ---- 1.7) 代码里「外层类.内部类」的限定引用（如 StorageIoWorker.Result）----
    # 这类引用里内部类名不带 import，token 通道改不到，必须整体解析
    def inner_sub(m: re.Match) -> str:
        outer, inner = m.group(1), m.group(2)
        base = simple_index.get(outer)
        if base is None:
            return m.group(0)
        mapped = renamer.class_map.get(base + "$" + inner)
        if mapped is None:
            return m.group(0)
        stats["code_inner"] = stats.get("code_inner", 0) + 1
        if outer in simple_index:      # 外层类本来就有 import，输出简单名形式
            rest = mapped.rpartition("/")[2]
            outer_simple = rest.split("$")[0]
            inner_simple = rest.split("$", 1)[1].replace("$", ".") if "$" in rest else inner
            return f"{outer_simple}.{inner_simple}"
        return to_source_fqn(mapped)
    text = QUALIFIED_INNER.sub(inner_sub, text)

    # ---- 2) 注解里的字符串（含数组形式 method = { "a", "b" } 与多行写法）----
    # 做法：找出所有注解跨度，凡落在注解里的字符串字面量都按映射负载处理；
    #       普通字符串（日志等）不受影响，因为它们不在注解里。
    ann_spans = annotation_spans(text)

    # ---- 3) 代码 token ----------------------------------------------------
    normal, overwrite, unique = declared_names(text)
    forced = overwrite - unique

    def _receiver_is_self_or_none(start: int) -> bool:
        """token 前面若不是点号（声明/无接收者调用），或点号前是 this/super，才算指向本混入目标。"""
        if start == 0 or seg[start - 1] != ".":
            return True
        j = start - 2
        while j >= 0 and (seg[j].isalnum() or seg[j] in "_$"):
            j -= 1
        return seg[j + 1:start - 1] in ("this", "super")

    def code_sub(m: re.Match) -> str:
        tok = m.group(0)
        if tok in imports:
            stats["code_class"] += 1
            return imports[tok]
        if tok in accessor_global:
            # @Accessor/@Invoker 推导出的改名：这些方法名是我们生成的接口方法，
            # 调用点通常写在别的对象上（如 i.getChunkManager()），因此不加接收者限制
            stats["accessor_call"] = stats.get("accessor_call", 0) + 1
            return accessor_global[tok]
        if tok in forced:
            # @Shadow/@Overwrite 的成员一定属于混入目标类：优先按属主解析，再退回全局唯一。
            # 注意：只能改「声明/this.调用/无接收者调用」，否则会误伤其它对象上的同名方法
            # （曾经把 DataOutputStream.write(data) 改成 out.runStore(data)）
            if not _receiver_is_self_or_none(m.start()):
                return tok
            mapped = (renamer.map_member(owner_internal, tok, "method")
                      or renamer.map_member(owner_internal, tok, "field")
                      or renamer.global_member(tok))
            if mapped is None:
                cands = sorted(renamer.member_by_owner.get((owner_internal, tok)) or set())
                findings.append(f"{rel}: @Shadow/@Overwrite 成员 {tok} 无法全局唯一映射"
                                f"（本属主候选官方名: {', '.join(cands)}）")
                return tok
            stats["code_member_forced"] += 1
            return mapped
        if tok in normal and tok not in accessor_local:
            return tok
        got = renamer.global_member(tok)
        if got and got != tok:
            stats["code_member"] += 1
            return got
        return tok

    out: List[str] = []
    offset = 0
    for kind, seg in split_code(text):
        orig_len = len(seg)
        if kind == "str" and any(s <= offset < e for s, e in ann_spans):
            value = seg[1:-1]
            new_value = remap_string_payload(value, owner_internal, renamer, stats, findings, f"{rel} 注解字符串")
            if new_value != value:
                seg = '"' + new_value + '"'
        elif kind == "code":
            # 先把 Yarn 全限定名整体换成 Mojang 全限定名
            seg = FQN_DOTTED.sub(
                lambda m: (lambda g: to_source_fqn(g[1]) if g else m.group(0))(renamer.resolve_dotted(m.group(0))),
                seg)
            # 再保护「包路径式点号链」（小写包名 + 大写类名，例如 net.minecraft.world.level.Level）：
            # 链内一律不做 token 替换，否则包名分量会被成员名映射误伤
            # （曾经出现 net.minecraft.world.level.X 里的 level 被改成 heightAccessor 这类事故）
            spans = [(mm.start(), mm.end()) for mm in PROTECTED_CHAIN.finditer(seg)]

            def _sub(mm: re.Match) -> str:
                if any(s <= mm.start() and mm.end() <= e for s, e in spans):
                    return mm.group(0)
                return code_sub(mm)

            seg = IDENT.sub(_sub, seg)
        out.append(seg)
        offset += orig_len
    text = "".join(out)

    return text, text != original


# ---------------------------------------------------------------------------
# 自测
# ---------------------------------------------------------------------------
def selftest() -> int:
    fails = 0

    def check(name: str, cond: bool, extra: str = "") -> None:
        nonlocal fails
        print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"  {extra}"))
        if not cond:
            fails += 1

    print("== remap_src 自测 ==")
    # 用一个仅含少量条目的合成重命名器测试各条替换路径
    r = Renamer.__new__(Renamer)
    r.class_map = {"net/minecraft/server/world/ServerChunkManager": "net/minecraft/server/level/ServerChunkCache",
                   "net/minecraft/world/storage/StorageIoWorker$Result": "net/minecraft/world/level/chunk/storage/IOWorker$PendingStore"}
    r.method_by_name = {"getChunkManager": {"getChunkSource"}, "tick": {"tick", "aiStep"}}
    r.field_by_name = {"chunkManager": {"chunkSource"}}
    r.member_by_owner = {("net/minecraft/server/world/ServerChunkManager", "getChunkManager"): {"getChunkSource"},
                         ("net/minecraft/server/world/ServerChunkManager", "chunkManager"): {"chunkSource"},
                         ("net/minecraft/world/storage/StorageIoWorker$Result", "nbt"): {"data"}}
    r.member_desc_by_owner = {}
    r.unmapped_classes = []
    r.mojang_classes = {"net/minecraft/world/level/Level",
                        "net/minecraft/server/level/ServerChunkCache",
                        "net/minecraft/world/level/chunk/storage/IOWorker$PendingStore"}
    # 夹具：IOWorker 自身与它的 write->runStore 映射（接收者保护用例需要）
    r.class_map["net/minecraft/world/level/chunk/storage/IOWorker"] = "net/minecraft/world/level/chunk/storage/IOWorker"
    r.member_by_owner[("net/minecraft/world/level/chunk/storage/IOWorker", "write")] = {"runStore"}
    r.chain = None

    check("点号 FQN 解析（含内部类 . -> $）",
          r.resolve_dotted("net.minecraft.world.storage.StorageIoWorker.Result")
          == ("net/minecraft/world/storage/StorageIoWorker$Result",
              "net/minecraft/world/level/chunk/storage/IOWorker$PendingStore"))
    check("全局唯一成员可映射", r.global_member("getChunkManager") == "getChunkSource")
    check("歧义成员不映射（tick 有多个目标）", r.global_member("tick") is None)
    check("按属主解析成员", r.map_member("net/minecraft/world/storage/StorageIoWorker$Result", "nbt", "field") == "data")

    stats = {k: 0 for k in ("import", "code_class", "code_member", "code_member_forced", "str_class",
                            "str_member", "desc_class", "mixin_targets_str", "mixin_targets_fixed",
                            "mixin_class_resolved")}
    findings: List[str] = []
    src = (
        "import net.minecraft.server.world.ServerChunkManager;\n"
        "@Mixin(ServerChunkManager.class)\n"
        "public abstract class MixinServerChunkManager {\n"
        "    @Shadow protected abstract StorageIoWorker.Result getResult();\n"
        "    @Accessor(\"chunkManager\") void c2me$setChunkManager();\n"
        "    @Inject(method = \"getChunkManager()Lnet/minecraft/server/world/ServerChunkManager;\", at = @At(\"HEAD\"))\n"
        "    private void onTick() { this.getChunkManager(); ServerChunkManager s = null; }\n"
        "}\n"
    )
    tmp = pathlib.Path(__import__("tempfile").mkdtemp()) / "MixinServerChunkManager.java"
    tmp.write_text(src, encoding="utf-8")
    out, changed = process_file(tmp, r, tmp.parent, stats, findings)
    check("import 类名已替换", "import net.minecraft.server.level.ServerChunkCache;" in out, out)
    check("代码类名已替换", "ServerChunkCache s = null;" in out, out)
    check("全局唯一方法名已替换", "this.getChunkSource();" in out, out)
    check("注解字符串里的成员与方法名已替换",
          'method = "getChunkSource()Lnet/minecraft/server/level/ServerChunkCache;"' in out, out)
    check("注解字符串里的字段名已替换", '@Accessor("chunkSource")' in out, out)
    # 属主下查不到时应回退到全局唯一映射
    r.field_by_name["lonelyField"] = {"lonelyFieldMapped"}
    src2 = src.replace('@Accessor("chunkManager")', '@Accessor("lonelyField")')
    tmp2 = tmp.with_name("MixinSecond.java")
    tmp2.write_text(src2, encoding="utf-8")
    out2, _ = process_file(tmp2, r, tmp2.parent, stats, [])
    check("属主查不到时回退全局唯一映射", '@Accessor("lonelyFieldMapped")' in out2, out2)

    # --- 回归测试：import 简单名必须映射成简单名（曾经误存完整路径，拼出双前缀）---
    check("代码里的类名不会被替换成完整路径（无双前缀）",
          "net.minecraft.net.minecraft" not in out and "ServerChunkCache s = null;" in out
          and "net.minecraft.server.level.ServerChunkCache s = null;" not in out, out)
    # --- 回归测试：包路径分量不能被成员名替换（Yarn 里有名为 level 的成员）---
    r.method_by_name["level"] = {"heightAccessor"}
    src3 = "import net.minecraft.world.level.Level;\npublic class T { void f(Level l) { net.minecraft.world.level.Level x; } }\n"
    tmp3 = tmp.with_name("T.java")
    tmp3.write_text(src3, encoding="utf-8")
    out3, _ = process_file(tmp3, r, tmp3.parent, stats, [])
    check("包路径分量不被成员名替换",
          "net.minecraft.world.heightAccessor.Level" not in out3, out3)
    # --- @Mixin 内部类引用整体重映射 ---
    r.class_map["net/minecraft/entity/ai/brain/task/ShuffledList"] = "net/minecraft/world/entity/ai/behavior/ShufflingList"
    r.class_map["net/minecraft/entity/ai/brain/task/ShuffledList$Entry"] = "net/minecraft/world/entity/ai/behavior/ShufflingList$WeightedEntry"
    src4 = ('import net.minecraft.entity.ai.brain.task.ShuffledList;\n'
            '@Mixin(ShuffledList.Entry.class)\npublic interface I {}\n')
    tmp4 = tmp.with_name("I.java")
    tmp4.write_text(src4, encoding="utf-8")
    out4, _ = process_file(tmp4, r, tmp4.parent, stats, [])
    check("@Mixin 内部类引用被整体重映射",
          "@Mixin(net.minecraft.world.entity.ai.behavior.ShufflingList.WeightedEntry.class)" in out4, out4)
    # --- @Accessor 不带值：方法名编码字段名，声明与调用点都要改 ---
    src5 = ('import net.minecraft.server.world.ServerChunkManager;\n'
            '@Mixin(ServerChunkManager.class)\n'
            'public interface IFoo {\n'
            '    @Accessor\n'
            '    int getChunkManager();\n'
            '}\n'
            'class Use { void f(IFoo i) { i.getChunkManager(); } }\n')
    tmp5 = tmp.with_name("IFoo.java")
    tmp5.write_text(src5, encoding="utf-8")
    acc_local, acc_global, acc_warn = collect_accessor_renames([tmp5], r, tmp.parent)
    check("访问器改名被推导出来（getChunkManager -> getChunkSource）",
          acc_global.get("getChunkManager") == "getChunkSource", str(acc_global))
    out5, _ = process_file(tmp5, r, tmp.parent, stats, [],
                           accessor_local=acc_local.get(str(tmp5)), accessor_global=acc_global)
    check("访问器声明名已改", "int getChunkSource();" in out5, out5)
    check("访问器调用点已改", "i.getChunkSource();" in out5, out5)
    # --- @Invoker 带 invoke 前缀：先去前缀 decapitalize 再映射，然后还原前缀 ---
    r.member_by_owner[("net/minecraft/server/world/ServerChunkManager", "setWatchDistance")] = {"setViewDistance"}
    src6 = ('import net.minecraft.server.world.ServerChunkManager;\n'
            '@Mixin(ServerChunkManager.class)\n'
            'public interface IBar {\n'
            '    @Invoker\n'
            '    void invokeSetWatchDistance(int i);\n'
            '}\n')
    tmp6 = tmp.with_name("IBar.java")
    tmp6.write_text(src6, encoding="utf-8")
    acc_local6, acc_global6, _ = collect_accessor_renames([tmp6], r, tmp.parent)
    check("@Invoker invoke 前缀目标名推导正确",
          acc_global6.get("invokeSetWatchDistance") == "invokeSetViewDistance", str(acc_global6))
    # --- 代码里「外层类.内部类」限定引用（内部类名不带 import，token 通道改不到）---
    r.class_map["net/minecraft/world/storage/StorageIoWorker"] = "net/minecraft/world/level/chunk/storage/IOWorker"
    src7 = ('import net.minecraft.world.storage.StorageIoWorker;\n'
            'public class T7 { StorageIoWorker.Result r; }\n')
    tmp7 = tmp.with_name("T7.java")
    tmp7.write_text(src7, encoding="utf-8")
    out7, _ = process_file(tmp7, r, tmp7.parent, stats, [])
    check("代码里外层类.内部类引用被整体重映射",
          "IOWorker.PendingStore r;" in out7, out7)
    # --- 接收者保护：其它对象上的同名方法不能被 @Shadow 改名误伤 ---
    src8 = ('import net.minecraft.world.level.ChunkPos;\n'
            'import net.minecraft.world.level.chunk.storage.IOWorker;\n'
            '@Mixin(net.minecraft.world.level.chunk.storage.IOWorker.class)\n'
            'public abstract class T8 {\n'
            '    @Shadow protected abstract void write(ChunkPos pos, IOWorker.PendingStore r);\n'
            '    void f(java.io.DataOutputStream out, byte[] data) throws Exception {\n'
            '        out.write(data);\n'
            '        this.write(null, null);\n'
            '    }\n'
            '}\n')
    tmp8 = tmp.with_name("T8.java")
    tmp8.write_text(src8, encoding="utf-8")
    out8, _ = process_file(tmp8, r, tmp8.parent, stats, [])
    check("out.write(data) 未被误改（接收者保护）", "out.write(data);" in out8, out8)
    check("声明与 this.write 已按属主改名",
          "runStore(ChunkPos pos, IOWorker.PendingStore r)" in out8 and "this.runStore(null, null);" in out8, out8)
    check("统计计数非零", stats["import"] >= 1 and stats["code_class"] >= 1 and stats["str_member"] >= 1, str(stats))
    check("无意外 finding", all("未能" not in f for f in findings), str(findings))
    print(f"== 失败 {fails} 项 ==")
    return 1 if fails else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Yarn -> Mojang 源码 remap")
    ap.add_argument("--src", default="src/main/java")
    default_mappings = pathlib.Path(__import__("tempfile").gettempdir()) / "mc-mappings"
    ap.add_argument("--yarn", default=str(default_mappings / "yarn.tiny"))
    ap.add_argument("--intermediary", default=str(default_mappings / "intermediary.tiny"))
    ap.add_argument("--proguard", default=str(default_mappings / "client.txt"))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force", action="store_true", help="即使看起来已重映射过也强制执行")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--check-mixin", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    yarn_p, inter_p, pg_p = pathlib.Path(args.yarn), pathlib.Path(args.intermediary), pathlib.Path(args.proguard)
    for p in (yarn_p, inter_p, pg_p):
        if not p.is_file():
            print(f"[错误] 找不到映射文件: {p}", file=sys.stderr)
            return 2

    root = pathlib.Path(args.src)
    files = sorted(p for p in root.rglob("*.java"))

    yarn_step = aw2at.parse_tiny(yarn_p, reverse=True)          # named -> intermediary
    inter_step = aw2at.parse_tiny(inter_p, reverse=True)        # intermediary -> official(混淆)

    # ---- 预扫描源码：候选成员名 + 引用到的 MC 类（用于给 client.txt 瘦身）----
    candidates: Set[str] = set()
    raw_class_mentions: Set[str] = set()
    for p in files:
        t = p.read_text(encoding="utf-8")
        candidates |= set(IDENT.findall(t))
        raw_class_mentions |= {m.split("/")[-1].split("$")[-1] for m in FQN_INTERNAL.findall(t)}
        raw_class_mentions |= {m.split(".")[-1] for m in FQN_DOTTED.findall(t)}
        for cm in MIXIN_TARGETS.finditer(t):
            tm = TARGETS_STR.search(cm.group(1)) or re.search(r"([\w.]+)\s*\.class", cm.group(1))
            if tm:
                raw_class_mentions.add(tm.group(1).split(".")[-1])
    named_classes = set(yarn_step.class_map.keys())          # 键即 Yarn(named) 名
    referenced = {c for c in named_classes
                  if c.split("/")[-1].split("$")[-1] in raw_class_mentions}
    inter_of_named = dict(yarn_step.class_map)               # named -> intermediary
    keep_owners = {inter_step.class_map.get(inter_of_named.get(c, c), inter_of_named.get(c, c))
                   for c in referenced}
    keep_names: Set[str] = set()
    for tables, target in ((yarn_step.method_map, inter_step.method_map),
                           (yarn_step.field_map, inter_step.field_map)):
        for (y_owner, y_desc, y_name) in tables:
            if y_name not in candidates:
                continue
            i_owner = inter_of_named.get(y_owner, y_owner)
            i_desc = aw2at.remap_desc(y_desc, inter_of_named)
            i_name = tables[(y_owner, y_desc, y_name)]
            obf = target.get((i_owner, i_desc, i_name))
            if obf:
                keep_names.add(obf)

    pg_step = parse_proguard(pg_p, keep_owners=keep_owners, keep_names=keep_names)
    chain = aw2at.Chain([yarn_step, inter_step, pg_step])
    renamer = Renamer(chain, yarn_step, referenced=referenced, candidates=candidates)
    renamer.mojang_classes = set(pg_step.class_map.values())
    print(f"[映射链] named->intermediary->official(混淆)->mojang；类 {len(renamer.class_map)} 条；"
          f"引用到的 MC 类 {len(referenced)} 个；client.txt 保留属主 {len(keep_owners)} / 候选名 {len(keep_names)}；"
          f"方法名 {len(renamer.method_by_name)} 个，字段名 {len(renamer.field_by_name)} 个")
    print(f"[源码] {root} 下 {len(files)} 个 Java 文件")
    ambiguous_m = sum(1 for v in renamer.method_by_name.values() if len(v) > 1)
    ambiguous_f = sum(1 for v in renamer.field_by_name.values() if len(v) > 1)
    print(f"[歧义] 方法名 {ambiguous_m} 个 / 字段名 {ambiguous_f} 个在 MC 内部映射不唯一（这些不参与全局替换）")

    if args.check_mixin:
        print("== @Mixin 目标检查 ==")
        n_targets_str = 0
        n_class = 0
        n_unresolved = 0
        for p in files:
            t = p.read_text(encoding="utf-8")
            idx = build_simple_index(t, renamer)
            name = _mixin_target_name(t)
            if name is None:
                continue
            got = resolve_source_class(name, idx, renamer)
            if TARGETS_STR.search(MIXIN_TARGETS.search(t).group(1)):
                n_targets_str += 1
            else:
                n_class += 1
            if got:
                mapped = renamer.class_map[got]
                if got != mapped:
                    print(f"  {p.name}: {name} -> {to_source_fqn(mapped)}")
            else:
                n_unresolved += 1
                print(f"  {p.name}: @Mixin({name}) 未能解析为 MC 类（非 MC 类，或名字不在 Yarn 映射里）")
        print(f"  @Mixin 总数 {n_targets_str + n_class}（targets=\"...\" 形式 {n_targets_str} 处，X.class 形式 {n_class} 处）；未解析 {n_unresolved}")
        return 0

    stats = {k: 0 for k in ("import", "code_class", "code_member", "code_member_forced", "str_class",
                            "str_member", "desc_class", "mixin_targets_str", "mixin_targets_fixed",
                            "mixin_class_resolved", "accessor_decl", "accessor_call")}
    findings: List[str] = []
    changed_files = 0

    # ---- 预扫描 @Accessor/@Invoker 改名（声明与调用点必须一致）----
    accessor_per_file, accessor_global, acc_findings = collect_accessor_renames(files, renamer, root)
    findings.extend(acc_findings)
    print(f"[访问器] 需改名的方法 {len(accessor_global)} 个（涉及 {len(accessor_per_file)} 个文件）")

    # ---- 防护闸：看起来已经重映射过就拒绝再次应用（避免二次映射把 Mojang 名再改一遍）----
    if args.apply and not args.force:
        yarn_ish = mojang_ish = 0
        for p in files:
            for m in re.finditer(r"import\s+(?:static\s+)?([\w.]+)\s*;", p.read_text(encoding="utf-8")):
                if renamer.resolve_dotted(m.group(1)):
                    yarn_ish += 1
                elif renamer.is_mojang_class(m.group(1)):
                    mojang_ish += 1
        print(f"[防护闸] 可被 Yarn 映射的 import {yarn_ish} 个；已是官方名的 import {mojang_ish} 个")
        if mojang_ish > 0 and yarn_ish < mojang_ish:
            print("[中止] 源码看起来已经重映射过（已是官方名的 import 占多数）。"
                  "如确实要再跑请加 --force。", file=sys.stderr)
            return 3
    for p in files:
        new_text, changed = process_file(p, renamer, root, stats, findings,
                                        accessor_local=accessor_per_file.get(str(p)),
                                        accessor_global=accessor_global)
        if changed:
            changed_files += 1
            if args.apply:
                p.write_text(new_text, encoding="utf-8")

    print("== 替换统计 ==")
    for k, v in stats.items():
        print(f"  {k:22s} {v}")
    print(f"  改动文件数            {changed_files}")
    print("== 需要人工确认的条目 ==")
    if not findings:
        print("  （无）")
    for f in findings[:80]:
        print("  " + f)
    if len(findings) > 80:
        print(f"  ... 其余 {len(findings) - 80} 条省略")
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(
            {"stats": stats, "findings": findings, "changed_files": changed_files},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[已写出] {args.json}")
    if not args.apply:
        print("[提示] 未加 --apply，文件未改动")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
