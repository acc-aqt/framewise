import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { OverrideChange } from './session-api';

@Injectable({ providedIn: 'root' })
export class OverrideApi {
  private readonly http = inject(HttpClient);

  change(frameId: number, change: OverrideChange): Observable<unknown> {
    return this.http.patch(`/api/frames/${frameId}/override`, change);
  }

  clear(frameId: number): Observable<unknown> {
    return this.http.delete(`/api/frames/${frameId}/override`);
  }
}
