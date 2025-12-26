export const LOCALE_COOKIE = 'polaris_locale'

export const SUPPORTED_LOCALES = ['en', 'es'] as const
export type AppLocale = (typeof SUPPORTED_LOCALES)[number]

export const DEFAULT_LOCALE: AppLocale = 'en'

export function isSupportedLocale(
  v: string | null | undefined,
): v is AppLocale {
  if (!v) return false
  return (SUPPORTED_LOCALES as readonly string[]).includes(v)
}

/**
 * Parse an Accept-Language header and choose our best-supported locale.
 * Very small + dependency-free on purpose (middleware runs on Edge).
 */
export function pickLocaleFromAcceptLanguage(
  acceptLanguageHeader: string | null,
): AppLocale {
  const raw = String(acceptLanguageHeader || '').trim()
  if (!raw) return DEFAULT_LOCALE

  // Example: "es-ES,es;q=0.9,en;q=0.8"
  const tags = raw
    .split(',')
    .map((part) => part.trim().split(';')[0]?.trim())
    .filter(Boolean)
    .map((tag) => String(tag).toLowerCase())

  for (const tag of tags) {
    const base = tag.split('-')[0]
    if (isSupportedLocale(base)) return base
  }

  return DEFAULT_LOCALE
}

