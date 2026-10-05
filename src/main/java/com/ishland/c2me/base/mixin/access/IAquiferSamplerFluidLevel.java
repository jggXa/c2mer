package com.ishland.c2me.base.mixin.access;

import net.minecraft.world.level.levelgen.Aquifer;
import org.spongepowered.asm.mixin.Mixin;

@Mixin(net.minecraft.world.level.levelgen.Aquifer.FluidStatus.class)
public interface IAquiferSamplerFluidLevel {

}
