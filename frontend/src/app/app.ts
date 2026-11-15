import { HttpErrorResponse, httpResource } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  linkedSignal,
  signal,
} from '@angular/core';
import { Observable } from 'rxjs';
import { AnalysisProgressView } from './analysis-progress';
import { AnalysisSettings } from './analysis-settings';
import { GroupGrid } from './group-grid';
import { GroupView } from './group-view';
import { Icon } from './icon';
import { KeeperBudget } from './keeper-budget';
import { Loupe, LoupeZoom } from './loupe';
import { OverrideApi } from './override-api';
import { findWinner, NO_FILTER, ProposalFilter } from './proposal';
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
  isPaletteKey,
  PALETTE_KEY,
  Shortcut,
  shortcutFor,
  stepFrom,
} from './shortcuts';
import { Tooltip, TooltipContent } from './tooltip';
import { WriteBackView } from './write-back';

export const POLL_INTERVAL_MS = 1000;

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
  protected readonly writingBack = signal(false);
  protected readonly openGroup = computed(
    () =>
      this.groups
        .value()
        .find((group) => group.frames.some((frame) => frame.id === this.openedFrameId())) ?? null,
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
  protected readonly overrideFailed = signal(false);
  protected readonly keeperBudget = linkedSignal(() =>
    this.summary.hasValue() ? this.summary.value().keeper_budget : null,
  );
  protected readonly keeperBudgetFailed = signal(false);
  protected readonly paletteOpen = signal(false);
  protected readonly paletteAvailable = computed(() => !this.noSession() && !this.writingBack());
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
      writeBackAvailable: this.summary.hasValue() && !this.analyzing(),
    };
  });
  protected readonly paletteKey = PALETTE_KEY;
  protected readonly paletteTooltip: TooltipContent = { label: 'Commands', key: PALETTE_KEY };

  private readonly overrideApi = inject(OverrideApi);
  private readonly sessionChangeApi = inject(SessionChangeApi);

  constructor() {
    effect((onCleanup) => {
      if (!this.analyzing() || this.progress.isLoading()) {
        return;
      }
      const timer = setTimeout(() => this.progress.reload(), POLL_INTERVAL_MS);
      onCleanup(() => clearTimeout(timer));
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
    const frame = this.currentFrame();
    const shortcut = frame === null ? null : shortcutFor(event);
    if (frame === null || shortcut === null) {
      return;
    }
    event.preventDefault();
    this.run(shortcut, frame);
  }

  protected runCommand(command: Command): void {
    this.paletteOpen.set(false);
    if (command.shortcut.kind === 'writeBack') {
      return this.openWriteBack();
    }
    const frame = this.currentFrame();
    if (frame !== null) {
      this.run(command.shortcut, frame);
    }
  }

  protected openWriteBack(): void {
    this.closeGroup();
    this.writingBack.set(true);
  }

  protected changeOverride(frame: Frame, change: OverrideChange): void {
    this.save(this.overrideApi.change(frame.id, change));
  }

  /** The Group `by` Groups before or after the open Group, in capture order. */
  protected neighbourGroup(by: -1 | 1): Group | null {
    const groups = this.groups.value();
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

  protected changeKeeperBudget(share: number): void {
    this.keeperBudget.set(share);
    this.sessionChangeApi.changeKeeperBudget(share).subscribe({
      next: () => {
        this.keeperBudgetFailed.set(false);
        this.groups.reload();
      },
      error: () => this.keeperBudgetFailed.set(true),
    });
  }

  protected onSessionReset(): void {
    this.summary.reload();
    this.groups.reload();
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
          stepFrom(
            this.groups.value(),
            frame.id,
            shortcut.by,
            shortcut.withinGroup || this.comparing(),
          ),
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
      case 'makeWinner':
        return frame.verdict === 'winner'
          ? undefined
          : this.changeOverride(frame, { verdict: 'winner' });
    }
  }

  private save(request: Observable<unknown>): void {
    request.subscribe({
      next: () => {
        this.overrideFailed.set(false);
        this.groups.reload();
      },
      error: () => this.overrideFailed.set(true),
    });
  }
}
