import {
  HttpClient,
  HttpErrorResponse,
  HttpEventType,
  HttpInterceptorFn,
} from '@angular/common/http';
import { DOCUMENT, effect, inject, Injectable, signal } from '@angular/core';
import { finalize, tap } from 'rxjs';

export const RECONNECT_INTERVAL_MS = 3000;

/** Whether the review server answers, judged from the Review UI's own requests. */
@Injectable({ providedIn: 'root' })
export class ServerConnection {
  private readonly http = inject(HttpClient);
  private readonly lost = signal(false);
  private checking = false;

  readonly disconnected = this.lost.asReadonly();

  constructor() {
    const document = inject(DOCUMENT);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') {
        this.check();
      }
    });
    effect((onCleanup) => {
      if (!this.lost()) {
        return;
      }
      const timer = setInterval(() => this.check(), RECONNECT_INTERVAL_MS);
      onCleanup(() => clearInterval(timer));
    });
  }

  /** Asks the server whether it is still there, for when something failed without saying why. */
  check(): void {
    if (this.checking) {
      return;
    }
    this.checking = true;
    this.http
      .get('/api/about')
      .pipe(finalize(() => (this.checking = false)))
      .subscribe({ error: () => undefined });
  }

  answered(): void {
    this.lost.set(false);
  }

  unreachable(): void {
    this.lost.set(true);
  }
}

/** A request that fails with status 0 never reached the server; any other answer means it is up. */
export const watchServerConnection: HttpInterceptorFn = (request, next) => {
  const connection = inject(ServerConnection);
  return next(request).pipe(
    tap({
      next: (event) => {
        if (event.type === HttpEventType.Response) {
          connection.answered();
        }
      },
      error: (error) => {
        if (error instanceof HttpErrorResponse && error.status === 0) {
          connection.unreachable();
        } else {
          connection.answered();
        }
      },
    }),
  );
};
