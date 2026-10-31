import { get, type Params } from './api';

/** Rows per server page (BootUI's `SERVER_PAGE_SIZE`); the server caps any page at 1000. */
export const PAGE_SIZE = 200;

/** Contract `PageMetadata`. */
export interface PageMetadata {
  total: number;
  matched: number;
  offset: number;
  limit: number;
  returned: number;
  hasMore: boolean;
}

/**
 * A server-paged list (config, loggers, beans, mappings), immutable: `load` and `more` return new values,
 * so a view just assigns the result and drops it if its filter changed meanwhile.
 */
export class ServerPage<T> {
  private constructor(
    private readonly path: string,
    private readonly key: string,
    private readonly params: Params,
    readonly items: readonly T[],
    readonly page: PageMetadata,
    /** The whole last response, for fields beside the rows (e.g. config's `propertySuggestions`). */
    readonly data: Readonly<Record<string, unknown>> = {},
  ) {}

  static async load<T>(path: string, key: string, params: Params = {}): Promise<ServerPage<T>> {
    return new ServerPage<T>(path, key, params, [], emptyPage).fetch();
  }

  /** Every row up to `maxRows`; stops early on an empty page, so a server stuck on `hasMore` cannot loop forever. */
  static async loadAll<T>(path: string, key: string, maxRows: number, params: Params = {}): Promise<readonly T[]> {
    let page = await ServerPage.load<T>(path, key, params);
    while (page.hasMore && page.items.length < maxRows) {
      const next = await page.more();
      if (next.items.length === page.items.length) break;
      page = next;
    }
    return page.items.slice(0, maxRows);
  }

  /** The same query from offset 0 again, with at least as many rows as are loaded now (Load more is kept). */
  async refresh(): Promise<ServerPage<T>> {
    let next = await ServerPage.load<T>(this.path, this.key, this.params);
    while (next.hasMore && next.items.length < this.items.length) {
      const longer = await next.more();
      if (longer.items.length === next.items.length) break;
      next = longer;
    }
    return next;
  }

  private pending: Promise<ServerPage<T>> | null = null;

  /** The next page appended; `this` when there is nothing more. Concurrent calls share one request. */
  more(): Promise<ServerPage<T>> {
    if (!this.page.hasMore) return Promise.resolve(this);
    this.pending ??= this.fetch().finally(() => (this.pending = null));
    return this.pending;
  }

  get hasMore(): boolean {
    return this.page.hasMore;
  }
  get matched(): number {
    return this.page.matched;
  }
  get total(): number {
    return this.page.total;
  }

  private async fetch(): Promise<ServerPage<T>> {
    const data = await get<Record<string, unknown>>(this.path, { ...this.params, offset: this.items.length, limit: PAGE_SIZE });
    const rows = (data[this.key] ?? []) as T[];
    return new ServerPage(this.path, this.key, this.params, [...this.items, ...rows], data.page as PageMetadata, data);
  }
}

const emptyPage: PageMetadata = { total: 0, matched: 0, offset: 0, limit: PAGE_SIZE, returned: 0, hasMore: true };
