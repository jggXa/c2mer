package com.ishland.c2me.base.mixin.access;

import net.minecraft.world.level.LevelHeightAccessor;
import net.minecraft.world.level.levelgen.blending.BlendingData;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;


@Mixin(value = net.minecraft.world.level.levelgen.blending.BlendingData.class)
public interface IBlendingData {
    @Accessor
    LevelHeightAccessor getAreaWithOldGeneration();

    @Accessor
    double[] getHeights();
}
