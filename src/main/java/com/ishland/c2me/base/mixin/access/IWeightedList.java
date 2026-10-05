package com.ishland.c2me.base.mixin.access;

import net.minecraft.world.entity.ai.behavior.ShufflingList;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

import java.util.List;

@Mixin(net.minecraft.world.entity.ai.behavior.ShufflingList.class)
public interface IWeightedList<U> {

    @Accessor
    List<ShufflingList.WeightedEntry<U>> getEntries();

}
