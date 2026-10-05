package com.ishland.c2me.base.mixin.access;

import net.minecraft.server.level.ChunkHolder;
import net.minecraft.server.level.ChunkMap;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

import java.util.concurrent.Executor;

@Mixin(net.minecraft.server.level.ChunkHolder.class)
public interface IChunkHolder {

    @Invoker
    void invokeUpdateFutures(ChunkMap chunkMap, Executor executor);

}
