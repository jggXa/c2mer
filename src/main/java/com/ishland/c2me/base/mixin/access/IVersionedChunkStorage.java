package com.ishland.c2me.base.mixin.access;

import net.minecraft.world.level.chunk.storage.IOWorker;
import net.minecraft.world.level.chunk.storage.ChunkStorage;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

@Mixin(net.minecraft.world.level.chunk.storage.ChunkStorage.class)
public interface IVersionedChunkStorage {

    @Accessor
    IOWorker getWorker();

}
