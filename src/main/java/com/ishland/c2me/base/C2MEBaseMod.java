package com.ishland.c2me.base;

import com.ishland.c2me.base.common.config.ConfigSystem;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.event.lifecycle.FMLCommonSetupEvent;
import net.minecraftforge.fml.javafmlmod.FMLJavaModLoadingContext;

@Mod(C2MEBaseMod.MOD_ID)
public class C2MEBaseMod {

    /**
     * Forge 的 mod id 只允许 {@code [a-z0-9_]}（见 {@code ModInfo} 的校验），
     * 所以 Fabric 里的 {@code c2me-base} 在这里是 {@code c2me_base}。
     * mixin 配置的文件名（c2me-base.mixins.json）不受这个限制。
     */
    public static final String MOD_ID = "c2me_base";

    public C2MEBaseMod() {
        // Fabric 版用 preLaunch 入口点；Forge 用 mod 事件总线上的生命周期事件
        FMLJavaModLoadingContext.get().getModEventBus().addListener(this::onCommonSetup);
    }

    /**
     * 对应 Fabric 版 {@code PreLaunchEntrypoint#onPreLaunch()}。
     *
     * <p><b>时机差异（重要）</b>：Fabric 的 preLaunch 早于 Minecraft 类加载，而
     * {@link FMLCommonSetupEvent} 在注册表冻结之后才触发。若 {@code flushConfig()} 必须更早执行
     * （例如要让配置在 mixin 应用前落盘），把这一行挪到上面的构造函数里——构造函数同样早于
     * common setup，且仍在 mod 加载线程上。</p>
     */
    private void onCommonSetup(FMLCommonSetupEvent gameEvent) {
        gameEvent.enqueueWork(ConfigSystem::flushConfig);
    }
}
