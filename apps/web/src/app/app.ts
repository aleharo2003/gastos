import { Component, inject, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AuthSession } from './auth-session';

@Component({
  selector: 'app-root', imports: [FormsModule],
  templateUrl: './app.html', styleUrl: './app.css',
})
export class App implements OnInit {
  protected readonly auth = inject(AuthSession);
  protected email = '';
  protected password = '';
  ngOnInit(): void { void this.auth.initialize(); }
  protected async submit(): Promise<void> {
    try { await this.auth.login(this.email, this.password); }
    finally { this.password = ''; }
  }
}
