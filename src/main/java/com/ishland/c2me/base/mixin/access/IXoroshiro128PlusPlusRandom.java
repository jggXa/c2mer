package com.ishland.c2me.base.mixin.access;

import net.minecraft.world.level.levelgen.XoroshiroRandomSource;
import net.minecraft.world.level.levelgen.Xoroshiro128PlusPlus;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

@Mixin(net.minecraft.world.level.levelgen.XoroshiroRandomSource.class)
public interface IXoroshiro128PlusPlusRandom {

    @Accessor
    Xoroshiro128PlusPlus getRandomNumberGenerator();

}
