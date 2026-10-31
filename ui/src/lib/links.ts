// only app-relative or http(s) URLs become links: no javascript:, and no //host or /\host (browsers read both as
// protocol-relative, i.e. another origin)
export const linkable = (url: string): boolean => /^(\/(?![/\\])|https?:\/\/)/i.test(url);
