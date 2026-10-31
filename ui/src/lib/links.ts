// only app-relative or http(s) URLs become links: no javascript:, and no //host or /\host (browsers read both as
// protocol-relative, i.e. another origin). Browsers drop tab, CR and LF while parsing, so the check does too.
export const linkable = (url: string): boolean => /^(\/(?![/\\])|https?:\/\/)/i.test(url.replace(/[\t\r\n]/g, ''));
