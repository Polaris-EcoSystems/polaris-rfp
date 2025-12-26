export const SESSION_COOKIE_NAME =
  process.env.NODE_ENV === 'production'
    ? '__Host-polaris_session'
    : 'polaris_session'

export const SESSION_ID_COOKIE_NAME =
  process.env.NODE_ENV === 'production' ? '__Host-polaris_sid' : 'polaris_sid'

export function sessionCookieName(): string {
  return SESSION_COOKIE_NAME
}

export function sessionIdCookieName(): string {
  return SESSION_ID_COOKIE_NAME
}

