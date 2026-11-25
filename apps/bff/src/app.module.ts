import { MovementsController } from './movements.controller.js';
import { SpaceExportController } from './space-export.controller.js';
import { MovementCategoriesController } from './movement-categories.controller.js';
import { CommitmentsController } from './commitments.controller.js';
import { SavingsGoalsController } from './savings-goals.controller.js';
import { TransfersController } from './transfers.controller.js';
import { IncomesController } from './incomes.controller.js';
import { PlanningController } from './planning.controller.js';
import { ExpensesController } from './expenses.controller.js';
import { ReceiptsController } from './receipts.controller.js';
import { AccountsController } from './accounts.controller.js';
import { Module } from '@nestjs/common';
import { AppController } from './app.controller.js';
import { AppService } from './app.service.js';
import { AuthController } from './auth.controller.js';
import { AuthService } from './auth.service.js';

@Module({
  imports: [],
  controllers: [MovementsController, SpaceExportController, MovementCategoriesController, CommitmentsController, SavingsGoalsController, TransfersController, IncomesController, PlanningController, ReceiptsController, ExpensesController, AppController, AuthController, AccountsController],
  providers: [AppService, AuthService],
})
export class AppModule {}
