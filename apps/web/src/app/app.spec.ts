import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../environments/environment';
import { App } from './app';

describe('App', () => {
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('crea la aplicación sin consultar el BFF automáticamente', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    expect(fixture.componentInstance).toBeTruthy();
    http.expectNone(`${environment.bffBaseUrl}/api/hello`);
  });

  it('conserva el título', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const page = fixture.nativeElement as HTMLElement;
    expect(page.querySelector('h1')?.textContent).toContain('Hello, gastos-web');
  });

  it('muestra la espera, evita consultas duplicadas y presenta el mensaje', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const page = fixture.nativeElement as HTMLElement;
    const button = page.querySelector('button')!;
    button.click();
    await fixture.whenStable();

    expect(button.disabled).toBe(true);
    expect(page.querySelector('[role="status"]')?.textContent).toContain('Esperando respuesta');
    button.click();

    const pending = http.expectOne(`${environment.bffBaseUrl}/api/hello`);
    expect(pending.request.method).toBe('GET');
    expect(pending.request.timeout).toBe(environment.requestTimeoutMs);
    pending.flush({ message: 'Hola desde FastAPI' });
    await fixture.whenStable();

    expect(page.textContent).toContain('Hola desde FastAPI');
    expect(page.querySelector('[role="status"]')).toBeNull();
    expect(button.disabled).toBe(false);
  });

  it('permite reintentar después del error controlado del BFF', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const page = fixture.nativeElement as HTMLElement;
    const button = page.querySelector('button')!;

    button.click();
    http.expectOne(`${environment.bffBaseUrl}/api/hello`).flush(
      { message: 'No se pudo consultar FastAPI' },
      { status: 502, statusText: 'Bad Gateway' },
    );
    await fixture.whenStable();
    expect(page.querySelector('[role="alert"]')?.textContent).toContain('Intentá nuevamente');
    expect(button.disabled).toBe(false);

    button.click();
    http.expectOne(`${environment.bffBaseUrl}/api/hello`).flush({ message: 'Hola desde FastAPI' });
    await fixture.whenStable();
    expect(page.querySelector('[role="alert"]')).toBeNull();
    expect(page.textContent).toContain('Hola desde FastAPI');
  });

  it('termina la espera y permite otra consulta tras un error de red', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const page = fixture.nativeElement as HTMLElement;
    const button = page.querySelector('button')!;

    button.click();
    http.expectOne(`${environment.bffBaseUrl}/api/hello`).error(new ProgressEvent('error'));
    await fixture.whenStable();

    expect(page.querySelector('[role="alert"]')).not.toBeNull();
    expect(page.querySelector('[role="status"]')).toBeNull();
    expect(button.disabled).toBe(false);
  });
});
