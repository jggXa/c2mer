package com.ishland.c2me.base.mixin.access;

import net.minecraft.world.level.chunk.storage.IOWorker;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

import java.util.BitSet;
import java.util.concurrent.CompletableFuture;

@Mixin(net.minecraft.world.level.chunk.storage.IOWorker.class)
public interface IStorageIoWorker {

    @Invoker
    CompletableFuture<BitSet> invokeGetOrCreateOldDataForRegion(int x, int z);

}
