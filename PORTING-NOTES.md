# C2ME Base：Fabric → Forge 1.20.1 移植说明

目标环境：**Minecraft 1.20.1 / Forge 47.2.0 / JDK 17 / Gradle 8 / official(Mojang) 映射**

## 〇、源码出处（这一版已换成时代匹配的源码）

本目录的源码取自上游 C2ME 的 **`ver/1.20.1`** 分支（不是之前那份 1.21.x 的）：

| 项目 | 本目录（ver/1.20.1） | 之前的 1.21.x 版（已留档在 `../c2me-base-1.21.11`） |
|---|---|---|
| Java 文件 | 83（删掉无用的 ASMUtils 后 82） | 128 |
| accesswidener | 536 字节 / 5 条规则 | 13310 字节 / 100 条规则 |
| mixin 配置 | 只有 c2me-base.mixins.json（41 条） | c2me-base + c2me 父配置（70 条） |
| 1.20.5+ API（CustomPayload 等） | 无 | 有（ExtRenderDistance） |
| 需要的第三方库 | asyncutil、night-config、exp4j、mixinextras | 另加 rxjava、flowsched、oshi、JNA |

**结论**：不再需要 1.21→1.20.1 的 API 降级，只剩 Fabric→Forge 这一件事。

## 一、已完成的改动

| 文件 | 改动 |
|---|---|
| `build.gradle` | Fabric 子模块脚本 → Forge 根构建：ForgeGradle 6.x + MixinGradle + AccessTransformer + shadow + reobf（原文件留档 `build.gradle.fabric-original`） |
| `settings.gradle` | **新增**：ForgeGradle / MixinGradle 插件仓库（该分支没有 flowsched 组合构建） |
| `gradle.properties` | **新增**：目标环境 + 模组元数据 + 依赖版本（取自上游该分支） |
| `src/main/resources/META-INF/mods.toml` | **新增**，由 `fabric.mod.json` 转换 |
| `src/main/resources/pack.mcmeta` | **新增**（pack_format=15） |
| `src/main/resources/META-INF/accesstransformer.cfg` | **新增**，5 条规则，名字已换算为 Mojang 官方名（见第三节） |
| `c2me-base.mixins.json` | 删除 `parent: c2me.mixins.json`（父配置在未移植的根模块里）、补 `refmap` / `minVersion` / `compatibilityLevel: JAVA_17` |
| `C2MEBaseMod.java` | `PreLaunchEntrypoint#onPreLaunch` → `@Mod("c2me_base")` + `FMLCommonSetupEvent` |
| `ModuleEntryPoint.java` | `FabricLoader...getEnvironmentType()==EnvType.CLIENT` → `FMLEnvironment.dist == Dist.CLIENT` |
| `ConfigSystem.java` | 3 处：配置目录、`incompatibleMod()`、跨模组冲突扫描（见第四节） |
| `common/util/ASMUtils.java` | **删除**：本模块零调用，且依赖 Fabric 专有的 `MappingResolver` |
| `tools/aw2at.py` | **新增**：AW→AT 转换器（支持链式映射 + `:reverse` 反向映射 + `--selftest`） |

## 二、依赖（按源码 import 逐个核对）

**随模组打包（shadow）**：`com.ibm.async:asyncutil:0.1.0`、`com.electronwill.night-config:core|toml:3.6.5`、
`net.objecthunter:exp4j:0.4.8`、`io.github.llamalad7:mixinextras-forge:0.3.6`（+ `mixinextras-common` 注解处理器）。

> MixinExtras 在 **Forge 1.20.1 不自带**（FabricLoader 0.15+ / NeoForge 20.2.84+ 才自带），必须随模组打包；
> 按官方 README 对 Shadow 方案的要求做了 `relocate` + `mergeServiceFiles()`。

**只做编译期依赖（MC/Forge 自带）**：`org.jetbrains:annotations`、`org.ow2.asm:asm-tree`；
fastutil / netty / gson / guava / slf4j / Mixin 由 MC 与 Forge 提供。

## 三、AccessTransformer（5 条，名字已用真实映射验证）

AW 是 Yarn 命名，Forge 用 Mojang 官方名。验证方法：把 `yarn-1.20.1+build.1-v2` 与
`intermediary-1.20.1-v2` 反向链式映射得到混淆名，再用 Mojang 官方 `client_mappings` 换成去混淆名
（`tools/aw2at.py` 支持 `--map ...:reverse`）。

| AW（Yarn） | 官方（Mojang 1.20.1） |
|---|---|
| `server/world/ChunkTicketManager$NearbyChunkTicketUpdater` | `net.minecraft.server.level.DistanceManager$PlayerTicketTracker` |
| `server/world/ServerChunkManager$MainThreadExecutor` | `net.minecraft.server.level.ServerChunkCache$MainThreadExecutor` |
| `world/storage/StorageIoWorker$Result` | `net.minecraft.world.level.chunk.storage.IOWorker$PendingStore` |
| `…StorageIoWorker$Result.nbt` | `…IOWorker$PendingStore.data`（官方名不是 nbt） |
| `…StorageIoWorker$Result.future` | `…IOWorker$PendingStore.result`（官方名不是 future） |

