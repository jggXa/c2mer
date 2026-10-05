package com.ishland.c2me.base.common.config;

import com.electronwill.nightconfig.core.CommentedConfig;
import com.electronwill.nightconfig.core.file.CommentedFileConfig;
import com.ishland.c2me.base.common.util.BooleanUtils;
import net.minecraftforge.forgespi.language.IModInfo;
import net.minecraftforge.fml.ModContainer;
import net.minecraftforge.fml.ModList;
import net.minecraftforge.fml.loading.FMLPaths;
import org.apache.maven.artifact.versioning.DefaultArtifactVersion;
import org.apache.maven.artifact.versioning.InvalidVersionSpecificationException;
import org.apache.maven.artifact.versioning.VersionRange;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.HashSet;
import java.util.Iterator;
import java.util.Optional;
import java.util.function.Supplier;

public class ConfigSystem {

    public static final Logger LOGGER = LoggerFactory.getLogger("C2ME Config System");

    private static final long CURRENT_CONFIG_VERSION = 3;

    // Fabric: FabricLoader.getInstance().getConfigDir() -> Forge: FMLPaths.CONFIGDIR
    private static final Supplier<CommentedFileConfig> configSupplier =
            () -> CommentedFileConfig.builder(FMLPaths.CONFIGDIR.get().resolve("c2me.toml"))
                    .preserveInsertionOrder()
                    .sync()
                    .build();

    private static final CommentedFileConfig CONFIG;

    private static final HashSet<String> visitedConfig = new HashSet<>();

    static {
        CommentedFileConfig config = configSupplier.get();
        try {
            config.load();
        } catch (Throwable t) {
            config = configSupplier.get();
            config.save();
        }

        Updaters.update(config);
        if (config.getInt("version") != CURRENT_CONFIG_VERSION) {
            config.clear();
            LOGGER.warn("Config version mismatch, resetting config");
            config.set("version", CURRENT_CONFIG_VERSION);
        }

        visitedConfig.add("version");

        CONFIG = config;
    }

    public static void flushConfig() {
        purgeUnusedRecursively("", CONFIG);
        CONFIG.save();
    }

    private static void purgeUnusedRecursively(String prefix, CommentedConfig config) {
        for (Iterator<? extends CommentedConfig.Entry> cursor = config.entrySet().iterator(); cursor.hasNext(); ) {
            CommentedConfig.Entry entry = cursor.next();
            final String key = prefix + "." + entry.getKey();
            if (entry.getValue() instanceof CommentedConfig child) {
                purgeUnusedRecursively(key, child);
                if (child.isEmpty()) {
                    LOGGER.info("Removing config entry {} because it is not used", key);
                    cursor.remove();
                }
            } else if (!visitedConfig.contains(key.substring(".".length()))) {
                LOGGER.info("Removing config entry {} because it is not used", key);
                cursor.remove();
            }
        }
    }

    public static class ConfigAccessor {

        private static final String propertyPrefix = "c2me.base.config.override.";

        private final StringBuilder incompatibilityReason = new StringBuilder();

        private String key;
        private String comment;
        private boolean incompatibilityDetected;

        public ConfigAccessor key(String key) {
            this.key = key;
            markVisited();
            return this;
        }

        public ConfigAccessor comment(String comment) {
            this.comment = comment;
            return this;
        }

        public ConfigAccessor incompatibleMod(String modId, String predicate) {
            try {
                // Fabric: FabricLoader.getInstance().getModContainer(modId) + VersionPredicate
                // Forge : ModList.get().getModContainerById(modId) + Maven 版本区间
                // 同上：ModList 可能尚未初始化（Mixin 插件阶段），此时视为「未安装」而不是崩溃
            final ModList modListForLookup = ModList.get();
            final Optional<? extends ModContainer> optIn = modListForLookup == null
                    ? Optional.empty()
                    : modListForLookup.getModContainerById(modId);
                if (optIn.isPresent()) {
                    final ModContainer modContainer = optIn.get();
                    final String version = modContainer.getModInfo().getVersion().toString();

                    if (versionMatches(predicate, version)) {
                        final String reason = String.format("Incompatible with %s@%s (%s) (defined in c2me)", modId, version, predicate);
                        disableConfigWithReason(reason);
                    }
                }
            } catch (Throwable t) {
                throw new IllegalArgumentException(t);
            }
            return this;
        }

