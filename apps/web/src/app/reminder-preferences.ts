import { Component, DestroyRef, inject, Input, OnChanges, signal, SimpleChanges } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AuthSession } from './auth-session';

type Preferences = {
  canal: 'ninguno' | 'email' | 'push';
  dias_anticipacion: number;
  hora_local: string;
  vencimientos: boolean;
  vencidas: boolean;
  resumen_semanal: boolean;
};

@Component({
  selector: 'app-reminder-preferences',
  imports: [FormsModule],
  templateUrl: './reminder-preferences.html',
  styleUrls: ['./planning.css', './reminder-preferences.css'],
})
export class ReminderPreferences implements OnChanges {
  @Input({ required: true }) space = '';
  @Input() active = false;
  private readonly auth = inject(AuthSession);
  private readonly destroy = inject(DestroyRef);
  private generation = 0;

  protected draft: Preferences | null = null;
  protected readonly loading = signal(false);
  protected readonly saving = signal(false);
  protected readonly error = signal('');
  protected readonly notice = signal('');

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['space']) {
      this.generation++;
      this.draft = null;
      this.loading.set(false);
      this.saving.set(false);
      this.error.set('');
      this.notice.set('');
    }
    if (this.active && !this.draft) void this.load();
  }

  private get path(): string {
    return '/api/spaces/' + encodeURIComponent(this.space) + '/reminder-preferences';
  }

  private current(generation: number): boolean {
    return !this.destroy.destroyed && this.generation === generation;
  }

  protected async load(): Promise<void> {
    if (!this.space || this.loading() || this.saving()) return;
    const generation = this.generation;
    this.loading.set(true);
    this.error.set('');
    try {
      const data = await this.auth.accountRequest<Preferences>('GET', this.path);
      if (this.current(generation)) this.draft = { ...data };
    } catch {
      if (this.current(generation)) this.error.set('No pudimos cargar tus preferencias.');
    } finally {
      if (this.current(generation)) this.loading.set(false);
    }
  }

  protected async save(): Promise<void> {
    if (!this.draft || this.saving()) return;
    if (!Number.isInteger(this.draft.dias_anticipacion)) {
      this.notice.set('');
      this.error.set('Ingresá un número entero de días de anticipación.');
      return;
    }
    const generation = this.generation;
    this.saving.set(true);
    this.notice.set('');
    this.error.set('');
    try {
      const data = await this.auth.accountRequest<Preferences>('POST', this.path, { ...this.draft });
      if (!this.current(generation)) return;
      this.draft = { ...data };
      this.notice.set('Preferencias guardadas.');
    } catch {
      if (this.current(generation)) this.error.set('No pudimos guardar tus preferencias. Tus cambios siguen en el formulario.');
    } finally {
      if (this.current(generation)) this.saving.set(false);
    }
  }
}