## 四、Fabric 耦合的处理（本版共 4 个文件）

| 文件 | 原 Fabric 用法 | 现在的 Forge 写法 |
|---|---|---|
| `C2MEBaseMod` | `PreLaunchEntrypoint` | `@Mod("c2me_base")` + `FMLCommonSetupEvent`（时机差异见类注释） |
| `ModuleEntryPoint` | `FabricLoader...getEnvironmentType()==EnvType.CLIENT` | `FMLEnvironment.dist == Dist.CLIENT`（2 处 + 1 处注释） |
| `ConfigSystem` `configSupplier` | `FabricLoader...getConfigDir()` | `FMLPaths.CONFIGDIR.get()` |
| `ConfigSystem` `incompatibleMod()` | `getModContainer` + `Version` + `VersionPredicate` | `ModList.get().getModContainerById()` + Maven `VersionRange`（`"*"` 视为全匹配） |
| `ConfigSystem` `findModDefinedIncompatibility()` | `getAllMods()` + `customValue("c2me:incompatibleConfig")` | `ModList.get().getMods()` + `IModInfo.getModProperties()`（实际等同无冲突） |
| `ASMUtils` | `MappingResolver`（intermediary→运行时名） | 删除（零调用） |

## 五、剩余工作：82 个 Java 文件的 remap（Yarn → Mojang official）

