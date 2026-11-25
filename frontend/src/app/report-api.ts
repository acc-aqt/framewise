import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { ProblemReport, ReportImages } from './session-api';

export interface ProblemReportRequest {
  /** What the photographer expected instead. */
  text: string;
  /** Whether the report carries the Group's state. */
  include_state: boolean;
}

export interface ReportImagesRequest {
  /** Whether to remove location and owner info from the copies. */
  remove_personal_info: boolean;
}

@Injectable({ providedIn: 'root' })
export class ReportApi {
  private readonly http = inject(HttpClient);

  /** Builds a Problem report on the Group whose first Frame has `groupId`. */
  build(groupId: number, request: ProblemReportRequest): Observable<ProblemReport> {
    return this.http.post<ProblemReport>(`/api/groups/${groupId}/problem-report`, request);
  }

  /**
   * Copies the Group's Analysis sources into a folder on this computer and opens it in the file
   * manager. Nothing is uploaded.
   */
  prepareImages(groupId: number, request: ReportImagesRequest): Observable<ReportImages> {
    return this.http.post<ReportImages>(`/api/groups/${groupId}/problem-report/images`, request);
  }
}
