import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ReportProblem } from './report-problem';
import { ProblemReport } from './session-api';

const built: ProblemReport = {
  title: 'Judging problem: DSCF0003 should be the Winner',
  body: 'DSCF0003 should be the Winner\n',
  issue_url: 'https://github.com/acc-aqt/framewise/issues/new?template=judging-problem.md',
  body_fits_url: true,
};

describe('Report a problem', () => {
  let fixture: ComponentFixture<ReportProblem>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [ReportProblem],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(ReportProblem);
    fixture.componentRef.setInput('groupId', 7);
    TestBed.tick();
  });

  afterEach(() => {
    http.verify();
    vi.restoreAllMocks();
  });

  function element(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function byTestId<T extends HTMLElement>(testId: string): T {
    return element().querySelector<T>(`[data-testid="${testId}"]`)!;
  }

  function text(testId: string): string {
    return byTestId(testId)?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
  }

  async function settle(): Promise<void> {
    await Promise.resolve();
    TestBed.tick();
  }

  async function type(value: string): Promise<void> {
    const field = byTestId<HTMLTextAreaElement>('report-text');
    field.value = value;
    field.dispatchEvent(new Event('input'));
    await settle();
  }

  async function click(testId: string): Promise<void> {
    byTestId<HTMLButtonElement>(testId).click();
    await settle();
  }

  async function answer(report: ProblemReport = built): Promise<void> {
    const request = http.expectOne({ method: 'POST', url: '/api/groups/7/problem-report' });
    expect(request.request.body).toEqual({
      text: 'DSCF0003 should be the Winner',
      include_state: true,
    });
    request.flush(report);
    await settle();
    await settle();
  }

  function actionsEnabled(): boolean[] {
    return ['report-open-github', 'report-copy', 'report-save'].map(
      (testId) => !byTestId<HTMLButtonElement>(testId).disabled,
    );
  }

  it('asks what the photographer expected instead', () => {
    expect(element().textContent).toContain('What did you expect instead?');
  });

  it('keeps every action disabled until the photographer says what they expected', async () => {
    expect(actionsEnabled()).toEqual([false, false, false]);

    await type('  \n ');
    expect(actionsEnabled()).toEqual([false, false, false]);

    await type('DSCF0003 should be the Winner');
    expect(actionsEnabled()).toEqual([true, true, true]);
  });

  it('opens the prefilled new-issue page in a new tab', async () => {
    const tab = { opener: window as Window | null, location: { href: '' }, close: vi.fn() };
    const open = vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window);
    await type('DSCF0003 should be the Winner');

    await click('report-open-github');
    await answer();

    expect(open).toHaveBeenCalledWith('', '_blank');
    expect(tab.location.href).toBe(built.issue_url);
    expect(tab.opener).toBeNull();
  });

  it('opens the new-issue page directly when the blank tab was blocked', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    await type('DSCF0003 should be the Winner');

    await click('report-open-github');
    await answer();

    expect(open).toHaveBeenLastCalledWith(built.issue_url, '_blank', 'noopener');
  });

  it('closes the opened tab and says so when the report could not be built', async () => {
    const tab = { opener: null, location: { href: '' }, close: vi.fn() };
    vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window);
    await type('DSCF0003 should be the Winner');

    await click('report-open-github');
    http
      .expectOne('/api/groups/7/problem-report')
      .flush({ detail: 'Group not found' }, { status: 404, statusText: 'Not Found' });
    await settle();
    await settle();

    expect(tab.close).toHaveBeenCalled();
    expect(text('report-error')).toBe('Could not build the report.');
  });

  it('copies the report to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    await type('DSCF0003 should be the Winner');

    await click('report-copy');
    await answer();

    expect(writeText).toHaveBeenCalledWith(built.body);
    expect(text('report-status')).toBe('Report copied to the clipboard.');
  });

  it('saves the report as a dated Markdown file', async () => {
    vi.useFakeTimers({ now: new Date(2026, 10, 25, 9, 30), toFake: ['Date'] });
    const blobs: Blob[] = [];
    URL.createObjectURL = vi.fn((blob: Blob) => {
      blobs.push(blob);
      return 'blob:report';
    });
    URL.revokeObjectURL = vi.fn();
    const downloads: { download: string; href: string }[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      downloads.push({ download: this.download, href: this.href });
    });
    await type('DSCF0003 should be the Winner');

    await click('report-save');
    await answer();
    vi.useRealTimers();

    expect(downloads).toEqual([
      { download: 'framewise-report-2026-11-25.md', href: 'blob:report' },
    ]);
    expect(await blobs[0].text()).toBe(built.body);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:report');
    expect(text('report-status')).toBe('Report saved as framewise-report-2026-11-25.md.');
  });

  it('closes on Cancel', async () => {
    const closed = vi.fn();
    fixture.componentInstance.close.subscribe(closed);

    await click('report-cancel');

    expect(closed).toHaveBeenCalled();
  });
});