这些 mixin / accessor 的目标类与成员名都是 Yarn 命名，在 Forge + official 下**无法编译**。
需要的映射材料已备好（在 `%TEMP%\mc-1.20.1\`）：

* `yarn.tiny`（`yarn-1.20.1+build.1-v2.jar` → intermediary→named）
* `intermediary.tiny`（`intermediary-1.20.1-v2.jar` → official(混淆)→intermediary）
* `client.txt`（Mojang 官方映射：混淆→Mojang 名）
* `aw2at.py` 里的链式映射器可直接复用（`Chain.remap_class/remap_method/remap_field`）

**注意**：AT 只用了链的前 3 段（named→intermediary→混淆），这 5 条我再用 client.txt 人工核对后写死；
若要做**全量源码 remap**，需要给工具再加一个 ProGuard 映射读取器（`client.txt`）作为第 4 段，
或直接用 `tiny-remapper`。`@Mixin(targets = "...")` 是字符串常量，remap 工具通常改不到，需要单独处理。

## 六、验证记录

**已验证**

* 全模块 **`net.fabricmc` 引用 = 0**（原 4 文件 9 处）
* 改动过的 3 个 Java 文件：`javac --release 17` **语法错误 0**，26 条错误全部是「包不存在/找不到符号」（预期），
  非包/符号类错误 = 0
* `c2me-base.mixins.json`：JSON 合法，41 条 mixin，`parent` 已移除，`refmap=c2me_base.refmap.json`
* `mods.toml` 展开后 `tomllib` 解析通过：`modId=c2me_base`、`ver=0.2.0+alpha.11+forge.1`、deps=[forge, minecraft]
* `pack.mcmeta` / `fabric.mod.json` JSON 合法
* `accesstransformer.cfg`：5 条规则、0 语法异常
* `tools/aw2at.py --selftest` **23/23 通过**（新增反向映射用例）
* 残留的 `c2me.mixins.json` 引用 = 0

**没验证**

* 没有真正跑 Gradle 构建（本机无 Gradle，且 ForgeGradle 需下载 MC/Forge）：
  `build.gradle` / `settings.gradle` 只是人工审阅 + 与上游/官方文档核对，**未执行**。
  `shadow`（含 MixinExtras 重定位）+ `reobf` 的组合是 Forge 侧最易出错处，需首次真实构建确认。
* 整模块仍无法编译（第五节：82 个 Yarn 命名文件）。
* 之前的 1.21.x 版工作留档在 `../c2me-base-1.21.11`（含它的 PORTING-NOTES），本次未删除。
---

## 九、Remap 结果（Yarn → Mojang official，已完成）

工具：`tools/remap_src.py`（映射链 named→intermediary→official(混淆)→Mojang，逐级由
`yarn.tiny` / `intermediary.tiny` / Mojang `client.txt` 提供；支持 `--report` 干跑、
`--check-mixin` 检查、`--apply` 应用、`--force` 覆盖、"已重映射"防护闸）

替换规模（64 个文件）：

| 类别 | 处数 |
|---|---|
| import 类名 | 121 |
| 代码里的类名 | 121 |
| 注解字符串里的类名 | 7 |
| `@Mixin(X.class)` 目标类 | 42（全部成功；`targets="..."` 形式 0 处） |
| 代码里的成员名（全局唯一才替换） | 106 |
| `@Shadow`/`@Overwrite` 强制替换 | 1 |
| 注解字符串里的成员名 | 6 |
| `@Accessor`/`@Invoker` 声明名（含 invoke 前缀推导） | 35 |
| 访问器调用点 | 1 |

独立验证（`tools/verify_remap.py`）：
* 源码里 73 种 `net.minecraft.*` 引用**全部存在于官方映射**
* 描述符里的 3 种类引用全部存在；**0 行畸形**（无 `net.minecraft.net.minecraft` 之类）
* 全量 `javac --release 17`：**语法错误 0**，非"包/符号"类错误 **0**（100 条"包不存在/找不到符号"属预期：
  本地没有 Forge/MC 依赖）
* 幂等防护：重复 `--apply` 会被防护闸中止（退出码 3）

**仍需人工确认的 8 处死角**（工具已全部列出，未擅自改写）：
1. `ISimpleRandom` `@Invoker invokeSetSeed` — 目标方法名推导不出来（Yarn 里可能叫 `setSeed`，官方名需查）
2. `IThreadedAnvilChunkStorage` `@Invoker invokeSave` — 同上
3. `invokeTick` 在不同文件里映射结果不一致（`ChunkHolder.tick` vs `ServerChunkCache.tick`），已跳过
4. `ChunkLoadScheduleEvent` 注解字符串里的 `status`（候选含 `status` 本身，很可能无需改）
5. `MixinServerChunkManager` `@Inject/@Redirect method = "getChunk"` ×2（候选含 `getChunk`，很可能无需改）
6. `MixinStorageIoWorker` `@Shadow/@Overwrite write` ×2（候选 `runStore`，需人工判断）

## 十、尚未做的验证

* 仍未真正执行 Gradle 构建（本地无 Gradle，且需联网拉 Forge/MC）：
  `build.gradle` 的 shadow + reobf 组合需首次真实构建确认。
* 方法级校验只能覆盖注解里显式引用的成员；**继承来的成员**（Mixin 允许访问父类字段/方法）
  不在按类的官方成员索引里，因此 `verify_members.py` 报的"不存在"可能是误报，
  以上 8 条死角也可能因此略多——以真实编译报错为准。

---

## 十一、许可决策（保持 MIT，附 GPL-3.0 可行性评估）

本移植以 **MIT** 分发，与上游 C2ME 一致。曾评估改判 GPL-3.0，结论存档如下。

### 可行性：成立
* 上游 C2ME 为 MIT，允许再许可（**前提**：必须原样保留版权声明与许可全文，不得删除）；
* 随包依赖与 GPL-3.0 全部兼容：
  * MixinExtras — MIT
  * `com.ibm.async:asyncutil`、`net.objecthunter:exp4j` — Apache-2.0（与 GPLv3 兼容；注意不兼容 GPLv2）
  * `com.electronwill.night-config` — LGPL-3.0（LGPLv3 §4 明确允许组合作品整体按 GPL-3.0 分发）
  * `org.spongepowered:mixin`（MIT）、`org.jetbrains:annotations`（Apache-2.0）、`org.ow2.asm`（BSD-3）— 仅编译期

### 最终选择：保持 MIT
1. 若认定模组构成 Minecraft 的衍生作品，GPL-3.0 会要求**整个组合作品**（含专有的 Minecraft）以 GPL 提供，
   现实不可行 —— 这是模组社区普遍回避 GPLv3 的首要原因，也是上游选 MIT 的原因；
2. GPL-3.0 §7 禁止附加任何额外限制（不能加"禁止商用 / 禁止转载 / 禁止整合包"等条款）；
3. MIT 对整合包与二次搬运更友好，且与上游一致，便于把改进回馈上游（自身改动仍可另以 MIT 提供给上游）；
4. MIT 的合规义务已履行完毕：`LICENSE`（上游 + 移植者版权声明）、`THIRD-PARTY.md`、`licenses/`
   三部分均随 jar 与源码仓库分发；`mods.toml` 声明 `license="MIT"` 且含 `displayURL`。

### 若将来要改判 GPL-3.0（操作清单）
1. `LICENSE` 换成 GPL-3.0 全文（本仓库 `licenses/GPL-3.0.txt` 已备）；
2. **新增 `LICENSE-MIT`** 保留上游 MIT 全文与版权行（不可省略）；
3. 在 `LICENSE` 顶部加入 GPL-3.0 §5(a) 要求的修改声明（说明这是 C2ME `c2me-base` 的 Forge 移植、改动日期）；
4. 同步 `gradle.properties` 的 `mod_license` 与 `THIRD-PARTY.md` 的许可关系；
5. 重新构建并开箱验证产物内含 `LICENSE` 与 `LICENSE-MIT`。
