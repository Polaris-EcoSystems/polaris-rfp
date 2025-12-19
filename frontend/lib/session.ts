export const SESSION_COOKIE_NAME =
  process.env.NODE_ENV === 'production'
    ? '__Host-polaris_session'
    : 'polaris_session'

export function sessionCookieName(): string {
  return SESSION_COOKIE_NAME
}


