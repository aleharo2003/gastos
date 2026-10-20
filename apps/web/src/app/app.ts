import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { finalize } from 'rxjs';
import { environment } from '../environments/environment';

@Component({
  imports: [RouterOutlet],
  selector: 'app-root',
  styleUrl: './app.css',
  templateUrl: './app.html',
})
export class App {
  protected readonly title = signal('gastos-web');
  protected readonly message = signal('');
  protected readonly loading = signal(false);
  protected readonly error = signal('');

  private readonly http = inject(HttpClient);

  protected loadMessage(): void {
    if (this.loading()) {
      return;
    }

    this.message.set('');
    this.error.set('');
    this.loading.set(true);

    this.http
      .get<{ message: string }>(`${environment.bffBaseUrl}/api/hello`, {
        timeout: environment.requestTimeoutMs,
      })
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (response) => {
          this.message.set(response.message);
        },
        error: () => {
          this.error.set('No se pudo obtener el mensaje. Intentá nuevamente.');
        },
      });
  }
}
