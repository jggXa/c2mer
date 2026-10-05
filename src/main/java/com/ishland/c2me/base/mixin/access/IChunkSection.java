package com.ishland.c2me.base.mixin.access;

import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.core.Holder;
import net.minecraft.world.level.biome.Biome;
import net.minecraft.world.level.chunk.LevelChunkSection;
import net.minecraft.world.level.chunk.PalettedContainer;
import net.minecraft.world.level.chunk.PalettedContainerRO;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

@Mixin(net.minecraft.world.level.chunk.LevelChunkSection.class)
public interface IChunkSection {
    @Accessor
    PalettedContainer<BlockState> getStates();

    @Accessor
    PalettedContainerRO<Holder<Biome>> getBiomes();
}
