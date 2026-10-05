package com.ishland.c2me.base.mixin.access;

import net.minecraft.world.entity.ai.behavior.ShufflingList;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

@Mixin(net.minecraft.world.entity.ai.behavior.ShufflingList.WeightedEntry.class)
public interface IWeightedListEntry {

    @Invoker
    double invokeGetRandWeight();

    @Invoker
    void invokeSetRandom(float random);

}
