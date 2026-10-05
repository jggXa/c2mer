#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aw2at.py —— 把 Fabric 的 accessWidener(AW) 转换成 Forge 的 accessTransformer(AT)。

为什么不能只做文本替换：
    Fabric 侧通常用 Yarn 映射（net/minecraft/server/world/ChunkLevelManager），
    Forge 侧（official 映射）用的是 Mojang 名字（net.minecraft.server.level.ChunkMap）。
    纯文本转换会得到“语法正确但名字全错”的 AT —— 构建时找不到类，AT 静默失效。
    所以本脚本支持链式映射：--map yarn.tiny --map intermediary.tiny，
    逐级把类名/成员名/描述符换到目标命名空间。

用法：
    # 1) 仅做语法转换（名字保持原样，会在文件头写明警告）
    python tools/aw2at.py src/main/resources/c2me-base.accesswidener \
        -o src/main/resources/META-INF/accesstransformer.cfg

    # 2) 带映射转换（推荐）：按顺序给出映射文件，逐级套用
    python tools/aw2at.py src/main/resources/c2me-base.accesswidener \
        -o src/main/resources/META-INF/accesstransformer.cfg \
        --map yarn-1.20.1-v2.tiny --map intermediary-1.20.1-v2.tiny

    # 3) 自测（内置小型映射，验证语法转换与链式映射逻辑）
    python tools/aw2at.py --selftest

支持的映射文件：
    * tiny v2（每个文件恰好两个命名空间，如 named→intermediary、intermediary→official）
    * 简单 TSV：每行 “源类名<TAB>目标类名”（只映射类名，成员名不动），用 --map-simple 指定
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# AW → AT 的访问级别对应
#   accessible  → public      （设为可访问）
#   extendable  → public-f    （允许继承/覆写：去 final；AT 无法“只去 final 不改可见性”，
#                              public-f 是通用近似）
#   mutable     → public-f    （字段去 final，可写）
# ---------------------------------------------------------------------------
def at_access(aw_access: str, kind: str) -> str:
    base = aw_access.replace("transitive-", "")
    if base == "accessible":
        return "public"
    if base in ("extendable", "mutable"):
        return "public-f"
    raise ValueError("未知 access 关键字: " + aw_access)


AW_ACCESS = {
    "accessible", "extendable", "mutable",
    "transitive-accessible", "transitive-extendable", "transitive-mutable",
}

CLASS_IN_DESC = re.compile(r"L([^;]+);")


def remap_desc(desc: str, class_map: Dict[str, str]) -> str:
    """把 JVM 描述符里出现的类名替换掉，例如 (Lnet/minecraft/x/Foo;)V"""
    return CLASS_IN_DESC.sub(lambda m: "L" + class_map.get(m.group(1), m.group(1)) + ";", desc)


# ---------------------------------------------------------------------------
# tiny v2 解析
# ---------------------------------------------------------------------------
@dataclass
class Step:
    """一个命名空间到下一个命名空间的映射步骤。"""
    src_ns: str
    dst_ns: str
    class_map: Dict[str, str] = field(default_factory=dict)
    method_map: Dict[Tuple[str, str, str], str] = field(default_factory=dict)  # (srcClass, srcDesc, srcName) -> dstName
    field_map: Dict[Tuple[str, str, str], str] = field(default_factory=dict)


