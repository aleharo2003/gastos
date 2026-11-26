import { Component, DestroyRef, DOCUMENT, inject, signal } from '@angular/core';

interface InstallPrompt extends Event {
  prompt(): Promise<unknown>;
}

const visitCountKey = 'piggo.install.visits';

@Component({
  selector: 'app-install-piggo',
  templateUrl: './install-piggo.html',
  styleUrl: './install-piggo.css',
})
export class InstallPiggo {
  protected readonly canInstall = signal(false);
  protected readonly iosSafari = signal(false);
  protected readonly showInstructions = signal(false);
  private deferredPrompt: InstallPrompt | null = null;

  constructor() {
    const browser = inject(DOCUMENT).defaultView;
    const destroyRef = inject(DestroyRef);
    if (!browser) return;

    const navigator = browser.navigator as Navigator & { standalone?: boolean };
    if (browser.isSecureContext && navigator.serviceWorker) {
      void navigator.serviceWorker.register('piggo-sw.js').catch(() => undefined);
    }
    if (navigator.standalone || browser.matchMedia?.('(display-mode: standalone)').matches) return;

    const agent = navigator.userAgent;
    const ios = /iPhone|iPad|iPod/i.test(agent)
      || (/Macintosh/i.test(agent) && navigator.maxTouchPoints > 1);
    this.iosSafari.set(ios && /Safari/i.test(agent) && !/CriOS|FxiOS|EdgiOS|OPiOS/i.test(agent));
    const returning = this.recordVisit(browser);

    const onPrompt = (event: Event) => {
      event.preventDefault();
      if (!returning) return;
      this.deferredPrompt = event as InstallPrompt;
      this.canInstall.set(true);
    };
    const onInstalled = () => this.clearPrompt();
    browser.addEventListener('beforeinstallprompt', onPrompt);
    browser.addEventListener('appinstalled', onInstalled);
    destroyRef.onDestroy(() => {
      browser.removeEventListener('beforeinstallprompt', onPrompt);
      browser.removeEventListener('appinstalled', onInstalled);
    });
  }

  protected async install(): Promise<void> {
    const prompt = this.deferredPrompt;
    if (!prompt) return;
    this.clearPrompt();
    try {
      await prompt.prompt();
    } catch {
      // The browser can withdraw an offer when eligibility changes.
    }
  }

  private clearPrompt(): void {
    this.deferredPrompt = null;
    this.canInstall.set(false);
  }

  private recordVisit(browser: Window): boolean {
    try {
      const returning = Number(browser.localStorage.getItem(visitCountKey)) >= 1;
      browser.localStorage.setItem(visitCountKey, returning ? '2' : '1');
      return returning;
    } catch {
      return true;
    }
  }
}
