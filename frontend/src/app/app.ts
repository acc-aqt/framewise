import { httpResource } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, effect, signal } from '@angular/core';
import { AnalysisProgressView } from './analysis-progress';
import { GroupGrid } from './group-grid';
import { GroupView } from './group-view';
import { AnalysisProgress, Group, SessionSummary } from './session-api';
import { SessionSummaryView } from './session-summary';

export const POLL_INTERVAL_MS = 1000;

@Component({
  selector: 'app-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [AnalysisProgressView, GroupGrid, GroupView, SessionSummaryView],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  protected readonly summary = httpResource<SessionSummary>(() => '/api/session');
  protected readonly progress = httpResource<AnalysisProgress>(() => '/api/progress');
  protected readonly analyzing = computed(
    () => this.progress.hasValue() && this.progress.value().frames_left > 0,
  );
  // Keyed on Frames done, so the Groups are fetched again each time more Frames are analysed.
  protected readonly groups = httpResource<Group[]>(
    () =>
      this.progress.hasValue()
        ? `/api/groups?frames_done=${this.progress.value().frames_done}`
        : undefined,
    { defaultValue: [] },
  );
  protected readonly openGroupId = signal<number | null>(null);
  protected readonly openGroup = computed(
    () => this.groups.value().find((group) => group.id === this.openGroupId()) ?? null,
  );

  constructor() {
    effect((onCleanup) => {
      if (!this.analyzing() || this.progress.isLoading()) {
        return;
      }
      const timer = setTimeout(() => this.progress.reload(), POLL_INTERVAL_MS);
      onCleanup(() => clearTimeout(timer));
    });
  }
}