def parse_tiny(path: Path, reverse: bool = False) -> Step:
    """解析 tiny v2 映射文件。

    reverse=True 时把该文件的映射方向反过来用：Fabric 发布的
    ``intermediary-1.20.1-v2.jar`` 里是 official→intermediary、
    ``yarn-1.20.1-v2.jar`` 里是 intermediary→named，而移植时需要反过来的方向。
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].startswith("tiny"):
        raise ValueError(f"{path}: 不是 tiny 映射文件（缺少 tiny 头）")
    header = lines[0].split("\t")
    if len(header) < 4 or header[1] != "2":
        raise ValueError(f"{path}: 只支持 tiny v2（头部: {lines[0][:60]}）")
    nss = header[3:]
    if len(nss) != 2:
        raise ValueError(f"{path}: 期望恰好两个命名空间，实际 {nss}")
    step = Step(nss[0], nss[1])
    cur = ["", ""]
    for raw in lines[1:]:
        if not raw or raw.startswith("#"):
            continue
        if raw.startswith("c\t"):
            names = (raw.split("\t")[1:] + ["", ""])[:2]
            cur = names
            if names[0] and names[1]:
                step.class_map[names[0]] = names[1]
        elif raw.startswith("\t") and not raw.startswith("\t\t"):
            body = raw[1:]
            parts = body.split("\t")
            kind = parts[0]
            if kind not in ("m", "f"):
                continue          # 注释(c)、参数名(p)等忽略
            if len(parts) < 4:
                continue
            desc, src_name, dst_name = parts[1], parts[2], parts[3]
            if not (cur[0] and src_name and dst_name):
                continue
            key = (cur[0], desc, src_name)
            (step.method_map if kind == "m" else step.field_map)[key] = dst_name
    return invert_step(step) if reverse else step


def invert_step(step: Step) -> Step:
    """把一步映射反过来：A→B 变成 B→A（成员键要同时把描述符里的类名换算过去）。"""
    inv = Step(step.dst_ns, step.src_ns)
    inv.class_map = {v: k for k, v in step.class_map.items()}
    for table_src, table_dst in ((step.method_map, inv.method_map),
                                 (step.field_map, inv.field_map)):
        for (cls, desc, name), dst_name in table_src.items():
            table_dst[(step.class_map.get(cls, cls), remap_desc(desc, step.class_map), dst_name)] = name
    return inv


def parse_simple_tsv(path: Path) -> Step:
    step = Step("simple-src", "simple-dst")
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split("\t") if "\t" in line else line.split()
        if len(parts) < 2:
            print(f"[警告] {path}:{lineno}: 忽略无法解析的行: {line}", file=sys.stderr)
            continue
        step.class_map[parts[0].replace(".", "/")] = parts[1].replace(".", "/")
    return step


@dataclass
class Chain:
    steps: List[Step]

    def has_mapping(self) -> bool:
        return bool(self.steps)

    def remap_class(self, cls: str) -> str:
        cur = cls
        for st in self.steps:
            cur = st.class_map.get(cur, cur)
        return cur

    def remap_desc_all(self, desc: str) -> str:
        cur = desc
        for st in self.steps:
            cur = remap_desc(cur, st.class_map)
        return cur

    def remap_member(self, cls: str, desc: str, name: str, kind: str
                     ) -> Optional[Tuple[str, str, str]]:
        """链式查找成员的新名字；任一级查不到返回 None（调用方回退并告警）。"""
        cur_cls, cur_desc, cur_name = cls, desc, name
        for st in self.steps:
            table = st.method_map if kind == "method" else st.field_map
            nxt = table.get((cur_cls, cur_desc, cur_name))
            if nxt is None and kind == "field":
                # 有些映射文件里字段描述符可能缺失，退化为按类+名字查
                nxt = next((v for (c, _d, n), v in table.items() if c == cur_cls and n == cur_name), None)
            if nxt is None:
                return None
            cur_desc = remap_desc(cur_desc, st.class_map)
            cur_cls = st.class_map.get(cur_cls, cur_cls)
            cur_name = nxt
        return cur_cls, cur_desc, cur_name


# ---------------------------------------------------------------------------
# AW 解析与 AT 生成
# ---------------------------------------------------------------------------
@dataclass
class Entry:
    access: str
    kind: str          # class | field | method
    owner: str
    name: str = ""
    desc: str = ""


def parse_aw(path: Path) -> Tuple[str, List[Entry], List[str]]:
    namespace = "named"
    entries: List[Entry] = []
    warns: List[str] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        toks = line.split()
        if toks[0] == "accessWidener":
            if len(toks) < 3:
                warns.append(f"{lineno}: accessWidener 头不完整，按 v1 处理")
            else:
                if toks[1] != "v1":
                    warns.append(f"{lineno}: 声明为 {toks[1]}，本工具完整支持 v1，按 v1 语法解析")
                namespace = toks[2]
            continue
        if len(toks) < 3 or toks[0] not in AW_ACCESS:
            warns.append(f"{lineno}: 无法解析，已跳过: {line}")
            continue
        access, kind = toks[0], toks[1]
        if kind == "class" and len(toks) == 3:
            entries.append(Entry(access, "class", toks[2]))
        elif kind in ("field", "method") and len(toks) == 5:
            entries.append(Entry(access, kind, toks[2], toks[3], toks[4]))
        else:
            warns.append(f"{lineno}: 字段/方法行必须是 5 列，已跳过: {line}")
    return namespace, entries, warns


def convert(namespace: str, entries: Sequence[Entry], chain: Chain
            ) -> Tuple[List[str], List[str]]:
    out: List[str] = []
    warns: List[str] = []
    for e in entries:
        try:
            acc = at_access(e.access, e.kind)
        except ValueError as ex:
            warns.append(f"{ex}（跳过 {e.owner}）")
            continue
        if e.kind == "class":
            out.append(f"{acc} {chain.remap_class(e.owner).replace('/', '.')}")
            continue

        mapped = chain.remap_member(e.owner, e.desc, e.name, e.kind) if chain.has_mapping() else None
        if mapped is None:
            owner = chain.remap_class(e.owner).replace('/', '.')
            name = e.name
            desc = chain.remap_desc_all(e.desc)
            if chain.has_mapping():
                warns.append(f"映射链里找不到成员，保留原名: {e.owner}.{e.name}{e.desc}")
        else:
            owner = mapped[0].replace('/', '.')
            desc = mapped[1]
            name = mapped[2]
        if e.kind == "field":
            out.append(f"{acc} {owner} {name}")          # AT 的字段行不带描述符
        else:
            out.append(f"{acc} {owner} {name}{desc}")    # AT 的方法行：名字紧跟描述符
    return out, warns


HINT = """#
# 由 Fabric accessWidener 转换而来（工具: tools/aw2at.py）
# 源文件: {src}   (AW 命名空间: {ns})
{map_line}#
# Fabric 的 accessWidener 与 Forge 的 accessTransformer 语法对应关系：
#   accessible class  X        ->  public X
#   extendable class  X        ->  public-f X      （AT 无法“只去 final 不改可见性”）
#   accessible method X n (d)  ->  public X n(d)
#   extendable method X n (d)  ->  public-f X n(d)
#   accessible field  X n d    ->  public X n       （AT 字段行不带描述符）
#   mutable    field  X n d    ->  public-f X n
#
"""


def build_at_text(src: Path, namespace: str, at_lines: List[str], warns: List[str],
                  mapped: bool, extra_map_note: str = "") -> str:
    if mapped:
        map_line = "# 已应用命名空间映射（链式）: 名字已换到目标命名空间\n"
    else:
        map_line = ("# ⚠ 未应用任何映射：以下名字仍是 AW 的命名空间（{ns}，通常为 Yarn），"
                    "在 Forge 的 official 映射下**不可用**（AT 会找不到类）。\n"
                    "#   请准备映射文件后重新生成，例如：\n"
                    "#     python tools/aw2at.py {src} -o <输出> \\\n"
                    "#         --map yarn-1.20.1-v2.tiny --map intermediary-1.20.1-v2.tiny\n"
                    ).format(ns=namespace, src=src.as_posix())
    text = HINT.format(src=src.as_posix(), ns=namespace, map_line=map_line)
    if extra_map_note:
        text += extra_map_note
    if warns:
        text += "#\n# 转换期间的告警（%d 条）：\n" % len(warns)
        for w in warns[:200]:
            text += f"#   - {w}\n"
        if len(warns) > 200:
            text += f"#   ... 其余 {len(warns) - 200} 条省略\n"
    text += "#\n\n"
    text += "\n".join(at_lines) + "\n"
    return text


# ---------------------------------------------------------------------------
# 自测：内置一份迷你映射，验证“语法转换”与“链式映射”都对
# ---------------------------------------------------------------------------
def selftest() -> int:
    import tempfile

    failures = 0

    def check(name: str, cond: bool, extra: str = "") -> None:
        nonlocal failures
        if cond:
            print(f"  [OK]   {name}")
        else:
            failures += 1
            print(f"  [FAIL] {name} {extra}")

    print("== aw2at 自测 ==")

    aw = """accessWidener v1 named