        public long getLong(long def, long incompatibleDef, LongChecks... checks) {
            findModDefinedIncompatibility();
            final String systemPropertyOverride = getSystemPropertyOverride();
            final Object configured = systemPropertyOverride != null ? systemPropertyOverride : CONFIG.get(this.key);
            boolean isDefaultValue;
            if (configured != null) {
                if (String.valueOf(configured).equals("default")) { // default placeholder
                    isDefaultValue = true;
                } else if (!(configured instanceof Number)) { // try to fix config
                    try {
                        CONFIG.set(this.key, Long.valueOf(String.valueOf(configured)));
                        isDefaultValue = false;
                    } catch (NumberFormatException e) {
                        LOGGER.warn("Invalid configured value: {} -> {}", this.key, configured);
                        CONFIG.remove(this.key);
                        isDefaultValue = true;
                    }
                } else {
                    isDefaultValue = false;
                }
            } else {
                isDefaultValue = true;
            }
            generateDefaultEntry(def, incompatibleDef);

            if (this.incompatibilityDetected) return incompatibleDef;
            long configLong = isDefaultValue ? def : CONFIG.getLong(this.key);
            if (checkConfig(configLong, checks)) {
                return configLong;
            } else {
                CONFIG.remove(this.key);
                generateDefaultEntry(def, incompatibleDef);
                return def;
            }
        }

        private boolean checkConfig(long value, LongChecks... checks) {
            for (LongChecks check : checks) {
                if (!check.test(value)) return false;
            }
            return true;
        }

        public boolean getBoolean(boolean def, boolean incompatibleDef) {
            findModDefinedIncompatibility();
            final String systemPropertyOverride = getSystemPropertyOverride();
            final Object configured = systemPropertyOverride != null ? systemPropertyOverride : CONFIG.get(this.key);
            boolean isDefaultValue;
            if (configured != null) {
                if (String.valueOf(configured).equals("default")) { // default placeholder
                    isDefaultValue = true;
                } else if (!(configured instanceof Boolean)) { // try to fix config
                    try {
                        CONFIG.set(this.key, BooleanUtils.parseBoolean(String.valueOf(configured)));
                        isDefaultValue = false;
                    } catch (BooleanUtils.BooleanFormatException e) {
                        LOGGER.warn("Invalid configured value: {} -> {}", this.key, configured);
                        CONFIG.remove(this.key);
                        isDefaultValue = true;
                    }
                } else {
                    isDefaultValue = false;
                }
            } else {
                isDefaultValue = true;
            }
            generateDefaultEntry(def, incompatibleDef);

            return this.incompatibilityDetected ? incompatibleDef : (isDefaultValue ? def : CONFIG.get(this.key));
        }

        public <T extends Enum<T>> T getEnum(Class<T> enumClass, T def, T incompatibleDef) {
            findModDefinedIncompatibility();
            final String systemPropertyOverride = getSystemPropertyOverride();
            final Object configured = systemPropertyOverride != null ? systemPropertyOverride : CONFIG.get(this.key);
            boolean isDefaultValue;
            if (configured != null) {
                if (String.valueOf(configured).equals("default")) {
                    isDefaultValue = true;
                } else {
                    try {
                        CONFIG.set(this.key, Enum.valueOf(enumClass, String.valueOf(configured)));
                        isDefaultValue = false;
                    } catch (IllegalArgumentException e) {
                        LOGGER.warn("Invalid configured value: {} -> {}", this.key, configured);
                        CONFIG.remove(this.key);
                        isDefaultValue = true;
                    }
                }
            } else {
                isDefaultValue = true;
            }
            generateDefaultEntry(def, incompatibleDef);

            return this.incompatibilityDetected ? incompatibleDef : (isDefaultValue ? def : CONFIG.getEnum(this.key, enumClass));
        }

        public String getString(String def, String incompatibleDef) {
            findModDefinedIncompatibility();
            final String systemPropertyOverride = getSystemPropertyOverride();
            final Object configured = systemPropertyOverride != null ? systemPropertyOverride : CONFIG.get(this.key);
            boolean isDefaultValue;
            if (configured != null) {
                if (String.valueOf(configured).equals("default")) { // default placeholder
                    isDefaultValue = true;
                } else if (!(configured instanceof String)) { // try to fix config
                    CONFIG.set(this.key, String.valueOf(configured));
                    isDefaultValue = false;
                } else {
                    isDefaultValue = false;
                }
            } else {
                isDefaultValue = true;
            }
            generateDefaultEntry(def, incompatibleDef);

            return this.incompatibilityDetected ? incompatibleDef : (isDefaultValue ? def : CONFIG.get(this.key));
        }

