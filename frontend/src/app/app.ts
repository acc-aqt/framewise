import { httpResource } from '@angular/common/http';
import { ChangeDetectionStrategy, Component } from '@angular/core';
import { FrameGrid } from './frame-grid';
import { Frame, SessionSummary } from './session-api';
import { SessionSummaryView } from './session-summary';

@Component({
  selector: 'app-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FrameGrid, SessionSummaryView],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  protected readonly summary = httpResource<SessionSummary>(() => '/api/session');
  protected readonly frames = httpResource<Frame[]>(() => '/api/frames', { defaultValue: [] });
}
