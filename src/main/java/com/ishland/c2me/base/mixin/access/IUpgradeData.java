package com.ishland.c2me.base.mixin.access;

import net.minecraft.core.Direction8;
import net.minecraft.world.level.chunk.UpgradeData;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

import java.util.EnumSet;

@Mixin(net.minecraft.world.level.chunk.UpgradeData.class)
public interface IUpgradeData {
    @Accessor
    int[][] getIndex();

    @Accessor
    EnumSet<Direction8> getSides();
}
