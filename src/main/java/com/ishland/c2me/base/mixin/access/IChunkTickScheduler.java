package com.ishland.c2me.base.mixin.access;

import net.minecraft.world.ticks.LevelChunkTicks;
import net.minecraft.world.ticks.ScheduledTick;
import net.minecraft.world.ticks.SerializableTickContainer;
import net.minecraft.world.ticks.SavedTick;
import org.jetbrains.annotations.Nullable;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

import java.util.List;
import java.util.Queue;

@Mixin(net.minecraft.world.ticks.LevelChunkTicks.class)
public interface IChunkTickScheduler<T> extends SerializableTickContainer<T> {
    @Accessor
    @Nullable List<SavedTick<T>> getPendingTicks();

    @Accessor
    Queue<ScheduledTick<T>> getTickQueue();

}
