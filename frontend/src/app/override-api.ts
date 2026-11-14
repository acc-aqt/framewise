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

  /** Splits these Frames off their Group into a Group of their own. */
  split(frameIds: number[]): Observable<unknown> {
    return this.http.post('/api/groups/split', { frame_ids: frameIds });
  }

  /** Merges the Groups holding these Frames into one. */
  merge(frameIds: number[]): Observable<unknown> {
    return this.http.post('/api/groups/merge', { frame_ids: frameIds });
  }

  /** Hands the fixed Groups holding these Frames back to framewise's grouping. */
  resetGrouping(frameIds: number[]): Observable<unknown> {
    return this.http.post('/api/groups/reset', { frame_ids: frameIds });
  }

  /** Moves a Frame into the Group of another Frame. */
  move(frameId: number, toFrameId: number): Observable<unknown> {
    return this.http.post(`/api/frames/${frameId}/move`, { to_frame_id: toFrameId });
  }
}
