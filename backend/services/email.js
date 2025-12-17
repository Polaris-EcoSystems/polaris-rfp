const { SESv2Client, SendEmailCommand } = require('@aws-sdk/client-sesv2')

function getRegion() {
  return (
    process.env.SES_REGION ||
    process.env.AWS_REGION ||
    process.env.AWS_DEFAULT_REGION ||
    'us-east-1'
  )
}

function getFromAddress() {
  return String(process.env.SES_FROM || 'support@righteousgambit.com').trim()
}

function buildResetEmail({ to, resetUrl }) {
  const safeTo = String(to || '').trim()
  const safeUrl = String(resetUrl || '').trim()
  const subject = 'Reset your password'

  const text = `A password reset was requested for this email address.

Reset your password using this link (valid for a limited time):
${safeUrl}

If you did not request this, you can ignore this email.`

  const html = `<!doctype html>
<html>
  <body style="font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Arial, sans-serif; line-height: 1.5; color: #111827;">
    <h2 style="margin: 0 0 12px 0;">Reset your password</h2>
    <p style="margin: 0 0 12px 0;">A password reset was requested for <strong>${safeTo}</strong>.</p>
    <p style="margin: 0 0 16px 0;">
      <a href="${safeUrl}" style="display: inline-block; background: #1d4ed8; color: white; padding: 10px 14px; border-radius: 8px; text-decoration: none;">
        Reset password
      </a>
    </p>
    <p style="margin: 0 0 12px 0; font-size: 14px; color: #374151;">
      If the button doesn’t work, copy/paste this URL:
      <br />
      <a href="${safeUrl}">${safeUrl}</a>
    </p>
    <p style="margin: 16px 0 0 0; font-size: 14px; color: #6b7280;">
      If you did not request this, you can safely ignore this email.
    </p>
  </body>
</html>`

  return { subject, text, html }
}

async function sendPasswordResetEmail({ to, resetUrl }) {
  const region = getRegion()
  const fromEmail = getFromAddress()

  const { subject, text, html } = buildResetEmail({ to, resetUrl })

  const client = new SESv2Client({ region })
  const cmd = new SendEmailCommand({
    FromEmailAddress: fromEmail,
    Destination: { ToAddresses: [String(to).trim()] },
    Content: {
      Simple: {
        Subject: { Data: subject, Charset: 'UTF-8' },
        Body: {
          Text: { Data: text, Charset: 'UTF-8' },
          Html: { Data: html, Charset: 'UTF-8' },
        },
      },
    },
  })

  return await client.send(cmd)
}

module.exports = { sendPasswordResetEmail, getFromAddress }
