import type { ScoreName } from '../api/types'

const ORDER: ScoreName[] = ['hook', 'insight', 'accuracy', 'clarity', 'tone']
const LABEL: Record<ScoreName, string> = {
  hook: 'Hook',
  insight: 'Insight',
  accuracy: 'Accuracy',
  clarity: 'Clarity',
  tone: 'Tone',
}

/** Compact bars (draft panel). */
export function ScoreBars({ scores }: { scores: Record<ScoreName, number> }) {
  return (
    <dl className="grid grid-cols-[72px_minmax(0,1fr)_24px] items-center gap-x-2.5 gap-y-2 text-[13px]">
      {ORDER.map((name) => (
        <div key={name} className="contents">
          <dt>{LABEL[name]}</dt>
          <dd className="m-0 h-1.5 rounded-full bg-line" aria-hidden="true">
            <span
              className={`block h-1.5 rounded-full ${scores[name] < 7 ? 'bg-review' : 'bg-accent'}`}
              style={{ width: `${scores[name] * 10}%` }}
            />
          </dd>
          <dd className="m-0 text-right font-mono" aria-label={`${LABEL[name]} ${scores[name]} out of 10`}>
            {scores[name]}
          </dd>
        </div>
      ))}
    </dl>
  )
}

/** Big number tiles (review screen). */
export function ScoreTiles({ scores }: { scores: Record<ScoreName, number> }) {
  return (
    <dl className="grid grid-cols-5 gap-2">
      {ORDER.map((name) => (
        <div
          key={name}
          className={`flex flex-col-reverse items-center gap-0.5 rounded-[10px] py-2.5 ${
            scores[name] < 7 ? 'bg-review-soft' : 'bg-paper'
          }`}
        >
          <dt className="text-[11px] text-ink-2">{LABEL[name]}</dt>
          <dd className="m-0 font-display text-3xl leading-none">{scores[name]}</dd>
        </div>
      ))}
    </dl>
  )
}

export function VerdictPill({ verdict, bar }: { verdict: 'pass' | 'revise'; bar?: number }) {
  const pass = verdict === 'pass'
  return (
    <span
      className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
        pass ? 'bg-success-soft text-success' : 'bg-review-soft text-review'
      }`}
    >
      {pass ? 'Pass' : 'Revise'}
      {bar !== undefined && ` · bar ${bar}`}
    </span>
  )
}
