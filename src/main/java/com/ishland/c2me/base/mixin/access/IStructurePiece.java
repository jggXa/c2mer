package com.ishland.c2me.base.mixin.access;

import net.minecraft.world.level.levelgen.structure.StructurePiece;
import net.minecraft.world.level.levelgen.structure.pieces.StructurePieceType;
import net.minecraft.world.level.block.Mirror;
import net.minecraft.world.level.block.Rotation;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.core.Direction;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

@Mixin(net.minecraft.world.level.levelgen.structure.StructurePiece.class)
public interface IStructurePiece {

    @Accessor
    StructurePieceType getType();

    @Accessor
    BoundingBox getBoundingBox();

    @Accessor
    Direction getOrientation();

    @Accessor
    Mirror getMirror();

    @Accessor
    Rotation getRotation();

    @Accessor
    int getGenDepth();
}
