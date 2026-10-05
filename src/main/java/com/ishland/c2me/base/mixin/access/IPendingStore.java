package com.ishland.c2me.base.mixin.access;

import net.minecraft.world.level.chunk.storage.IOWorker;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

import java.util.concurrent.CompletableFuture;

@Mixin(IOWorker.PendingStore.class)
public interface IPendingStore {

    @Accessor("result")
    CompletableFuture getResult();

}