import { Module, OnModuleInit } from "@nestjs/common";
import { QueueController } from "./queue.controller";
import { initQueues } from "./bullmq.service";

@Module({
  controllers: [QueueController],
})
export class QueueModule implements OnModuleInit {
  async onModuleInit() {
    await initQueues();
  }
}
