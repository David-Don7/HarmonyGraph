import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { api } from './api';
import type { components } from './generated/api';
import ResultCard from './StudioResult';
import { ErrorBox, Field, modelName, PageTitle } from './StudioUI';

type SearchRequest = components['schemas']['SearchRequest'];
type SearchResponse = components['schemas']['SearchResponse'];
const FEATURES = ['secondary','secondary_dominant_chain','borrowed','dominant_resolution','plagal_motion','modulation','half_cadence'];

export default function StudioSearch({overview, onSong}: {overview: any; onSong: (id: string) => void}) {
  const [progression, setProgression] = useState('V7 I');
  const [mode, setMode] = useState<SearchRequest['mode']>('functional');
  const [section, setSection] = useState('chorus');
  const [boundary, setBoundary] = useState('end');
  const [genre, setGenre] = useState('');
  const [advanced, setAdvanced] = useState(false);
  const [tolerance, setTolerance] = useState(.45);
  const [cross, setCross] = useState(false);
  const [every, setEvery] = useState(false);
  const [key, setKey] = useState('');
  const [yearFrom, setYearFrom] = useState('');
  const [yearTo, setYearTo] = useState('');
  const [ranking, setRanking] = useState<SearchRequest['ranking']>('path_expectation');
  const [pathBudget, setPathBudget] = useState(4);
  const [required, setRequired] = useState('');
  const [optional, setOptional] = useState('');
  const [distance, setDistance] = useState(0);
  const [preferredBoundary, setPreferredBoundary] = useState('');
  const [preferred, setPreferred] = useState('');
  const functional = mode === 'functional' || mode === 'fuzzy';
  const effectiveRanking = functional ? ranking : 'legacy_mixture';
  const additionalCount = [key, yearFrom, yearTo, required, optional, preferredBoundary, preferred, cross, every, boundary && distance > 0].filter(Boolean).length;
  const mutation = useMutation({mutationFn: (body: SearchRequest) => api<SearchResponse>('/search', body)});
  const modes = [
    {id: 'literal', title: 'Literal', hint: 'Exact chord identities'},
    {id: 'transposed', title: 'Transposed', hint: 'Same pattern at another pitch'},
    {id: 'functional', title: 'Functional', hint: 'Fixed-length function alignment'},
    {id: 'fuzzy', title: 'Fuzzy functional', hint: 'Approximate function alignment'},
  ] as const;
  function submit() {
    mutation.mutate({progression, mode, ranking: effectiveRanking, path_budget: pathBudget,
      pattern: 'progression', section: section || null, boundary: (boundary || null) as SearchRequest['boundary'],
      genre: genre || null, key: key || null, year_from: yearFrom ? Number(yearFrom) : null,
      year_to: yearTo ? Number(yearTo) : null, cross_sections: cross, every_chorus: every,
      required_features: required ? [required] : [], optional_features: optional ? [optional] : [],
      boundary_distance: boundary ? distance : 0, preferred_boundary: (preferredBoundary || null) as SearchRequest['preferred_boundary'],
      preferred_section: preferred || null, tolerance: mode === 'fuzzy' && effectiveRanking === 'legacy_mixture' ? tolerance : .45,
      limit: 20, function_budget: 16, match_threshold: .8, dataset_ids: [], song_ids: []});
  }
  return <>
    <PageTitle title="Harmonic search" text="Find chord passages and inspect their musical interpretations."/>
    <form className="search-panel panel" onSubmit={e => {e.preventDefault(); submit();}}>
      <div className="mode-grid" role="group" aria-label="Search mode">{modes.map(m =>
        <button type="button" key={m.id} title={m.hint} aria-pressed={mode === m.id} className={mode === m.id ? 'mode selected' : 'mode'}
          onClick={() => {setMode(m.id); if (functional !== (m.id === 'functional' || m.id === 'fuzzy')) setProgression(m.id === 'literal' || m.id === 'transposed' ? 'G7 C' : 'V7 I');}}>
          {m.title}
        </button>)}</div>
      <div className="query-row"><Field label="Progression"><input id="progression" required value={progression}
        onChange={e => setProgression(e.target.value)} placeholder={functional ? 'V7 I' : 'G7 C'} aria-describedby="notation-help"/></Field>
        <button className="primary" disabled={mutation.isPending || !overview?.analysis}>{mutation.isPending ? 'Searching…' : 'Find matches'}</button>
      </div>
      <p id="notation-help" className="field-help">{functional ? `${effectiveRanking === 'legacy_mixture' ? 'Roman numerals' : '2–8 Roman numerals'}, separated by spaces.` : 'Chord symbols, separated by spaces.'}</p>
      {!overview?.analysis && <p role="status">Search becomes available after an analysis is published.</p>}
      {functional && <div className="filter-row model-controls">
        <Field label="Research model"><select value={ranking} onChange={e => setRanking(e.target.value as SearchRequest['ranking'])}>
          <option value="path_expectation">Context paths · research v2</option><option value="legacy_mixture">Averaged keys · legacy baseline</option><option value="hard_path">Deterministic path · control</option>
        </select></Field>
        {ranking === 'path_expectation' && <Field label="Key-path budget"><select value={pathBudget} onChange={e => setPathBudget(Number(e.target.value))} aria-describedby="budget-help">
          {[4,16,64,256].map(n => <option key={n}>{n}</option>)}</select></Field>}
        <p className="field-help" id="budget-help">{ranking === 'path_expectation' ? 'More paths retain more model evidence and take longer to score.' : ranking === 'hard_path' ? 'One selected key/function trajectory; uncertainty is not retained.' : 'Averages key probabilities across the passage, then combines fixed-key readings.'}</p>
      </div>}
      <div className="filter-row">
        <Field label="Section"><select value={section} onChange={e => setSection(e.target.value)}><option value="">Any section</option>
          {['chorus','verse','bridge','intro','outro','solo'].map(s => <option key={s}>{s}</option>)}</select></Field>
        <Field label="Position"><select value={boundary} onChange={e => setBoundary(e.target.value)}><option value="">Anywhere</option>
          <option value="end">Section ending</option><option value="start">Section start</option><option value="interior">Inside section</option><option value="adjacent">Near boundary</option></select></Field>
        <Field label="Genre"><select value={genre} onChange={e => setGenre(e.target.value)}><option value="">All genres</option>
          {overview?.genres?.map((g: string) => <option key={g}>{g}</option>)}</select></Field>
        <button type="button" aria-expanded={advanced} onClick={() => setAdvanced(!advanced)}>{advanced ? 'Hide filters' : `More filters${additionalCount ? ` (${additionalCount} active)` : ''}`}</button>
      </div>
      {advanced && <div className="advanced">
        <div><h3>Additional requirements</h3><div className="filter-row">
          <Field label="Local key"><input value={key} onChange={e => setKey(e.target.value)} placeholder="e.g. C major"/></Field>
          <Field label="From year"><input type="number" value={yearFrom} onChange={e => setYearFrom(e.target.value)}/></Field>
          <Field label="To year"><input type="number" value={yearTo} onChange={e => setYearTo(e.target.value)}/></Field>
          <Field label="Required relation"><select value={required} onChange={e => setRequired(e.target.value)}><option value="">None</option>
            {FEATURES.map(x => <option key={x} value={x}>{x.replaceAll('_',' ')}</option>)}</select></Field>
          {boundary && <Field label="Boundary distance (chord events)"><input type="number" min="0" max="16" value={distance} onChange={e => setDistance(Number(e.target.value))}/></Field>}
        </div><div className="actions"><label className="check"><input type="checkbox" checked={cross} onChange={e => setCross(e.target.checked)}/>Allow crossing sections</label>
          <label className="check"><input type="checkbox" checked={every} onChange={e => setEvery(e.target.checked)}/>Require a match in every chorus</label></div></div>
        <div><h3>Ranking preferences</h3><div className="filter-row">
          <Field label="Preferred position"><select value={preferredBoundary} onChange={e => setPreferredBoundary(e.target.value)}><option value="">None</option><option value="start">Section start</option><option value="end">Section ending</option></select></Field>
          <Field label="Preferred section"><select value={preferred} onChange={e => setPreferred(e.target.value)}><option value="">None</option>{['chorus','verse','bridge'].map(s => <option key={s}>{s}</option>)}</select></Field>
          <Field label="Tie-break relation"><select value={optional} onChange={e => setOptional(e.target.value)}><option value="">None</option>{FEATURES.map(x => <option key={x} value={x}>{x.replaceAll('_',' ')}</option>)}</select></Field>
        </div><p className="field-help">Preferences change ordering; they do not exclude passages.</p></div>
        {mode === 'fuzzy' && effectiveRanking === 'legacy_mixture' && <Field label={`Legacy alignment tolerance: ${tolerance.toFixed(2)}`}><input type="range" min="0" max="1" step="0.05" value={tolerance} onChange={e => setTolerance(Number(e.target.value))}/></Field>}
      </div>}
    </form>
    <ErrorBox error={mutation.error}/>
    {mutation.isPending ? <p role="status">Scoring candidate passages…</p> : mutation.data && <>
      <div className="section-heading"><h2>{mutation.data.results.length} passage{mutation.data.results.length === 1 ? '' : 's'} shown</h2>
        <span className="muted">{mutation.variables?.mode === 'literal' ? 'Literal' : mutation.variables?.mode === 'transposed' ? 'Transposed' : modelName(mutation.variables?.ranking || 'legacy_mixture')}</span></div>
      <p className="field-help">Model scores rank the evaluated passages; they are not probabilities of human relevance.</p>
      {mutation.data.candidate_limit_reached && <p className="notice" role="status">Candidate cap reached: {mutation.data.candidate_count} starts evaluated. Other corpus passages may be missing.</p>}
      <details className="search-diagnostics"><summary>Search details</summary><dl className="evidence-summary">
        <div><dt>Query</dt><dd>{mutation.variables?.progression}</dd></div>
        <div><dt>Candidate starts evaluated</dt><dd>{mutation.data.candidate_count.toLocaleString()}</dd></div>
        <div><dt>Processing time</dt><dd>{(mutation.data.timings.total_ms / 1000).toFixed(2)} s</dd></div>
        <div><dt>Analysis</dt><dd><code>{mutation.data.analysis_id}</code></dd></div>
      </dl></details>
      {mutation.data.results.length ? mutation.data.results.map((r, index) => <ResultCard key={r.passage_id} result={r} rank={index + 1} onSong={onSong}/>)
        : <p className="empty">No passages found in the evaluated candidates. Try fewer requirements.</p>}
    </>}
  </>;
}
