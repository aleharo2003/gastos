import { Injectable, signal } from '@angular/core';
export type ThemeMode = 'system' | 'light' | 'dark';
export function validTheme(value: unknown): ThemeMode {
  return value === 'light' || value === 'dark' ? value : 'system';
}
@Injectable({providedIn: 'root'})
export class Theme {
  readonly mode = signal<ThemeMode>('system');
  constructor() {
    let saved: unknown = 'system';
    try { saved = localStorage.getItem('gastos.theme'); } catch { /* Storage may be disabled. */ }
    this.apply(validTheme(saved));
  }
  set(value: string): void {
    const mode = validTheme(value);
    this.apply(mode);
    try { localStorage.setItem('gastos.theme', mode); } catch { /* Keep the in-memory choice. */ }
  }
  private apply(mode: ThemeMode): void {
    this.mode.set(mode);
    document.documentElement.dataset['theme'] = mode;
  }
}
