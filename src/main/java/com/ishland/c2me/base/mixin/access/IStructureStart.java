package com.ishland.c2me.base.mixin.access;

import net.minecraft.world.level.levelgen.structure.pieces.PiecesContainer;
import net.minecraft.world.level.levelgen.structure.StructureStart;
import net.minecraft.world.level.levelgen.structure.Structure;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

@Mixin(net.minecraft.world.level.levelgen.structure.StructureStart.class)
public interface IStructureStart {
    @Accessor
    Structure getStructure();

    @Accessor
    PiecesContainer getPieceContainer();

    @Accessor
    int getReferences();
}
