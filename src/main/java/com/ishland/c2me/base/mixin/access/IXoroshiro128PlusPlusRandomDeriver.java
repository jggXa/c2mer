package com.ishland.c2me.base.mixin.access;

import net.minecraft.world.level.levelgen.XoroshiroRandomSource;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

@Mixin(net.minecraft.world.level.levelgen.XoroshiroRandomSource.XoroshiroPositionalRandomFactory.class)
public interface IXoroshiro128PlusPlusRandomDeriver {

    @Accessor
    long getSeedLo();

    @Accessor
    long getSeedHi();

}
