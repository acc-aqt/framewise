import { httpResource } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, signal } from '@angular/core';
import { GroupGrid } from './group-grid';
import { GroupView } from './group-view';
import { Group, SessionSummary } from './session-api';
import { SessionSummaryView } from './session-summary';

@Component({
  selector: 'app-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [GroupGrid, GroupView, SessionSummaryView],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  protected readonly summary = httpResource<SessionSummary>(() => '/api/session');
  protected readonly groups = httpResource<Group[]>(() => '/api/groups', { defaultValue: [] });
  protected readonly openGroupId = signal<number | null>(null);
  protected readonly openGroup = computed(
    () => this.groups.value().find((group) => group.id === this.openGroupId()) ?? null,
  );
}
