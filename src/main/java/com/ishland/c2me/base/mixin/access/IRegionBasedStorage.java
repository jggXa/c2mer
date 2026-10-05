package com.ishland.c2me.base.mixin.access;

import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.chunk.storage.RegionFileStorage;
import net.minecraft.world.level.chunk.storage.RegionFile;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

import java.io.IOException;

@Mixin(net.minecraft.world.level.chunk.storage.RegionFileStorage.class)
public interface IRegionBasedStorage {

    @Invoker
    RegionFile invokeGetRegionFile(ChunkPos pos) throws IOException;

}
