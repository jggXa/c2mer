package com.ishland.c2me.base.mixin.theinterface;

import com.ishland.c2me.base.common.theinterface.IDirectStorage;
import com.ishland.c2me.base.mixin.access.IPendingStore;
import com.ishland.c2me.base.mixin.access.IRegionBasedStorage;
import com.mojang.datafixers.util.Either;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.chunk.storage.RegionFileStorage;
import net.minecraft.world.level.chunk.storage.RegionFile;
import net.minecraft.world.level.chunk.storage.IOWorker;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;

import java.io.DataOutputStream;
import java.io.IOException;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.function.Supplier;

@Mixin(net.minecraft.world.level.chunk.storage.IOWorker.class)
public abstract class MixinStorageIoWorker implements IDirectStorage {


    @Shadow protected abstract <T> CompletableFuture<T> submitTask(Supplier<Either<T, Exception>> create);

    @Shadow @Final private Map<ChunkPos, IOWorker.PendingStore> pendingWrites;

    @Shadow protected abstract void runStore(ChunkPos pos, IOWorker.PendingStore result);

    @Shadow @Final private RegionFileStorage storage;

    @Override
    public CompletableFuture<Void> setRawChunkData(ChunkPos pos, byte[] data) {
        return this.submitTask(() -> {
            IOWorker.PendingStore result = this.pendingWrites.get(pos);
            try {
                final RegionFile regionFile = ((IRegionBasedStorage) (Object) this.storage).invokeGetRegionFile(pos);
                try (final DataOutputStream out = regionFile.getChunkDataOutputStream(pos)) {
                    out.write(data);
                }
                if (result != null) ((IPendingStore) (Object) result).getResult().complete(null);
            } catch (IOException e) {
                return Either.right(e);
            }
            return Either.left(null);
        });
    }

}
