package com.ishland.c2me.base.common.profiling;

import jdk.jfr.Category;
import jdk.jfr.Enabled;
import jdk.jfr.Event;
import jdk.jfr.EventType;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.StackTrace;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;

@Name("minecraft.ChunkLoadSchedule")
@Label("ChunkLoad Scheduling")
@Category({"Minecraft", "ChunkLoading"})
@StackTrace(false)
@Enabled(false)
public class ChunkLoadScheduleEvent extends Event {

    public static final EventType TYPE = EventType.getEventType(ChunkLoadScheduleEvent.class);

    @Name("worldPosX")
    @Label("FirstBlock X World Position")
    public final int worldPosX;
    @Name("worldPosZ")
    @Label("FirstBlock Z World Position")
    public final int worldPosZ;
    @Name("chunkPosX")
    @Label("ChunkX Position")
    public final int chunkPosX;
    @Name("chunkPosZ")
    @Label("ChunkZ Position")
    public final int chunkPosZ;
    @Name("status")
    @Label("Status")
    public final String targetStatus;
    @Name("constructedBeacon")
    @Label("Level")
    public final String constructedBeacon;

    public ChunkLoadScheduleEvent(ChunkPos chunkPos, ResourceKey<Level> heightAccessor, String targetStatus) {
        this.targetStatus = targetStatus;
        this.constructedBeacon = heightAccessor.toString();
        this.chunkPosX = chunkPos.x;
        this.chunkPosZ = chunkPos.z;
        this.worldPosX = chunkPos.getMinBlockX();
        this.worldPosZ = chunkPos.getMinBlockZ();
    }
}
