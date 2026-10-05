package com.ishland.c2me.base.mixin.profiling;

import com.ishland.c2me.base.common.profiling.IVanillaJfrProfiler;
import com.mojang.datafixers.util.Either;
import net.minecraft.server.level.ChunkHolder;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ChunkMap;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.util.profiling.jfr.callback.ProfiledDuration;
import net.minecraft.util.profiling.jfr.JvmProfiler;
import net.minecraft.world.level.LevelHeightAccessor;
import net.minecraft.world.level.chunk.ChunkAccess;
import net.minecraft.world.level.chunk.ChunkStatus;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

import java.util.concurrent.CompletableFuture;

@Mixin(net.minecraft.server.level.ChunkHolder.class)
public abstract class MixinChunkHolder {


    @Shadow public abstract ChunkPos getPos();

    @Shadow @Final private LevelHeightAccessor levelHeightAccessor;

    @Inject(method = "getOrScheduleFuture", at = @At("RETURN"))
    private void postGetChunkAt(ChunkStatus targetStatus, ChunkMap chunkMap, CallbackInfoReturnable<CompletableFuture<Either<ChunkAccess, ChunkHolder.ChunkLoadingFailure>>> cir) {
        if (JvmProfiler.INSTANCE instanceof IVanillaJfrProfiler profiler && this.levelHeightAccessor instanceof ServerLevel serverWorld && !cir.getReturnValue().isDone()) {
            final ProfiledDuration finishable = profiler.startChunkLoadSchedule(this.getPos(), serverWorld.dimension(), targetStatus.toString());
            if (finishable != null) {
                cir.getReturnValue().exceptionally(unused -> null).thenRun(finishable::finish);
            }
        }
    }

}
