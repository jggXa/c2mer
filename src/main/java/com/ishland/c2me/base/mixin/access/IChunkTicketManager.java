package com.ishland.c2me.base.mixin.access;

import it.unimi.dsi.fastutil.longs.Long2ObjectMap;
import it.unimi.dsi.fastutil.longs.Long2ObjectOpenHashMap;
import it.unimi.dsi.fastutil.objects.ObjectSet;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.level.Ticket;
import net.minecraft.server.level.DistanceManager;
import net.minecraft.util.SortedArraySet;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;
import org.spongepowered.asm.mixin.gen.Invoker;

@Mixin(net.minecraft.server.level.DistanceManager.class)
public interface IChunkTicketManager {

    @Invoker
    void invokeUpdatePlayerTickets(int viewDistance);

    @Accessor
    Long2ObjectMap<ObjectSet<ServerPlayer>> getPlayersPerChunk();

    @Accessor
    Long2ObjectOpenHashMap<SortedArraySet<Ticket<?>>> getTickets();

    @Accessor
    DistanceManager.PlayerTicketTracker getPlayerTicketManager();

}
