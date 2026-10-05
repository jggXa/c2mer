# 第三方组件与许可声明（Third-Party Notices）

本模组是 **C2ME 的 `c2me-base` 模块的 Forge 1.20.1 移植**，以 **MIT** 许可分发；
原始版权声明与许可全文原样保留在 [LICENSE](LICENSE) 中（`Copyright (c) 2021-2024 ishland`），并在其后追加了本次 Forge 移植的版权行（`Copyright (c) 2025 jggXa`）。

为了让二次分发完全合规，下面列出**被打包进产物**与**仅编译期使用**的全部第三方组件及处理方式。

---

## 一、随产物打包（`shadowJar` 已包含）

| 组件 | 版本 | 许可 | 是否重定位/改动 | 许可全文 | 上游 |
|---|---|---|---|---|---|
| MixinExtras | 0.3.6 | MIT | 是（重定位到 `com.ishland.c2me.shaded.mixinextras`） | [`licenses/MixinExtras.txt`](licenses/MixinExtras.txt) | https://github.com/LlamaLad7/MixinExtras |
| `com.ibm.async:asyncutil` | 0.1.0 | Apache-2.0 | 否（原样打包） | [`licenses/Apache-2.0.txt`](licenses/Apache-2.0.txt) | https://github.com/ibm/asyncutil |
| `net.objecthunter:exp4j` | 0.4.8 | Apache-2.0 | 否（原样打包） | [`licenses/Apache-2.0.txt`](licenses/Apache-2.0.txt) | https://www.objecthunter.net/exp4j/ |
| `com.electronwill.night-config:core` / `:toml` | 3.6.5 | LGPL-3.0 | **不打包**（Forge 运行环境自带；本产物不含其字节码） | [`licenses/LGPL-3.0.txt`](licenses/LGPL-3.0.txt)（+ [`licenses/GPL-3.0.txt`](licenses/GPL-3.0.txt)） | https://github.com/TheElectronWill/night-config |

### Apache-2.0 合规说明（asyncutil、exp4j）
* 已在产物中附带许可全文（`licenses/Apache-2.0.txt`），并在本文件与 `mods.toml` 中标注；
* 两个库均**未作任何修改**（原样打包，未重定位、未改字节码）；
* 上游 jar 内**不含 NOTICE 文件**，因此没有额外 NOTICE 需要转载（Apache-2.0 §4(d)）；
* 版权归各自作者所有，本项目不对其主张任何权利。

### LGPL-3.0 说明（NightConfig）—— 现已改为「不打包」
早期构建曾把 NightConfig shadow 进产物，**已修正**。原因：Forge 1.20.1 运行环境**自带** NightConfig
（Forge 自身的配置系统就依赖它），再打一份进模组会触发 Java 模块系统冲突，导致启动失败：

```
java.lang.module.ResolutionException: Modules com.electronwill.nightconfig.toml and c2me_base
export package com.electronwill.nightconfig.toml to module minecraft
```

现在 `com.electronwill.night-config:core` / `:toml` 仅作为 **compileOnly** 编译期依赖，
**不再随本产物分发**，运行时使用 Forge 提供的模块。因此本产物**不含任何 LGPL 代码**。
`licenses/LGPL-3.0.txt` 与 `licenses/GPL-3.0.txt` 仍保留供查证（LGPL-3.0 的条款建立在 GPL-3.0 之上）。
---

## 二、仅编译期使用（**未**打包进产物）

| 组件 | 版本 | 许可 | 用途 |
|---|---|---|---|
| `org.spongepowered:mixin` | 0.8.5 | MIT | 注解处理器（生成 refmap） |
| `org.jetbrains:annotations` | 24.0.1 | Apache-2.0 | 编译期可空性注解（`@NotNull` 等以注解形式可能残留在 class 文件中） |
| `org.ow2.asm:asm-tree` | 9.5 | BSD-3-Clause | 仅编译期引用 |
| Minecraft Forge / Minecraft | 1.20.1-47.2.0 | Forge: LGPL-2.1 / Minecraft: EULA | 编译目标，**未随本产物再分发** |

---

## 三、重新构建（用于验证或替换依赖）

```bash
# 需要 JDK 17，以及 Gradle 8.x（ForgeGradle 6 不支持 Gradle 9）
gradle clean build
# 产物：build/libs/c2me_base-<version>-all-dev.jar
```

---

## 四、上游归属

* 上游项目：**C2ME** — https://github.com/RelativityMC/C2ME-fabric
* 取自分支：`ver/1.20.1`（`c2me-base` 模块）
* 本仓库的改动：由 Fabric/Yarn 生态移植到 Forge 1.20.1，并把全部源码从 Yarn 命名
  改写为 **Mojang 官方（official）命名**；其余实现逻辑保持上游原样。
