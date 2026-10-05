package com.ishland.c2me.base.mixin.access;

import net.minecraft.world.level.chunk.storage.SectionStorage;
import net.minecraft.world.level.chunk.storage.IOWorker;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

@Mixin(net.minecraft.world.level.chunk.storage.SectionStorage.class)
public interface ISerializingRegionBasedStorage {

    @Accessor
    IOWorker getWorker();

}
