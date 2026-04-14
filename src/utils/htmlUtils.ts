import * as cheerio from 'cheerio';

const LANG_CODE_MAP: Record<string, string> = {
  en: 'en-US',
  es: 'es-ES',
  fr: 'fr-FR',
  de: 'de-DE',
  it: 'it-IT',
  pt: 'pt-BR',
  nl: 'nl-NL',
  ja: 'ja-JP',
  ko: 'ko-KR',
  zh: 'cmn-CN',
  ar: 'ar-XA',
  hi: 'hi-IN',
  ru: 'ru-RU',
  pl: 'pl-PL',
  tr: 'tr-TR',
  el: 'el-GR',
};

export const toBcp47 = (lang: string): string =>
  LANG_CODE_MAP[lang.toLowerCase()] ?? `${lang}-${lang.toUpperCase()}`;

export const stripHtml = (htmlOrText: string): string => {
  if (!htmlOrText?.trim()) return '';
  const $ = cheerio.load(htmlOrText);
  return $.text().replace(/\s+/g, ' ').trim();
};
