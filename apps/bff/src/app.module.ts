import { ExpensesController } from './expenses.controller.js';
import { AccountsController } from './accounts.controller.js';
import { Module } from '@nestjs/common';
import { AppController } from './app.controller.js';
import { AppService } from './app.service.js';
import { AuthController } from './auth.controller.js';
import { AuthService } from './auth.service.js';

@Module({
  imports: [],
  controllers: [ExpensesController, AppController, AuthController, AccountsController],
  providers: [AppService, AuthService],
})
export class AppModule {}
