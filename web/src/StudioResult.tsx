import { useState } from 'react';
import type { components } from './generated/api';
import { formatScore, modelName, precisePercent, sectionName } from './StudioUI';

type SearchResult = components['schemas']['SearchResult'];

function PathEvidence({evidence}: {evidence: any}) {
  const value = evidence.paths;
  const deterministic = value.semantics === 'hard_path';
  const [pathsOpen, setPathsOpen] = useState(false);
  const [allPaths, setAllPaths] = useState(false);
  return <section className="path-evidence">
    <h3>{deterministic ? 'Selected interpretation' : 'Alternative interpretations'}</h3>
    {deterministic ? <p>One selected key/function path. Its weight is fixed to 1 for this control.</p> : <>
      <dl className="evidence-summary">
        <div><dt>Retained model mass</dt><dd>{precisePercent(value.retained_mass)}</dd></div>
        <div><dt>Omitted model mass</dt><dd>{precisePercent(value.omitted_mass)}</dd></div>
        <div><dt>Model score bounds</dt><dd>{(value.ranking_bounds || value.expected_similarity_bounds).map(formatScore).join(' – ')}</dd></div>
      </dl>
      <p className="muted">Bounds cover omitted interpretations of this passage, not missing corpus passages or human relevance.</p>
    </>}
    <details onToggle={e => setPathsOpen(e.currentTarget.open)}><summary>{value.paths.length} {deterministic ? 'path and its alignment' : 'retained paths and their alignments'}</summary>
      {pathsOpen && <>{(allPaths ? value.paths : value.paths.slice(0, 12)).map((path: any, index: number) => <div className="interpretation" key={index}>
        <strong>{path.functions.join(' → ')}</strong><p>{path.key_names.join(' → ')}</p>
        <dl className="path-values">
          {!deterministic && <div><dt>Original probability</dt><dd>{precisePercent(path.probability)}</dd></div>}
          <div><dt>Alignment similarity</dt><dd>{formatScore(path.similarity)}</dd></div>
          <div><dt>Score contribution</dt><dd>{formatScore(path.contribution)}</dd></div>
        </dl>
        <p className="alignment-steps">{path.alignment.map((op: any, i: number) => <span key={i}>{op.operation} · cost {op.cost.toFixed(2)}</span>)}</p>
      </div>)}{!allPaths && value.paths.length > 12 && <button onClick={() => setAllPaths(true)}>Show all {value.paths.length} interpretations</button>}</>}
    </details>
  </section>;
}

export default function ResultCard({result: r, rank, onSong}: {
  result: SearchResult; rank?: number; onSong: (id: string, analysisId?: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [technicalOpen, setTechnicalOpen] = useState(false);
  const paths = r.evidence.paths as any;
  const hypotheses = r.key_hypotheses as any[];
  const components = Object.entries(r.components).filter(([, value]: any) => value.weight > 0) as
    [string, {value: number; weight: number; contribution: number}][];
  const deterministic = paths?.semantics === 'hard_path';
  return <article className="result">
    <div className="result-top">
      {rank && <span className="rank" aria-label={`Rank ${rank}`}>{rank}</span>}
      <div className="result-title"><button onClick={() => onSong(r.song_id, r.analysis_id)}>{r.title}</button>
        <p>{r.artist || 'Artist unavailable'} · {sectionName(r.section)} · Chord events {r.start + 1}–{r.end + 1}</p>
      </div>
      <div className="score"><span>Model score</span><strong>{formatScore(r.score)}</strong></div>
    </div>
    <div className="result-middle"><div className="chord-reading">
      <p className="chords">{r.labels.join(' → ')}</p>
      {r.interpretation.length > 0 && <p className="muted">{paths && !deterministic ? 'Leading interpretation' : 'Selected interpretation'}: {r.interpretation.join(' → ')}</p>}
    </div>{!!r.evidence.synthetic && <span className="tag">Synthetic fixture</span>}</div>
    <div className="result-bottom"><button onClick={() => setOpen(!open)} aria-expanded={open}>
      {open ? 'Hide evidence' : 'Why this matches'}</button></div>
    {open && <div className="evidence">
      {paths ? <PathEvidence evidence={r.evidence}/> : <>
        <h3>Averaged-key context</h3>
        {hypotheses.length > 0 && <div className="hypothesis-list">{hypotheses.map(h => <div key={h.key}>
          <span>{h.key}</span><span>{precisePercent(h.probability)}</span></div>)}</div>}
        <p>Retained averaged-key mass: {precisePercent(r.retained_mass)}. Model probabilities are not calibrated relevance estimates.</p>
      </>}
      <details><summary>Score contributions</summary><div className="table-scroll"><table>
        <thead><tr><th>Evidence</th><th>Value</th><th>Weight</th><th>Contribution</th></tr></thead>
        <tbody>{components.map(([name, c]) => <tr key={name}>
          <td>{name === 'path_expectation' ? (deterministic ? 'Selected-path alignment' : 'Expected alignment') : sectionName(name)}</td>
          <td>{formatScore(c.value)}</td><td>{c.weight.toFixed(4)}</td><td>{formatScore(c.contribution)}</td>
        </tr>)}</tbody>
      </table></div></details>
      {!!r.evidence.context_labels && <details><summary>Full chord context</summary><p className="context-events">{(r.evidence.context_labels as string[]).map((chord, i) =>
        <span className={i >= r.start && i <= r.end ? 'selected-event' : ''} key={i}>{i + 1}: {chord}</span>)}</p></details>}
      <details onToggle={e => setTechnicalOpen(e.currentTarget.open)}><summary>Technical details and provenance</summary>
        {paths && <p>{modelName(paths.semantics)} · {paths.probability_note}</p>}
        {technicalOpen && <pre>{JSON.stringify({analysis_id: r.analysis_id, passage_id: r.passage_id, evidence: r.evidence}, null, 2)}</pre>}
      </details>
    </div>}
  </article>;
}
