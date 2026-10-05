package com.ishland.c2me.base.mixin.access;

import it.unimi.dsi.fastutil.longs.Long2ObjectLinkedOpenHashMap;
import net.minecraft.server.level.ChunkHolder;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ChunkMap;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.util.thread.BlockableEventLoop;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;
import org.spongepowered.asm.mixin.gen.Invoker;

@Mixin(net.minecraft.server.level.ChunkMap.class)
public interface IThreadedAnvilChunkStorage {

    @Accessor
    ServerLevel getLevel();

    @Invoker
    boolean invokePromoteChunkMap();

    @Accessor
    Long2ObjectLinkedOpenHashMap<ChunkHolder> getVisibleChunkMap();

    @Accessor
    Long2ObjectLinkedOpenHashMap<ChunkHolder> getUpdatingChunkMap();

    @Invoker
    boolean invokeSaveChunkIfNeeded(ChunkHolder chunkHolder);

    @Invoker
    void invokeReleaseLightTicket(ChunkPos pos);

    @Accessor
    BlockableEventLoop<Runnable> getMainThreadExecutor();

}
