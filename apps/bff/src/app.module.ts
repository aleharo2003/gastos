import { Module } from '@nestjs/common';
import { AppController } from './app.controller.js';
import { AppService } from './app.service.js';
import { AuthController } from './auth.controller.js';
import { AuthService } from './auth.service.js';

@Module({
  imports: [],
  controllers: [AppController, AuthController],
  providers: [AppService, AuthService],
})
export class AppModule {}
