import { HttpErrorResponse, httpResource } from '@angular/common/http';
import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  Injector,
  linkedSignal,
  signal,
  viewChild,
} from '@angular/core';
import { Observable } from 'rxjs';
import { AnalysisProgressView } from './analysis-progress';
import { AnalysisSettings } from './analysis-settings';
import { GroupGrid, stillSelected } from './group-grid';
import { GroupView } from './group-view';
import { Icon } from './icon';
import { KeeperBudget } from './keeper-budget';
import { Loupe, LoupeZoom } from './loupe';
import { OverrideApi } from './override-api';
import { findWinner, isFiltering, NO_FILTER, ProposalFilter } from './proposal';
import { ProposalFilters } from './proposal-filters';
import { AnalysisProgress, Frame, Group, OverrideChange, SessionSummary } from './session-api';
import { SessionChangeApi } from './session-change-api';
import { SessionPicker } from './session-picker';
import { SessionSummaryView } from './session-summary';
import { CommandPalette } from './command-palette';
import {
  Command,
  CommandContext,
  COMMANDS,
  frameAfterTrash,
  isPaletteKey,
  PALETTE_KEY,
  Shortcut,
  shortcutFor,
  stepFrom,
} from './shortcuts';
import { Tooltip, TooltipContent } from './tooltip';
import { TrashApi, TrashResult } from './trash-api';
import { TrashConfirmation } from './trash-confirmation';
import { WriteBackView } from './write-back';

export const POLL_INTERVAL_MS = 1000;

/** Frames waiting for the photographer to confirm they go to the Trash. */
interface PendingTrash {
  frames: Frame[];
  /** How many Groups the Frames make up, when whole Groups go from All Groups. */
  groupCount: number | null;
  /** The grid position of the first of those Groups, in capture order. */
  tileIndex: number | null;
}

