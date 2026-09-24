// Temporary pages until Phase 11 builds History and Health & settings.
export function PlaceholderPage({ title }: { title: string }) {
  return (
    <main className="flex grow flex-col gap-2 p-10">
      <h1 className="font-display text-[40px] leading-none">{title}</h1>
      <p className="text-ink-2">This screen is built in Phase 11.</p>
    </main>
  )
}
