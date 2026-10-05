package com.ishland.c2me.base.mixin.access;

import net.minecraft.world.level.levelgen.blending.Blender;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

@Mixin(net.minecraft.world.level.levelgen.blending.Blender.class)
public interface IBlender {

    @Accessor
    static int getHEIGHT_BLENDING_RANGE_CHUNKS() {
        throw new AbstractMethodError();
    }

}
