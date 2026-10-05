package com.ishland.c2me.base.mixin.access;

import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.chunk.storage.RegionFile;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

import java.io.IOException;
import java.nio.ByteBuffer;

@Mixin(net.minecraft.world.level.chunk.storage.RegionFile.class)
public interface IRegionFile {

    @Invoker
    void invokeWrite(ChunkPos pos, ByteBuffer byteBuffer) throws IOException;

}
