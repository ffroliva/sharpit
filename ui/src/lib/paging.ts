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
  ) {}

  static async load<T>(path: string, key: string, params: Params = {}): Promise<ServerPage<T>> {
    return new ServerPage<T>(path, key, params, [], emptyPage).fetch();
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
    return new ServerPage(this.path, this.key, this.params, [...this.items, ...rows], data.page as PageMetadata);
  }
}

const emptyPage: PageMetadata = { total: 0, matched: 0, offset: 0, limit: PAGE_SIZE, returned: 0, hasMore: true };
