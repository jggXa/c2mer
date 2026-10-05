package com.ishland.c2me.base.mixin.access;

import net.minecraft.server.level.DistanceManager;
import net.minecraft.server.level.ServerChunkCache;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;
import org.spongepowered.asm.mixin.gen.Invoker;

@Mixin(net.minecraft.server.level.ServerChunkCache.class)
public interface IServerChunkManager {

    @Accessor
    DistanceManager getDistanceManager();

    @Accessor
    ServerChunkCache.MainThreadExecutor getMainThreadProcessor();

    @Invoker
    boolean invokeRunDistanceManagerUpdates();

}
