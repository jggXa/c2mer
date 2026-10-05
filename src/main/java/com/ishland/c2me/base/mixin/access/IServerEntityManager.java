package com.ishland.c2me.base.mixin.access;

import it.unimi.dsi.fastutil.longs.LongSet;
import net.minecraft.world.level.entity.PersistentEntitySectionManager;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

@Mixin(net.minecraft.world.level.entity.PersistentEntitySectionManager.class)
public interface IServerEntityManager {

    @Invoker
    LongSet invokeGetAllChunksToSave();

}
