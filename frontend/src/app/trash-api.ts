import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';

export interface TrashResult {
  /** The ids of the Frames that left the Session. */
  trashed: number[];
  failed: { path: string; error: string }[];
}

@Injectable({ providedIn: 'root' })
export class TrashApi {
  private readonly http = inject(HttpClient);

  /** Moves these Frames' files to the OS Trash and takes them out of the Session. */
  trash(frameIds: number[]): Observable<TrashResult> {
    return this.http.post<TrashResult>('/api/frames/trash', { frame_ids: frameIds });
  }
}
