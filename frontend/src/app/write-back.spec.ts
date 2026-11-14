import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { WriteBackDryRun, WriteBackFile, WriteBackProgress } from './session-api';
import { WriteBackView } from './write-back';

const dryRun: WriteBackDryRun = {
  label_set: { red: 'Rot', yellow: 'Gelb', from_lightroom: true },
  notice: null,
  files: [
    file(
      'DSCF0001.JPG',
      'DSCF0001.JPG',
      'winner',
      { stars: 1, label: null },
      { stars: 3, label: null },
    ),
    file(
      'DSCF0001.RAF',
      'DSCF0001.xmp',
      'winner',
      { stars: null, label: null },
      { stars: 3, label: null },
    ),
    file(
      'DSCF0002.JPG',
      'DSCF0002.JPG',
      'reject',
      { stars: null, label: null },
      { stars: 0, label: 'Rot' },
    ),
    file(
      'DSCF0003.JPG',
      'DSCF0003.JPG',
      'keeper',
      { stars: 2, label: null },
      { stars: 2, label: null },
    ),
  ],
  can_undo: false,
};

const idle: WriteBackProgress = { running: false, files_done: 0, files_total: null };

describe('Rating write-back', () => {
  let fixture: ComponentFixture<WriteBackView>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [WriteBackView],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(WriteBackView);
    TestBed.tick();
  });

  afterEach(() => http.verify());

  function element(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(selector: string, root: HTMLElement = element()): string {
    return root.querySelector(selector)?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
  }

  function all(selector: string): HTMLElement[] {
    return Array.from(element().querySelectorAll<HTMLElement>(selector));
  }

  async function settle(): Promise<void> {
    await Promise.resolve();
    TestBed.tick();
  }

  async function showDryRun(response: WriteBackDryRun = dryRun): Promise<void> {
    http.expectOne({ method: 'GET', url: '/api/write-back' }).flush(response);
    flushProgress();
    await settle();
  }

  function flushProgress(progress: WriteBackProgress = idle): void {
    for (const request of http.match('/api/write-back/progress')) {
      request.flush(progress);
    }
  }

  async function click(testId: string): Promise<void> {
    element().querySelector<HTMLButtonElement>(`[data-testid="${testId}"]`)!.click();
    await settle();
  }

  it('shows each file with its old and new rating and label', async () => {
    await showDryRun();

    const rows = all('[data-testid="write-back-file"]').map((row) =>
      Array.from(row.querySelectorAll('td')).map((cell) => cell.textContent?.trim()),
    );
    expect(rows).toEqual([
      ['DSCF0001.JPG', 'DSCF0001.JPG', 'Winner', '1★', '3★'],
      ['DSCF0001.RAF', 'DSCF0001.xmp', 'Winner', 'No rating', '3★'],
      ['DSCF0002.JPG', 'DSCF0002.JPG', 'Reject', 'No rating', '0★ Rot'],
      ['DSCF0003.JPG', 'DSCF0003.JPG', 'Keeper', '2★', '2★'],
    ]);
    expect(text('[data-testid="write-back-count"]')).toBe('3 of 4 files change.');
  });

  it('says when the English label names are used', async () => {
    await showDryRun({
      ...dryRun,
      label_set: { red: 'Red', yellow: 'Yellow', from_lightroom: false },
      notice: 'No Lightroom Classic color label set was found.',
    });

    expect(text('[data-testid="write-back-notice"]')).toBe(
      'No Lightroom Classic color label set was found.',
    );
  });

  it('writes only after the photographer confirms', async () => {
    await showDryRun();

    await click('write-back-apply');
    http.expectNone({ method: 'POST' });
    expect(text('[data-testid="write-back-confirmation"]')).toContain('3 files');

    await click('write-back-confirm');
    http.expectOne({ method: 'POST', url: '/api/write-back' }).flush({
      written: ['DSCF0001.JPG', 'DSCF0001.RAF', 'DSCF0002.JPG'],
      failed: [],
    });
    await settle();
    await showDryRun({ ...dryRun, can_undo: true });

    expect(text('[data-testid="write-back-result"]')).toBe('Wrote 3 files.');
  });

  it('writes nothing when the photographer cancels', async () => {
    await showDryRun();

    await click('write-back-apply');
    await click('write-back-cancel');

    http.expectNone({ method: 'POST' });
    expect(all('[data-testid="write-back-confirmation"]')).toEqual([]);
  });

  it('reports files that could not be written', async () => {
    await showDryRun();

    await click('write-back-apply');
    await click('write-back-confirm');
    http.expectOne({ method: 'POST', url: '/api/write-back' }).flush({
      written: ['DSCF0001.JPG'],
      failed: [{ path: 'DSCF0002.JPG', error: 'File is read-only' }],
    });
    await settle();
    await showDryRun();

    expect(text('[data-testid="write-back-result"]')).toContain('Wrote 1 file.');
    expect(text('[data-testid="write-back-failures"]')).toBe('DSCF0002.JPG: File is read-only');
  });

  it('offers undo once ratings have been written', async () => {
    await showDryRun({ ...dryRun, can_undo: true });

    await click('write-back-undo');
    http.expectOne({ method: 'POST', url: '/api/write-back/undo' }).flush({
      written: ['DSCF0001.JPG', 'DSCF0001.xmp'],
      failed: [],
    });
    await settle();
    await showDryRun();

    expect(text('[data-testid="write-back-result"]')).toBe('Restored 2 files.');
    expect(all('[data-testid="write-back-undo"]')).toEqual([]);
  });

  it('says that it is reading the files while the preview loads', async () => {
    flushProgress();
    await settle();

    expect(text('[data-testid="write-back-loading"]')).toBe(
      'Reading the current rating of every file…',
    );

    await showDryRun();

    expect(all('[data-testid="write-back-loading"]')).toEqual([]);
  });

  it('shows how many files are written while writing', async () => {
    await showDryRun();

    await click('write-back-apply');
    await click('write-back-confirm');
    expect(text('[data-testid="write-back-progress"]')).toBe(
      'Writing ratings: reading the current ratings…',
    );
    flushProgress({ running: true, files_done: 1, files_total: 3 });
    await settle();
    expect(text('[data-testid="write-back-progress"]')).toBe('Writing ratings: 1 of 3 files');

    http.expectOne({ method: 'POST', url: '/api/write-back' }).flush({ written: [], failed: [] });
    await settle();
    await showDryRun();
    expect(all('[data-testid="write-back-progress"]')).toEqual([]);
  });

  it('shows a write-back that is still running after the page was reloaded', async () => {
    http.expectOne({ method: 'GET', url: '/api/write-back' }).flush(dryRun);
    flushProgress({ running: true, files_done: 120, files_total: 1243 });
    await settle();

    expect(text('[data-testid="write-back-progress"]')).toBe('Writing files: 120 of 1243 files');
    expect(
      element().querySelector<HTMLButtonElement>('[data-testid="write-back-apply"]')!.disabled,
    ).toBe(true);
    expect(
      element().querySelector<HTMLButtonElement>('[data-testid="session-reset"]')!.disabled,
    ).toBe(true);
  });

  it('resets the Session only after the photographer confirms', async () => {
    let resets = 0;
    fixture.componentInstance.sessionReset.subscribe(() => resets++);
    await showDryRun();

    await click('session-reset');
    await click('session-reset-cancel');
    http.expectNone({ method: 'POST' });

    await click('session-reset');
    await click('session-reset-confirm');
    http.expectOne({ method: 'POST', url: '/api/session/reset' }).flush({
      written: ['DSCF0001.JPG'],
      failed: [],
    });
    await settle();
    await showDryRun();

    expect(text('[data-testid="write-back-result"]')).toBe(
      'Reset the Session and restored 1 file.',
    );
    expect(resets).toBe(1);
  });
});

function file(
  path: string,
  writtenTo: string,
  verdict: WriteBackFile['verdict'],
  old: WriteBackFile['old'],
  next: WriteBackFile['new'],
): WriteBackFile {
  return { frame_id: 1, path, written_to: writtenTo, verdict, old, new: next };
}
