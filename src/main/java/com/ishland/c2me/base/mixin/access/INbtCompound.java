package com.ishland.c2me.base.mixin.access;

import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.Tag;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

import java.util.Map;

@Mixin(net.minecraft.nbt.CompoundTag.class)
public interface INbtCompound {

    @Invoker
    Map<String, Tag> invokeEntries();

}