@Component({
  selector: 'app-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '(document:keydown)': 'onKeydown($event)' },
  imports: [
    AnalysisProgressView,
    AnalysisSettings,
    CommandPalette,
    GroupGrid,
    GroupView,
    Icon,
    KeeperBudget,
    Loupe,
    ProposalFilters,
    SessionPicker,
    SessionSummaryView,
    Tooltip,
    TrashConfirmation,
    WriteBackView,
  ],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  protected readonly summary = httpResource<SessionSummary>(() => '/api/session');
  // framewise started without a Session folder, so the photographer chooses one here.
  protected readonly noSession = computed(() => {
    const error = this.summary.error();
    return error instanceof HttpErrorResponse && error.status === 404;
  });
  protected readonly progress = httpResource<AnalysisProgress>(() => '/api/progress');
  protected readonly analyzing = computed(
    () => this.progress.hasValue() && this.progress.value().frames_left > 0,
  );
  protected readonly writeBackTooltip: TooltipContent = {
    label: 'Rating write-back',
    explanation:
      "Previews the star ratings and color labels for your reviewed Verdicts, and writes them into the Frames' files only once you confirm.",
  };
  // Keyed on Frames done, so the Groups are fetched again each time more Frames are analyzed.
  // Without progress, the Groups are still fetched once so an analyzed Session stays reviewable.
  protected readonly groupsResource = httpResource<Group[]>(
    () => {
      if (this.progress.hasValue()) {
        return `/api/groups?frames_done=${this.progress.value().frames_done}`;
      }
      return this.progress.error() ? '/api/groups' : undefined;
    },
    { defaultValue: [] },
  );
  // While a changed request loads, the resource falls back to no Groups, so the last loaded
  // Groups are kept until the next ones arrive rather than blanking the grid.
  protected readonly groups = linkedSignal<Group[] | undefined, Group[]>({
    source: () =>
      this.groupsResource.isLoading() || this.groupsResource.error()
        ? undefined
        : this.groupsResource.value(),
    computation: (groups, previous) => groups ?? previous?.value ?? [],
  });
  // Tracks the Frame the photographer opened rather than the Group id, which changes when a
  // Group gains an earlier Frame during analysis.
  protected readonly openedFrameId = signal<number | null>(null);
  protected readonly filter = signal<ProposalFilter>(NO_FILTER);
  /** The Groups selected in All Groups. A filter clears the selection. */
  protected readonly selectedGroups = linkedSignal<
    { groups: Group[]; filtering: boolean },
    Group[]
  >({
    source: () => ({ groups: this.groups(), filtering: isFiltering(this.filter()) }),
    computation: (source, previous) =>
      source.filtering || previous === undefined
        ? []
        : stillSelected(previous.source.groups, previous.value, source.groups),
  });
  protected readonly writingBack = signal(false);
  protected readonly openGroup = computed(
    () =>
      this.groups().find((group) =>
        group.frames.some((frame) => frame.id === this.openedFrameId()),
      ) ?? null,
  );
  protected readonly currentFrame = computed(
    () => this.openGroup()?.frames.find((frame) => frame.id === this.openedFrameId()) ?? null,
  );
  protected readonly loupeZoom = signal<LoupeZoom | null>(null);
  /** Whether the loupe compares the current Frame with the Group's Winner. */
  protected readonly comparing = signal(false);
  protected readonly loupeFrames = computed(() => {
    const frame = this.currentFrame();
    const group = this.openGroup();
    if (frame === null || group === null) {
      return [];
    }
    const winner = this.comparing() ? findWinner(group) : undefined;
    return winner === undefined ? [frame] : [frame, winner];
  });
  /** Where the current Frame sits in its Group, counting from 1. */
  protected readonly loupePosition = computed(() => {
    const frame = this.currentFrame();
    const group = this.openGroup();
    return frame === null || group === null
      ? null
      : { index: group.frames.indexOf(frame) + 1, total: group.frames.length };
  });
  protected readonly overrideFailed = signal(false);
  protected readonly keeperBudget = linkedSignal(() =>
    this.summary.hasValue() ? this.summary.value().keeper_budget : null,
  );
  protected readonly keeperBudgetFailed = signal(false);
  /** Rating write-back writes to a JPG-only Frame's file and to both files of a RAW+JPG Frame. */
  protected readonly sessionFileCount = computed(() => {
    if (!this.summary.hasValue()) {
      return null;
    }
    const { jpg_only_count, raw_jpg_count } = this.summary.value();
    return jpg_only_count + 2 * raw_jpg_count;
  });
  protected readonly trashing = signal<PendingTrash | null>(null);
  // Set by a Trash until the Groups are requested again. A request already under way, such as
  // one for an analysis poll, may predate the Trash, so the Groups are requested once it ends.
  private readonly groupsNeedReload = signal(false);
  /** The grid position to focus once the Groups reload after a Trash from All Groups. */
  private readonly tileToFocus = signal<number | null>(null);
  private readonly groupGrid = viewChild(GroupGrid);
  protected readonly trashError = signal<string | null>(null);
  protected readonly paletteOpen = signal(false);
  protected readonly paletteAvailable = computed(
    () => !this.noSession() && !this.writingBack() && this.trashing() === null,
  );
  protected readonly commands = COMMANDS;
  protected readonly commandContext = computed<CommandContext>(() => {
    const frame = this.currentFrame();
    const group = this.openGroup();
    const frameOpen = frame !== null && group !== null;
    return {
      frameOpen,
      hasPreviousGroup: frameOpen && this.neighbourGroup(-1) !== null,
      hasNextGroup: frameOpen && this.neighbourGroup(1) !== null,
      canSplitHere: frameOpen && group.frames[0] !== frame,
      canMakeWinner: frameOpen && frame.verdict !== 'winner',
      selectedGroupCount: this.selectedGroups().length,
      writeBackAvailable: this.summary.hasValue() && !this.analyzing(),
    };
  });
  protected readonly paletteKey = PALETTE_KEY;
  protected readonly paletteTooltip: TooltipContent = { label: 'Commands', key: PALETTE_KEY };

  private readonly overrideApi = inject(OverrideApi);
  private readonly sessionChangeApi = inject(SessionChangeApi);
  private readonly trashApi = inject(TrashApi);

  constructor() {
    effect((onCleanup) => {
      if (!this.analyzing() || this.progress.isLoading()) {
        return;
      }
      const timer = setTimeout(() => this.progress.reload(), POLL_INTERVAL_MS);
      onCleanup(() => clearTimeout(timer));
    });
    effect(() => {
      if (this.groupsNeedReload() && !this.groupsResource.isLoading()) {
        this.groupsNeedReload.set(false);
        this.groupsResource.reload();
      }
    });
    const injector = inject(Injector);
    effect(() => {
      const index = this.tileToFocus();
      const reloadedAfterTrash = !this.groupsNeedReload() && !this.groupsResource.isLoading();
      if (index === null || !reloadedAfterTrash) {
        return;
      }
      this.tileToFocus.set(null);
      afterNextRender(() => this.groupGrid()?.focusTile(index), { injector });
    });
  }

  protected openSession(): void {
    this.summary.reload();
    this.progress.reload();
  }

  protected onKeydown(event: KeyboardEvent): void {
    if (isPaletteKey(event)) {
      if (this.paletteAvailable()) {
        event.preventDefault();
        this.paletteOpen.update((open) => !open);
      }
      return;
    }
    if (this.paletteOpen()) {
      if (event.key === 'Escape') {
        this.paletteOpen.set(false);
      }
      return;
    }
    if (this.trashing() !== null) {
      if (event.key === 'Escape') {
        this.trashing.set(null);
      }
      return;
    }
    const shortcut = shortcutFor(event);
    if (shortcut === null) {
      return;
    }
    const frame = this.currentFrame();
    if (frame !== null) {
      event.preventDefault();
      this.run(shortcut, frame);
    } else if (this.selectedGroups().length > 0) {
      this.runOnSelectedGroups(shortcut, event);
    }
  }

  protected runCommand(command: Command): void {
    this.paletteOpen.set(false);
    if (command.shortcut.kind === 'writeBack') {
      return this.openWriteBack();
    }
    if (command.shortcut.kind === 'trashGroups') {
      return this.askToTrashGroups(this.selectedGroups());
    }
    const frame = this.currentFrame();
    if (frame !== null) {
      this.run(command.shortcut, frame);
    }
  }

  protected openFromGrid(frame: Frame): void {
    this.selectedGroups.set([]);
    this.openedFrameId.set(frame.id);
  }

  protected clearFilters(): void {
    this.filter.set(NO_FILTER);
  }

  protected openWriteBack(): void {
    this.closeGroup();
    this.selectedGroups.set([]);
    this.writingBack.set(true);
  }

  protected changeOverride(frame: Frame, change: OverrideChange): void {
    this.save(this.overrideApi.change(frame.id, change));
  }

  /** The Group `by` Groups before or after the open Group, in capture order. */
  protected neighbourGroup(by: -1 | 1): Group | null {
    const groups = this.groups();
    const index = groups.findIndex((group) => group === this.openGroup());
    return index === -1 ? null : (groups[index + by] ?? null);
  }

  protected splitGroup(frames: Frame[]): void {
    this.save(this.overrideApi.split(frames.map((frame) => frame.id)));
  }

  protected mergeGroup(group: Group, by: -1 | 1): void {
    const neighbour = this.neighbourGroup(by);
    if (neighbour !== null) {
      this.save(this.overrideApi.merge([group.frames[0].id, neighbour.frames[0].id]));
    }
  }

  protected resetGrouping(group: Group): void {
    this.save(this.overrideApi.resetGrouping([group.frames[0].id]));
  }

  protected moveFrame(frame: Frame, by: -1 | 1): void {
    const neighbour = this.neighbourGroup(by);
    if (neighbour !== null) {
      this.save(this.overrideApi.move(frame.id, neighbour.frames[0].id));
    }
  }

  protected askToTrash(frames: Frame[]): void {
    if (frames.length > 0) {
      this.trashing.set({ frames, groupCount: null, tileIndex: null });
    }
  }

  protected askToTrashGroups(groups: Group[]): void {
    if (groups.length > 0) {
      this.trashing.set({
        frames: groups.flatMap((group) => group.frames),
        groupCount: groups.length,
        tileIndex: this.groups().indexOf(groups[0]),
      });
    }
  }

  protected confirmTrash(): void {
    const trash = this.trashing();
    this.trashing.set(null);
    if (trash === null) {
      return;
    }
    this.trashApi.trash(trash.frames.map((frame) => frame.id)).subscribe({
      next: (result) => {
        if (trash.tileIndex !== null) {
          this.tileToFocus.set(trash.tileIndex);
        }
        this.afterTrash(result);
      },
      error: () => this.trashError.set('Could not move the Frames to the Trash.'),
    });
  }

  protected changeKeeperBudget(share: number): void {
    this.keeperBudget.set(share);
    this.sessionChangeApi.changeKeeperBudget(share).subscribe({
      next: () => {
        this.keeperBudgetFailed.set(false);
        this.groupsResource.reload();
      },
      error: () => this.keeperBudgetFailed.set(true),
    });
  }

  protected onSessionReset(): void {
    this.summary.reload();
    this.groupsResource.reload();
  }

  protected closeGroup(): void {
    this.closeLoupe();
    this.openedFrameId.set(null);
  }

  protected openLoupe(): void {
    this.comparing.set(false);
    this.loupeZoom.set('fit');
  }

  protected openCompareLoupe(): void {
    this.comparing.set(true);
    this.loupeZoom.set('fit');
  }

  protected closeLoupe(): void {
    this.comparing.set(false);
    this.loupeZoom.set(null);
  }

  protected toggleZoom(): void {
    this.loupeZoom.update((zoom) => (zoom === '100%' ? 'fit' : '100%'));
  }

  private run(shortcut: Shortcut, frame: Frame): void {
    switch (shortcut.kind) {
      case 'stars':
        return this.changeOverride(frame, { stars: shortcut.stars });
      case 'label': {
        const label = frame.override?.label === shortcut.label ? null : shortcut.label;
        return this.changeOverride(frame, { label });
      }
      case 'keep':
        return this.changeOverride(frame, {
          verdict: frame.verdict === 'winner' ? 'winner' : 'keeper',
        });
      case 'reject':
        return this.changeOverride(frame, { verdict: 'reject' });
      case 'clear':
        return this.save(this.overrideApi.clear(frame.id));
      case 'step':
        return this.openedFrameId.set(
          stepFrom(this.groups(), frame.id, shortcut.by, shortcut.withinGroup || this.comparing()),
        );
      case 'loupe':
        return this.openLoupe();
      case 'compare':
        return this.openCompareLoupe();
      case 'zoom':
        return this.toggleZoom();
      case 'close':
        return this.loupeZoom() === null ? this.closeGroup() : this.closeLoupe();
      case 'allGroups':
        return this.closeGroup();
      case 'merge':
        return this.mergeGroup(this.openGroup()!, shortcut.by);
      case 'splitHere': {
        const frames = this.openGroup()!.frames;
        return this.splitGroup(frames.slice(frames.indexOf(frame)));
      }
      case 'move':
        return this.moveFrame(frame, shortcut.by);
      case 'trash':
        return this.askToTrash([frame]);
      case 'trashGroup':
        return this.askToTrash(this.openGroup()!.frames);
      case 'makeWinner':
        return frame.verdict === 'winner'
          ? undefined
          : this.changeOverride(frame, { verdict: 'winner' });
    }
  }

  /** In All Groups, ⌫/Delete trashes the selected Groups and Escape clears the selection. */
  private runOnSelectedGroups(shortcut: Shortcut, event: KeyboardEvent): void {
    if (shortcut.kind === 'trash') {
      event.preventDefault();
      this.askToTrashGroups(this.selectedGroups());
    } else if (shortcut.kind === 'close') {
      event.preventDefault();
      this.selectedGroups.set([]);
    }
  }

  private afterTrash(result: TrashResult): void {
    const current = this.openedFrameId();
    if (current !== null) {
      const next = frameAfterTrash(this.groups(), current, result.trashed);
      if (next === null) {
        this.closeGroup();
      } else {
        this.openedFrameId.set(next);
      }
    }
    if (result.failed.length === 0) {
      this.selectedGroups.set([]);
    }
    this.trashError.set(
      result.failed.length === 0
        ? null
        : `Could not move ${result.failed.map((failure) => failure.path).join(', ')} to the Trash: ${result.failed[0].error}`,
    );
    this.summary.reload();
    this.groupsNeedReload.set(true);
  }

  private save(request: Observable<unknown>): void {
    request.subscribe({
      next: () => {
        this.overrideFailed.set(false);
        this.groupsResource.reload();
      },
      error: () => this.overrideFailed.set(true),
    });
  }
}
