import {
  WebSocketGateway,
  SubscribeMessage,
  OnGatewayConnection,
  OnGatewayDisconnect,
} from '@nestjs/websockets';

@WebSocketGateway({ 
  cors: {
    origin: [
      'http://localhost:3001', 
      'http://localhost:3000',
      process.env.FRONTEND_URL || 'http://localhost:3001',
      'https://intellimaint-ai.vercel.app',
    ],
    credentials: true,
  }
})
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