        /**
         * 版本匹配：Fabric 用 {@code VersionPredicate}（支持 {@code "*"}、{@code "1.2.x"} 等写法），
         * Forge 侧改用 Maven 的版本区间（{@code "[1.0,2.0)"}），并把 {@code "*"} 视为「任何版本都匹配」。
         */
        private static boolean versionMatches(String spec, String version) {
            if (spec == null || spec.isBlank() || "*".equals(spec.trim())) {
                return true;
            }
            try {
                return VersionRange.createFromVersionSpec(spec.trim())
                        .containsVersion(new DefaultArtifactVersion(version));
            } catch (InvalidVersionSpecificationException e) {
                LOGGER.warn("无法解析版本区间 {}（按不匹配处理）", spec, e);
                return false;
            }
        }

        private void findModDefinedIncompatibility() {
            // Fabric 侧读的是各 mod 的 fabric.mod.json 里的 custom 字段 c2me:incompatibleConfig（字符串数组）。
            // Forge 没有等价的 custom 元数据结构，这里改为读 IModInfo#getModProperties()（Forge 的自定义属性映射）。
            // 实际情况：没有 Forge mod 会声明这个键，因此效果等同于「未发现冲突」。
            // Mixin 插件加载阶段（ModuleMixinPlugin#onLoad）会早于 Forge 的 ModList 初始化，
            // 此时 ModList.get() 返回 null（见启动日志：ModuleEntryPoint.<clinit> -> ConfigSystem），
            // 必须直接跳过本检查，否则会 NPE -> ExceptionInInitializerError 导致启动失败。
            final ModList modList = ModList.get();
            if (modList == null) {
                return;
            }
            for (IModInfo modInfo : modList.getMods()) {
                final Object value = modInfo.getModProperties().get("c2me:incompatibleConfig");
                if (value == null) {
                    continue;
                }
                final java.util.Collection<?> keys;
                if (value instanceof java.util.Collection<?> storage) {
                    keys = storage;
                } else if (value instanceof String s) {
                    keys = java.util.List.of(s);
                } else {
                    continue;
                }
                for (Object key : keys) {
                    if (key != null && key.toString().equals(this.key)) {
                        final String reason = String.format("Incompatible with %s@%s (defined in %s)",
                                modInfo.getModId(), modInfo.getVersion(), modInfo.getModId());
                        disableConfigWithReason(reason);
                    }
                }
            }

        }

        private String getSystemPropertyOverride() {
            final String property = System.getProperty(propertyPrefix + this.key);
            if (property != null) LOGGER.info("Setting {} to {} (defined in system property)", this.key, property);
            return property;
        }

        private void disableConfigWithReason(String reason) {
            incompatibilityReason.append("\n ").append(reason);
            if (!Boolean.getBoolean("com.ishland.c2me.base.config.ignoreIncompatibility")) {
                LOGGER.info("Disabling config {}: {}", this.key, reason);
                this.incompatibilityDetected = true;
            } else {
                LOGGER.info("Compatibility issues ignored by system property: {}: {}", this.key, reason);
            }
        }

        private void generateDefaultEntry(Object def, Object incompatibleDef) {
            if (!CONFIG.contains(this.key)) {
                CONFIG.set(this.key, "default");
            }
            final String comment = String.format(" (Default: %s) %s", def, this.comment.replace("\n", "\n "));
            if (this.incompatibilityDetected) {
                CONFIG.setComment(this.key, String.format("%s\n Set to %s for the following reasons: %s ", comment, incompatibleDef, this.incompatibilityReason));
            } else {
                CONFIG.setComment(this.key, comment);
            }
        }

        private void markVisited() {
            visitedConfig.add(this.key);
        }
    }

    public enum LongChecks {
        THREAD_COUNT() {
            @Override
            public boolean test(long value) {
                return value >= 1 && value <= 0x7fff;
            }
        },
        NO_TICK_VIEW_DISTANCE() {
            @Override
            public boolean test(long value) {
                return value >= 2 && value <= 248;
            }
        },
        POSITIVE_VALUES_ONLY() {
            @Override
            public boolean test(long value) {
                return value >= 1;
            }
        };

        public abstract boolean test(long value);

    }

}
