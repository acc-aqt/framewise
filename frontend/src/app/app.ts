import { httpResource } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, effect, signal } from '@angular/core';
import { AnalysisProgressView } from './analysis-progress';
import { GroupGrid } from './group-grid';
import { GroupView } from './group-view';
import { NO_FILTER, ProposalFilter } from './proposal';
import { ProposalFilters } from './proposal-filters';
import { AnalysisProgress, Group, SessionSummary } from './session-api';
import { SessionSummaryView } from './session-summary';

export const POLL_INTERVAL_MS = 1000;

@Component({
  selector: 'app-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [AnalysisProgressView, GroupGrid, GroupView, ProposalFilters, SessionSummaryView],
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
  // Without progress, the Groups are still fetched once so an analysed Session stays reviewable.
  protected readonly groups = httpResource<Group[]>(
    () => {
      if (this.progress.hasValue()) {
        return `/api/groups?frames_done=${this.progress.value().frames_done}`;
      }
      return this.progress.error() ? '/api/groups' : undefined;
    },
    { defaultValue: [] },
  );
  // Tracks the Frame the photographer opened rather than the Group id, which changes when a
  // Group gains an earlier Frame during analysis.
  protected readonly openedFrameId = signal<number | null>(null);
  protected readonly filter = signal<ProposalFilter>(NO_FILTER);
  protected readonly openGroup = computed(
    () =>
      this.groups
        .value()
        .find((group) => group.frames.some((frame) => frame.id === this.openedFrameId())) ?? null,
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
