package com.ishland.c2me.base.common.registry;

import com.ibm.asyncutil.util.Either;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.chunk.storage.ChunkSerializer;
import net.minecraft.world.level.chunk.ChunkAccess;

/**
 * Only used for c2me-threading-chunkio
 */
public class SerializerAccess {

    private final static Serializer VANILLA = (heightAccessor, chunk) -> Either.left(ChunkSerializer.write(heightAccessor, chunk));

    private static Serializer activeSerializer = null;

    public static void registerSerializer(Serializer serializer) {
        if (serializer == null) {
            throw new NullPointerException("serializer");
        } else if (activeSerializer != null) {
            throw new IllegalStateException("Serializer already registered");
        } else {
            activeSerializer = serializer;
        }
    }

    public static Serializer getSerializer() {
        return activeSerializer == null ? VANILLA : activeSerializer;
    }

    public interface Serializer {

        com.ibm.asyncutil.util.Either<CompoundTag, byte[]> serialize(ServerLevel heightAccessor, ChunkAccess chunk);

    }

}
