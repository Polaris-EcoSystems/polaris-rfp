import { redirect } from 'next/navigation'

export default function CanvaIntegrationPage() {
  // This page used to contain Canva mapping + test tools.
  // We’ve moved the Canva-template workflow to /templates.
  redirect('/templates')
}


