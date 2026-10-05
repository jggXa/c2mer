package com.ishland.c2me.base.mixin.access;

import net.minecraft.server.level.Ticket;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

@Mixin(net.minecraft.server.level.Ticket.class)
public interface IChunkTicket {

    @Invoker
    boolean invokeTimedOut(long currentTick);

}
