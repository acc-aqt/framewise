import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { ProblemReport } from './session-api';

export interface ProblemReportRequest {
  /** What the photographer expected instead. */
  text: string;
  /** Whether the report carries the Group's state. */
  include_state: boolean;
}

@Injectable({ providedIn: 'root' })
export class ReportApi {
  private readonly http = inject(HttpClient);

  /** Builds a Problem report on the Group whose first Frame has `groupId`. */
  build(groupId: number, request: ProblemReportRequest): Observable<ProblemReport> {
    return this.http.post<ProblemReport>(`/api/groups/${groupId}/problem-report`, request);
  }
}
