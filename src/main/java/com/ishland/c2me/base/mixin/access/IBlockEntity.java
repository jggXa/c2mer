package com.ishland.c2me.base.mixin.access;

import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.nbt.CompoundTag;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

@Mixin(net.minecraft.world.level.block.entity.BlockEntity.class)
public interface IBlockEntity {

    @Invoker
    void invokeSaveAdditional(CompoundTag nbt);

}
