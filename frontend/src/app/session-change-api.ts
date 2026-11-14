import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { SessionSummary } from './session-api';

@Injectable({ providedIn: 'root' })
export class SessionChangeApi {
  private readonly http = inject(HttpClient);

  changeKeeperBudget(share: number): Observable<SessionSummary> {
    return this.http.patch<SessionSummary>('/api/session', { keeper_budget: share });
  }
}
