import { Component, DOCUMENT, inject, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Theme } from './theme';
import { Accounts } from './accounts';
import { AuthSession } from './auth-session';
import { InstallPiggo } from './install-piggo';

@Component({
  selector: 'app-root', imports: [FormsModule, Accounts, InstallPiggo],
  templateUrl: './app.html', styleUrl: './app.css',
})
export class App implements OnInit {
  protected readonly theme = inject(Theme);
  protected readonly auth = inject(AuthSession);
  protected email = '';
  protected password = '';
  protected recoveryMode: 'request' | 'reset' | null = null;
  protected recoveryNotice = '';
  protected recoveryError = '';
  protected recoveryBusy = false;
  protected newPassword = '';
  protected repeatedPassword = '';
  protected registrationMode: 'form' | 'confirm' | null = null;
  protected registrationNotice = '';
  protected registrationError = '';
  protected registrationToken = '';
  private recoveryToken = '';
  private readonly browser = inject(DOCUMENT).defaultView;

  ngOnInit(): void {
    if (this.browser) {
      const url = new URL(this.browser.location.href);
      if (url.searchParams.has('recuperar')) {
        this.recoveryToken = new URLSearchParams(url.hash.slice(1)).get('token_hash') ?? '';
        this.recoveryMode = this.recoveryToken ? 'reset' : 'request';
        if (!this.recoveryToken) this.recoveryError = 'El enlace no es válido. Pedí uno nuevo.';
        url.searchParams.delete('recuperar');
        url.hash = '';
        this.browser.history.replaceState(this.browser.history.state, '', url);
      } else if (url.searchParams.has('registro')) {
        this.registrationMode = 'confirm';
        const token = new URLSearchParams(url.hash.slice(1)).get('token_hash') ?? '';
        this.registrationToken = token.length <= 512 ? token : '';
        if (!this.registrationToken) this.registrationError = 'El enlace no es válido. Volvé a iniciar el registro.';
        url.searchParams.delete('registro');
        url.hash = '';
        this.browser.history.replaceState(this.browser.history.state, '', url);
      }
    }
    void this.auth.initialize();
  }

  protected startRecovery(): void {
    this.closeRegistration();
    this.recoveryMode = 'request';
    this.recoveryNotice = '';
    this.recoveryError = '';
    this.password = '';
  }

  protected closeRecovery(): void {
    this.recoveryMode = null;
    this.recoveryToken = '';
    this.newPassword = '';
    this.repeatedPassword = '';
    this.recoveryError = '';
    void this.auth.endPasswordRecovery();
  }

  protected async requestRecovery(): Promise<void> {
    if (!this.browser || this.recoveryBusy) return;
    this.recoveryBusy = true;
    this.recoveryError = '';
    try {
      const redirectTo = new URL('/?recuperar=1', this.browser.location.origin);
      await this.auth.requestPasswordReset(this.email, redirectTo.href);
      this.closeRecovery();
      this.recoveryNotice = 'Si el email tiene una cuenta, vas a recibir un enlace para cambiar la contraseña.';
    } finally { this.recoveryBusy = false; }
  }

  protected async submitNewPassword(): Promise<void> {
    if (this.recoveryBusy || this.newPassword.length < 8) return;
    if (this.newPassword !== this.repeatedPassword) {
      this.recoveryError = 'Las contraseñas tienen que coincidir.';
      return;
    }
    this.recoveryBusy = true;
    this.recoveryError = '';
    try {
      const result = await this.auth.resetPassword(this.recoveryToken, this.newPassword);
      if (result === 'updated') {
        this.closeRecovery();
        this.recoveryNotice = 'Contraseña actualizada. Ya podés ingresar con la nueva.';
      } else if (result === 'expired') {
        this.closeRecovery();
        this.startRecovery();
        this.recoveryError = 'El enlace venció o ya se usó. Pedí uno nuevo.';
      } else {
        this.recoveryError = 'No pudimos cambiar la contraseña. Revisá la conexión o probá otra contraseña.';
      }
    } finally { this.recoveryBusy = false; }
  }
  protected startRegistration(): void {
    this.registrationMode = 'form';
    this.registrationError = '';
    this.registrationNotice = '';
    this.recoveryNotice = '';
    this.password = '';
  }

  protected closeRegistration(): void {
    this.registrationMode = null;
    this.registrationError = '';
    this.registrationToken = '';
    this.password = '';
  }

  protected async submitRegistration(): Promise<void> {
    if (!this.browser || this.auth.busy() || this.password.length < 8) return;
    this.registrationError = '';
    const redirectTo = new URL('/?registro=1', this.browser.location.origin);
    const password = this.password;
    this.password = '';
    const result = await this.auth.register(this.email, password, redirectTo.href);
    if (result === 'retry') {
      this.registrationError = 'No pudimos enviar la solicitud. Revisá la conexión y volvé a intentar.';
      return;
    }
    this.closeRegistration();
    if (result === 'check-email') {
      this.registrationNotice = 'Si recibís un correo de Piggo, seguí el enlace para confirmar tu email. Si ya tenés acceso, iniciá sesión o recuperá tu contraseña.';
    }
  }

  protected async confirmRegistration(): Promise<void> {
    if (this.auth.busy() || !this.registrationToken) return;
    this.registrationError = '';
    if (await this.auth.confirmRegistration(this.registrationToken)) this.closeRegistration();
    else this.registrationError = 'No pudimos confirmar el email. El enlace puede haber vencido o estar usado. Volvé a intentar o iniciá sesión.';
  }

  protected async submit(): Promise<void> {
    this.registrationNotice = '';
    try { await this.auth.login(this.email, this.password); }
    finally { this.password = ''; }
  }
}