# 注释行
accessible class net/minecraft/server/world/ServerChunkManager
extendable class net/minecraft/world/storage/RegionBasedStorage
accessible method net/minecraft/nbt/NbtCompound <init> (Ljava/util/Map;)V
accessible field net/minecraft/server/world/ChunkHolder UNLOADED_WORLD_CHUNK_FUTURE Ljava/util/concurrent/CompletableFuture;
extendable method net/minecraft/world/chunk/AbstractChunkHolder generate (Lnet/minecraft/world/chunk/ChunkGenerationStep;Lnet/minecraft/world/ChunkLoadingManager;)Ljava/util/concurrent/CompletableFuture;
mutable field net/minecraft/world/gen/chunk/AquiferSampler$FluidLevel y I
无法解析的行
"""
    with tempfile.TemporaryDirectory() as td:
        awp = Path(td) / "test.accesswidener"
        awp.write_text(aw, encoding="utf-8")
        ns, entries, warns = parse_aw(awp)
        check("解析出 AW 命名空间", ns == "named", ns)
        check("解析出 6 条规则", len(entries) == 6, str(len(entries)))
        check("无法解析的行产生告警", any("无法解析" in w for w in warns))

        # --- 无映射：语法必须正确 ---
        lines, _w = convert(ns, entries, Chain([]))
        check("accessible class → public", "public net.minecraft.server.world.ServerChunkManager" in lines)
        check("extendable class → public-f", "public-f net.minecraft.world.storage.RegionBasedStorage" in lines)
        check("方法行：名字紧跟描述符，无空格",
              "public net.minecraft.nbt.NbtCompound <init>(Ljava/util/Map;)V" in lines)
        check("字段行：不带描述符",
              "public net.minecraft.server.world.ChunkHolder UNLOADED_WORLD_CHUNK_FUTURE" in lines)
        check("mutable field → public-f",
              "public-f net.minecraft.world.gen.chunk.AquiferSampler$FluidLevel y" in lines)
        check("extendable method → public-f 且描述符保留",
              any(l.startswith("public-f net.minecraft.world.chunk.AbstractChunkHolder generate(") for l in lines))

        # --- 链式映射：Yarn → intermediary → official ---
        # 注意 tiny v2 的格式要求：成员行必须紧跟在它所属的 c 行之后；
        # 成员行的描述符列是**该文件第一个命名空间**的形式
        # （named→intermediary 文件里是 Yarn 名，intermediary→official 文件里是 intermediary 名）
        yarn_tiny = "\n".join([
            "tiny\t2\t0\tnamed\tintermediary",
            "c\tnet/minecraft/server/world/ServerChunkManager\tnet/minecraft/class_3213",
            "c\tnet/minecraft/nbt/NbtCompound\tnet/minecraft/class_2487",
            "\tm\t(Ljava/util/Map;)V\t<init>\t<init>",
            "c\tnet/minecraft/server/world/ChunkHolder\tnet/minecraft/class_3195",
            "\tf\tLjava/util/concurrent/CompletableFuture;\tUNLOADED_WORLD_CHUNK_FUTURE\tfield_9000",
            "c\tnet/minecraft/world/chunk/AbstractChunkHolder\tnet/minecraft/class_99001",
            "\tm\t(Lnet/minecraft/world/chunk/ChunkGenerationStep;Lnet/minecraft/world/ChunkLoadingManager;)Ljava/util/concurrent/CompletableFuture;\tgenerate\tmethod_1",
            "c\tnet/minecraft/world/chunk/ChunkGenerationStep\tnet/minecraft/class_8826",
            "c\tnet/minecraft/world/ChunkLoadingManager\tnet/minecraft/class_3193",
            "c\tnet/minecraft/world/gen/chunk/AquiferSampler$FluidLevel\tnet/minecraft/class_6566$class_6567",
            "\tf\tI\ty\tfield_1",
        ])
        inter_tiny = "\n".join([
            "tiny\t2\t0\tintermediary\tofficial",
            "c\tnet/minecraft/class_3213\tnet/minecraft/server/level/ServerChunkCache",
            "c\tnet/minecraft/class_2487\tnet/minecraft/nbt/CompoundTag",
            "\tm\t(Ljava/util/Map;)V\t<init>\t<init>",
            "c\tnet/minecraft/class_3195\tnet/minecraft/server/level/ChunkHolder",
            "\tf\tLjava/util/concurrent/CompletableFuture;\tfield_9000\tunloadedWorldChunkFuture",
            "c\tnet/minecraft/class_99001\tnet/minecraft/server/level/AbstractChunkHolder",
            "\tm\t(Lnet/minecraft/class_8826;Lnet/minecraft/class_3193;)Ljava/util/concurrent/CompletableFuture;\tmethod_1\tapply",
            "c\tnet/minecraft/class_8826\tnet/minecraft/world/level/chunk/ChunkStep",
            "c\tnet/minecraft/class_3193\tnet/minecraft/world/level/ChunkMap",
            "c\tnet/minecraft/class_6566$class_6567\tnet/minecraft/world/level/levelgen/NoiseChunk$FluidStatus",
            "\tf\tI\tfield_1\tfluidLevel",
        ])
        yp = Path(td) / "yarn.tiny"
        ip = Path(td) / "intermediary.tiny"
        yp.write_text(yarn_tiny, encoding="utf-8")
        ip.write_text(inter_tiny, encoding="utf-8")
        chain = Chain([parse_tiny(yp), parse_tiny(ip)])
        lines2, warns2 = convert(ns, entries, chain)
        check("类名换到 official",
              "public net.minecraft.server.level.ServerChunkCache" in lines2, "\n".join(lines2))
        check("内部类 $ 与包名都换对",
              "public net.minecraft.nbt.CompoundTag <init>(Ljava/util/Map;)V" in lines2)
        check("方法名换对、属主类换对、描述符内的类名也换对",
              "public-f net.minecraft.server.level.AbstractChunkHolder apply("
              "Lnet/minecraft/world/level/chunk/ChunkStep;Lnet/minecraft/world/level/ChunkMap;)"
              "Ljava/util/concurrent/CompletableFuture;" in lines2, "\n".join(lines2))
        check("字段名换对（AT 字段行不带描述符）",
              "public net.minecraft.server.level.ChunkHolder unloadedWorldChunkFuture" in lines2,
              "\n".join(lines2))
        check("mutable 字段换到 official",
              "public-f net.minecraft.world.level.levelgen.NoiseChunk$FluidStatus fluidLevel" in lines2,
              "\n".join(lines2))
        check("链式映射不应产生“找不到成员”告警",
              not any("找不到成员" in w for w in warns2), str(warns2))

        # --- 反向映射（Fabric 发布的 tiny 方向与移植方向相反）---
        step_fwd = parse_tiny(yp)                 # named→intermediary
        step_inv = invert_step(step_fwd)          # intermediary→named
        check("反转后的命名空间正确",
              (step_inv.src_ns, step_inv.dst_ns) == ("intermediary", "named"),
              f"{step_inv.src_ns}->{step_inv.dst_ns}")
        check("反转后类名映射正确",
              step_inv.class_map.get("net/minecraft/class_3213")
              == "net/minecraft/server/world/ServerChunkManager", str(step_inv.class_map.get("net/minecraft/class_3213")))
        check("反转后成员映射正确（描述符里的类名也换算）",
              step_inv.method_map.get(("net/minecraft/class_99001",
                                       "(Lnet/minecraft/class_8826;Lnet/minecraft/class_3193;)"
                                       "Ljava/util/concurrent/CompletableFuture;", "method_1")) == "generate",
              str(list(step_inv.method_map.items())[:2]))
        check("正向+反向套用可还原类名（回到 named）",
              Chain([step_fwd, step_inv]).remap_class("net/minecraft/server/world/ServerChunkManager")
              == "net/minecraft/server/world/ServerChunkManager")

        # --- 映射链断裂要能告警 ---
        chain_broken = Chain([parse_tiny(ip)])   # 直接用 intermediary→official，源名对不上
        lines3, warns3 = convert(ns, entries, chain_broken)
        check("映射链对不上时给出告警", any("找不到成员" in w for w in warns3))
        check("告警时仍产出可解析的 AT 行（回退原名）",
              any(l.startswith("public net.minecraft.server.world.ServerChunkManager") for l in lines3))

        # --- 生成的 AT 文本带正确头部 ---
        text_unmapped = build_at_text(awp, ns, lines, _w, mapped=False)
        text_mapped = build_at_text(awp, ns, lines2, warns2, mapped=True)
        check("未映射时头部有醒目告警", "未应用任何映射" in text_unmapped)
        check("已映射时头部说明已套用映射", "已应用命名空间映射" in text_mapped)

    print(f"== 失败 {failures} 项 ==")
    return 1 if failures else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def validate_at(lines: Sequence[str]) -> List[str]:
    """粗校验 AT 行语法：<access> <class> [member]"""
    ok_access = {"public", "public-f", "protected", "protected-f", "private",
                 "private-f", "default", "default-f"}
    bad: List[str] = []
    for i, line in enumerate(lines, 1):
        body = line.split("#", 1)[0].strip()
        if not body:
            continue
        toks = body.split()
        if len(toks) < 2:
            bad.append(f"第 {i} 行：列数不足: {body}")
            continue
        if toks[0] not in ok_access:
            bad.append(f"第 {i} 行：未知 access 关键字 {toks[0]}")
        if toks[1].startswith("L") and toks[1].endswith(";"):
            bad.append(f"第 {i} 行：类名不应是描述符形式: {toks[1]}")
    return bad


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Fabric accessWidener → Forge accessTransformer 转换器")
    ap.add_argument("input", nargs="?", help="输入 .accesswidener 文件")
    ap.add_argument("-o", "--output", help="输出 accesstransformer.cfg 路径")
    ap.add_argument("--map", action="append", default=[], metavar="TINY[:reverse]",
                    help="tiny v2 映射文件（可重复，按 源→中间→目标 顺序链式套用）；"
                         "文件名后加 :reverse 表示把该文件的方向反过来用")
    ap.add_argument("--map-simple", action="append", default=[], metavar="TSV",
                    help="简单 TSV 类名映射（可重复）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--stdout", action="store_true", help="把结果打印到标准输出而不是写文件")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    if not args.input:
        ap.error("需要指定输入的 .accesswidener 文件（或用 --selftest）")

    src = Path(args.input)
    if not src.is_file():
        print(f"[错误] 找不到输入文件: {src}", file=sys.stderr)
        return 2

    steps: List[Step] = []
    for m in args.map:
        raw, rev = m, False
        if raw.endswith(":reverse"):
            raw, rev = raw[:-len(":reverse")], True
        mp = Path(raw)
        if not mp.is_file():
            print(f"[错误] 找不到映射文件: {mp}", file=sys.stderr)
            return 2
        steps.append(parse_tiny(mp, reverse=rev))
        print(f"[映射] {mp} : {steps[-1].src_ns} → {steps[-1].dst_ns}"
              f"{'（反向使用）' if rev else ''}（类 {len(steps[-1].class_map)} 条）")
    for m in args.map_simple:
        mp = Path(m)
        if not mp.is_file():
            print(f"[错误] 找不到映射文件: {mp}", file=sys.stderr)
            return 2
        steps.append(parse_simple_tsv(mp))
        print(f"[映射] {mp} : 简单 TSV，类 {len(steps[-1].class_map)} 条")

    namespace, entries, warns = parse_aw(src)
    chain = Chain(steps)
    lines, conv_warns = convert(namespace, entries, chain)
    all_warns = warns + conv_warns

    bad = validate_at(lines)
    text = build_at_text(src, namespace, lines, all_warns + bad, mapped=chain.has_mapping())

    if args.stdout or not args.output:
        sys.stdout.write(text)
    else:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"[完成] {src} → {out}")
        print(f"       规则 {len(lines)} 条；告警 {len(all_warns)} 条；"
              f"命名空间映射：{'已应用' if chain.has_mapping() else '未应用(名字仍是 ' + namespace + ')'}")
        if bad:
            print(f"[警告] 有 {len(bad)} 行未通过语法自校验，见文件头注释", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
