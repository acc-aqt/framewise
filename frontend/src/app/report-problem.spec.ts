import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ReportProblem } from './report-problem';
import { ProblemReport, ReportImages } from './session-api';

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

  function all(testId: string): string[] {
    return [...element().querySelectorAll(`[data-testid="${testId}"]`)].map(
      (row) => row.textContent?.replace(/\s+/g, ' ').trim() ?? '',
    );
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

  describe('Include images', () => {
    const prepared: ReportImages = {
      folder: '/data/framewise/problem-report-images',
      files: [
        { name: 'DSCF0001.JPG', size: 4_200_000, too_large: false },
        { name: 'DSCF0002.RAF.jpg', size: 12_400_000, too_large: true },
      ],
      personal_info_removed: false,
    };

    beforeEach(() => {
      fixture.componentRef.setInput('frames', [
        { id: 7, main_path: 'card-a/DSCF0001.JPG' },
        { id: 8, main_path: 'card-a/DSCF0002.RAF' },
      ]);
      TestBed.tick();
    });

    function includeImages(): HTMLInputElement {
      return byTestId<HTMLInputElement>('report-include-images');
    }

    async function tickIncludeImages(): Promise<void> {
      includeImages().click();
      await settle();
    }

    async function openOnGitHub(): Promise<void> {
      const tab = { opener: null, location: { href: '' }, close: vi.fn() };
      vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window);
      await type('DSCF0003 should be the Winner');
      await click('report-open-github');
      await answer();
    }

    async function answerImages(images: ReportImages = prepared): Promise<void> {
      const request = http.expectOne({
        method: 'POST',
        url: '/api/groups/7/problem-report/images',
      });
      expect(request.request.body).toEqual({ remove_personal_info: false });
      request.flush(images);
      await settle();
      await settle();
    }

    it('is off by default and lists no Frames', () => {
      expect(includeImages().checked).toBe(false);
      expect(byTestId('report-image-frames')).toBeNull();
    });

    it("lists the Group's Frames by file name when ticked", async () => {
      await tickIncludeImages();

      expect(all('report-image-frame')).toEqual(['DSCF0001.JPG', 'DSCF0002.RAF']);
    });

    it('prepares no images when it is not ticked', async () => {
      await openOnGitHub();

      http.expectNone('/api/groups/7/problem-report/images');
      expect(byTestId('report-image-files')).toBeNull();
    });

    it('prepares the images and shows the files, flagging those too large for GitHub', async () => {
      await tickIncludeImages();

      await openOnGitHub();
      await answerImages();

      const [small, large] = element().querySelectorAll('[data-testid="report-image-file"]');
      expect(small.textContent).toContain('DSCF0001.JPG');
      expect(small.textContent).toContain('4.2 MB');
      expect(small.querySelector('[data-testid="report-image-too-large"]')).toBeNull();
      expect(large.textContent).toContain('DSCF0002.RAF.jpg');
      expect(large.textContent).toContain('12.4 MB');
      expect(
        large.querySelector('[data-testid="report-image-too-large"]')?.textContent?.trim(),
      ).toBe("Over GitHub's 10 MB limit, share it another way");
      expect(text('report-images-folder')).toContain('/data/framewise/problem-report-images');
    });

    it('says so when the images could not be prepared', async () => {
      await tickIncludeImages();

      await openOnGitHub();
      http
        .expectOne('/api/groups/7/problem-report/images')
        .flush({ detail: 'Group not found' }, { status: 404, statusText: 'Not Found' });
      await settle();
      await settle();

      expect(text('report-error')).toBe('Could not prepare the images.');
    });
  });

  it('closes on Cancel', async () => {
    const closed = vi.fn();
    fixture.componentInstance.close.subscribe(closed);

    await click('report-cancel');

    expect(closed).toHaveBeenCalled();
  });
});
