import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';

describe('Chat (e2e)', () => {
  let app: INestApplication;

  beforeEach(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [],
    }).compile();

    app = moduleFixture.createNestApplication();
    await app.init();
  });

  it('/chat (POST)', () => {
    return request(app.getHttpServer())
      .post('/chat')
      .send({ message: 'Hello' })
      .expect(201);
  });
});

