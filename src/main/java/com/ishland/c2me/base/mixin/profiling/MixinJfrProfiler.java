// ===========================================================================
// MIXIN 未启用（未登记进 c2me-base.mixins.json）
// 原因：Mixin 0.8.5 禁止对 net.minecraft.util.profiling.jfr.JfrProfiler 的构造函数注入，
//   报 InvalidInjectionException: Found @Inject targetting a constructor；
//   HEAD 与 INVOKE+Shift.AFTER 两种写法均被拒。上游依赖 MixinExtras 的延迟注入接管来绕过，
//   而该接管在本环境（Forge 47.4.20 / Mixin 0.8.5）未生效。
// 影响：仅丧失「区块加载调度」的自定义 JFR 分析事件，其余功能不受影响；
//   MixinChunkHolder 中以 JvmProfiler.INSTANCE instanceof IVanillaJfrProfiler 作了保护。
// 保留本文件以便将来修好 MixinExtras 接管后重新启用。
// ===========================================================================
package com.ishland.c2me.base.mixin.profiling;

import com.ishland.c2me.base.common.profiling.ChunkLoadScheduleEvent;
import com.ishland.c2me.base.common.profiling.IVanillaJfrProfiler;
import jdk.jfr.Event;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.util.profiling.jfr.callback.ProfiledDuration;
import net.minecraft.util.profiling.jfr.JfrProfiler;
import net.minecraft.world.level.Level;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Mutable;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

import java.util.ArrayList;
import java.util.List;

@Mixin(net.minecraft.util.profiling.jfr.JfrProfiler.class)
public class MixinJfrProfiler implements IVanillaJfrProfiler {

    @Mutable
    @Shadow @Final private static List<Class<? extends Event>> CUSTOM_EVENTS;

    // Mixin 0.8.5 禁止 @Inject 把「构造函数调用」当作 @At 目标（会抛
    // InvalidInjectionException: Found @Inject targetting a constructor），上游的
    // @At(INVOKE, Ljava/lang/Object;<init>()V, shift=AFTER) 在本环境非法。
    // 构造器中的 HEAD 同样位于 super() 调用之后（即原写法想表达的位置），语义等价且合法。
    @Inject(method = "<init>", at = @At("HEAD"))
    private void preInit(CallbackInfo ci) {
        ArrayList<Class<? extends Event>> copy = new ArrayList<>(CUSTOM_EVENTS);
        copy.add(ChunkLoadScheduleEvent.class);
        CUSTOM_EVENTS = List.copyOf(copy);
    }


    @Override
    public ProfiledDuration startChunkLoadSchedule(ChunkPos chunkPos, ResourceKey<Level> heightAccessor, String targetStatus) {
        if (!ChunkLoadScheduleEvent.TYPE.isEnabled()) {
            return null;
        } else {
            ChunkLoadScheduleEvent event = new ChunkLoadScheduleEvent(chunkPos, heightAccessor, targetStatus);
            event.begin();
            return event::commit;
        }
    }
}
