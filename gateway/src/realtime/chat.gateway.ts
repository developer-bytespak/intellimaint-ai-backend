import {
  WebSocketGateway,
  SubscribeMessage,
  OnGatewayConnection,
  OnGatewayDisconnect,
} from '@nestjs/websockets';

@WebSocketGateway({ cors: true })
export class RealtimeChatGateway implements OnGatewayConnection, OnGatewayDisconnect {
  handleConnection(client: any) {
    console.log('Client connected:', client.id);
  }

  handleDisconnect(client: any) {
    console.log('Client disconnected:', client.id);
  }

  @SubscribeMessage('chat')
  handleChatMessage(client: any, payload: any) {
    return { event: 'chat', data: payload };
  }
}

