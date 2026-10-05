package com.ishland.c2me.base.mixin.access;

import net.minecraft.world.level.levelgen.BelowZeroRetrogen;
import net.minecraft.world.level.chunk.ChunkStatus;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;
import org.spongepowered.asm.mixin.gen.Invoker;

import java.util.BitSet;


@Mixin(value = net.minecraft.world.level.levelgen.BelowZeroRetrogen.class)
public interface IBelowZeroRetrogen {
    @Accessor
    BitSet getMissingBedrock();

    @Invoker
    ChunkStatus invokeTargetStatus();
}
