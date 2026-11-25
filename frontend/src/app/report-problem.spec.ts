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

class FakeClipboardItem {
  constructor(private readonly items: Record<string, Promise<Blob>>) {}

  getType(type: string): Promise<Blob> {
    return this.items[type];
  }
}

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
    vi.unstubAllGlobals();
  });

  /** A clipboard that, like a browser's, takes an item's text only once its promise settles. */
  function fakeClipboard() {
    const clipboard = {
      contents: null as string | null,
      write: vi.fn(async (items: FakeClipboardItem[]) => {
        clipboard.contents = await (await items[0].getType('text/plain')).text();
      }),
      writeText: vi.fn(async (value: string) => {
        clipboard.contents = value;
      }),
    };
    vi.stubGlobal('ClipboardItem', FakeClipboardItem);
    Object.defineProperty(navigator, 'clipboard', { value: clipboard, configurable: true });
    return clipboard;
  }

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

  /** Lets every pending promise settle, however long its chain. */
  async function finish(): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve));
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

  async function answer(
    report: ProblemReport = built,
    text = 'DSCF0003 should be the Winner',
    includeState = true,
  ): Promise<void> {
    const request = http.expectOne({ method: 'POST', url: '/api/groups/7/problem-report' });
    expect(request.request.body).toEqual({ text, include_state: includeState });
    request.flush(report);
    await finish();
  }

  function actionsEnabled(): boolean[] {
    return ['report-open-github', 'report-copy', 'report-save'].map(
      (testId) => !byTestId<HTMLButtonElement>(testId).disabled,
    );
  }

  it('asks what the photographer expected instead', () => {
    expect(element().textContent).toContain('What did you expect instead?');
  });

  it('includes the Group state by default', () => {
    expect(text('report-include-state')).toBe('Include Group state');
    expect(byTestId<HTMLInputElement>('report-include-state-box').checked).toBe(true);
  });

  it('leaves the Group state out when the photographer unticks it', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    await type('DSCF0003 should be the Winner');

    await click('report-include-state-box');
    await click('report-copy');
    await answer(built, undefined, false);

    expect(writeText).toHaveBeenCalledWith(built.body);
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

  describe('when the report is too long for the link', () => {
    const longText = 'DSCF0003 is sharper and should be the Winner. '.repeat(200).trim();
    const tooLong: ProblemReport = {
      title: 'Judging problem: DSCF0003 is sharper and should be the Winner.',
      body: `${longText}\n`,
      issue_url: 'https://github.com/acc-aqt/framewise/issues/new?body=Paste+it+here',
      body_fits_url: false,
    };

    it('copies the full report before opening the new-issue page and says to paste it', async () => {
      const clipboard = fakeClipboard();
      const opened: { url: string; clipboard: string | null }[] = [];
      const tab = {
        opener: null,
        close: vi.fn(),
        location: {
          set href(url: string) {
            opened.push({ url, clipboard: clipboard.contents });
          },
        },
      };
      vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window);
      await type(longText);

      await click('report-open-github');
      expect(clipboard.write).toHaveBeenCalled();
      await answer(tooLong, longText);

      expect(opened).toEqual([{ url: tooLong.issue_url, clipboard: tooLong.body }]);
      expect(text('report-status')).toBe(
        "The report didn't fit in the link, so it's on your clipboard. Paste it into the new issue.",
      );
    });

    it('says to save the report when it could not be copied', async () => {
      const clipboard = fakeClipboard();
      clipboard.write.mockRejectedValue(new DOMException('Not allowed', 'NotAllowedError'));
      const tab = { opener: null, location: { href: '' }, close: vi.fn() };
      vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window);
      await type(longText);

      await click('report-open-github');
      await answer(tooLong, longText);

      expect(tab.location.href).toBe(tooLong.issue_url);
      expect(text('report-error')).toBe(
        "The report didn't fit in the link and could not be copied. Save report and paste it into the new issue.",
      );
    });
  });

  it('leaves the clipboard alone when the whole report fits in the link', async () => {
    const clipboard = fakeClipboard();
    const tab = { opener: null, location: { href: '' }, close: vi.fn() };
    vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window);
    await type('DSCF0003 should be the Winner');

    await click('report-open-github');
    await answer();

    expect(tab.location.href).toBe(built.issue_url);
    expect(clipboard.contents).toBeNull();
    expect(text('report-status')).toBe('');
  });

  it('closes the opened tab and says so when the report could not be built', async () => {
    const tab = { opener: null, location: { href: '' }, close: vi.fn() };
    vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window);
    await type('DSCF0003 should be the Winner');

    await click('report-open-github');
    http
      .expectOne('/api/groups/7/problem-report')
      .flush({ detail: 'Group not found' }, { status: 404, statusText: 'Not Found' });
    await finish();

    expect(tab.close).toHaveBeenCalled();
    expect(text('report-error')).toBe('Could not build the report.');
  });

  it('starts copying the report within the click, before the report is built', async () => {
    const clipboard = fakeClipboard();
    await type('DSCF0003 should be the Winner');

    await click('report-copy');
    expect(clipboard.write).toHaveBeenCalled();
    await answer();

    expect(clipboard.contents).toBe(built.body);
    expect(text('report-status')).toBe('Report copied to the clipboard.');
  });

  it('copies the report as plain text where the browser has no clipboard items', async () => {
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
      skipped: [],
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

    function removePersonalInfo(): HTMLInputElement {
      return byTestId<HTMLInputElement>('report-remove-personal-info');
    }

    async function answerImages(
      images: ReportImages = prepared,
      removalAsked = true,
    ): Promise<void> {
      const request = http.expectOne({
        method: 'POST',
        url: '/api/groups/7/problem-report/images',
      });
      expect(request.request.body).toEqual({ remove_personal_info: removalAsked });
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

    it('names the Frames whose images could not be found', async () => {
      await tickIncludeImages();

      await openOnGitHub();
      await answerImages({ ...prepared, skipped: ['DSCF0003.JPG', 'DSCF0004.JPG'] });

      expect(text('report-images-skipped')).toBe(
        'framewise could not find the images of DSCF0003.JPG and DSCF0004.JPG, so they are not in the folder.',
      );
    });

    it('names no skipped Frames when every image was copied', async () => {
      await tickIncludeImages();

      await openOnGitHub();
      await answerImages();

      expect(byTestId('report-images-skipped')).toBeNull();
    });

    describe('Remove location and owner info', () => {
      it('is offered only with images, and ticked by default', async () => {
        expect(removePersonalInfo()).toBeNull();

        await tickIncludeImages();

        expect(removePersonalInfo().checked).toBe(true);
        expect(removePersonalInfo().disabled).toBe(false);
        expect(text('report-remove-personal-info-label')).toBe('Remove location and owner info');
      });

      it('asks to remove it from the copies when ticked', async () => {
        await tickIncludeImages();

        await openOnGitHub();
        await answerImages({ ...prepared, personal_info_removed: true });

        expect(byTestId('report-personal-info-kept')).toBeNull();
      });

      it('copies the images unchanged when unticked', async () => {
        await tickIncludeImages();
        removePersonalInfo().click();
        await settle();

        await openOnGitHub();
        await answerImages(prepared, false);

        expect(byTestId('report-personal-info-kept')).toBeNull();
      });

      describe('without ExifTool', () => {
        beforeEach(async () => {
          fixture.componentRef.setInput('exiftool', {
            available: false,
            install_hint: 'Install it with: brew install exiftool.',
          });
          await tickIncludeImages();
        });

        it('is disabled and unticked, with the install hint and a note that the info stays', () => {
          expect(removePersonalInfo().checked).toBe(false);
          expect(removePersonalInfo().disabled).toBe(true);
          expect(text('report-exiftool-missing')).toBe(
            'Location and owner info will stay in the files, as removing it needs ExifTool. ' +
              'Install it with: brew install exiftool.',
          );
        });

        it('still copies the images', async () => {
          await openOnGitHub();
          await answerImages(prepared, false);

          expect(all('report-image-file')).toHaveLength(2);
        });
      });

      it('says so when the info could not be removed after all', async () => {
        await tickIncludeImages();

        await openOnGitHub();
        await answerImages(prepared);

        expect(text('report-personal-info-kept')).toBe(
          'Location and owner info could not be removed, so it is still in these files.',
        );
      });
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

    it("asks to close the previous report's images when they could not be replaced", async () => {
      const detail =
        "framewise could not replace the previous report's images. " +
        'Close any of them that are open and try again.';
      await tickIncludeImages();

      await openOnGitHub();
      http
        .expectOne('/api/groups/7/problem-report/images')
        .flush({ detail }, { status: 409, statusText: 'Conflict' });
      await settle();
      await settle();

      expect(text('report-error')).toBe(detail);
    });
  });

  it('closes on Cancel', async () => {
    const closed = vi.fn();
    fixture.componentInstance.close.subscribe(closed);

    await click('report-cancel');

    expect(closed).toHaveBeenCalled();
  });
});
