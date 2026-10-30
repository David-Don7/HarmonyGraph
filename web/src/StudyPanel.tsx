import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useApi } from './api';
import { ErrorBox, formatScore, modelName } from './StudioUI';
import './study.css';

type Readiness = {
  name: string; synthetic: boolean; protocol_ready: boolean; annotation_ready: boolean;
  review_complete: boolean; notice: string; issues: string[];
  queries: {query_id: string; progression: string; pool_size: number; double_reviewed: number;
    adjudicated: number; issues: string[]; split: string; family: string; subtype: string}[];
  research: {comparators: {pending: string[]}};
};

export default function StudyPanel() {
  const client = useQueryClient();
  const benchmarks = useApi<any[]>('/benchmarks');
  const [benchmark, setBenchmark] = useState('');
  const [songs, setSongs] = useState('');
  const [customScope, setCustomScope] = useState(false);
  const [budget, setBudget] = useState(4);
  const [reviewer, setReviewer] = useState(localStorage.getItem('annotator') || '');
  const [packetFile, setPacketFile] = useState<File | null>(null);
  const annotators = useApi<any[]>('/annotators');
  const report = useApi<Readiness>(benchmark ? `/benchmarks/${benchmark}/readiness` : null);
  const queries = useApi<any[]>(benchmark ? `/benchmarks/${benchmark}/queries` : null);
  const jobs = useApi<any[]>('/jobs', 5000);
  const sourceIds = [...new Set((queries.data || []).map(q => q.source_song_id).filter(Boolean))];
  const songIds = customScope ? [...new Set(songs.split(/[\s,]+/).filter(Boolean))] : sourceIds;
  const task = useMutation({
    mutationFn: () => api('/jobs', {kind: 'research_v2_compare', parameters: {
      benchmark_id: benchmark, song_ids: songIds, path_budget: budget,
    }}),
    onSuccess: () => client.invalidateQueries({queryKey: ['/jobs']}),
  });
  const upload = useMutation({mutationFn: async () => {
    if (!packetFile || packetFile.size > 5_000_000) throw new Error('Choose a review packet smaller than 5 MB.');
    const packet = JSON.parse(await packetFile.text());
    return api(`/benchmarks/${benchmark}/review-responses`, {annotator_id: reviewer,
      material_hash: packet.material_hash, responses: packet.responses, minutes: packet.reviewer?.minutes ?? null});
  }, onSuccess: () => client.invalidateQueries({queryKey: [`/benchmarks/${benchmark}/readiness`]})});
  const data = report.data;
  const comparisons = jobs.data?.filter(j => j.kind === 'research_v2_compare' && j.parameters.benchmark_id === benchmark) || [];
  const comparison = (job: any) => {
    const missing = Object.values(job.result.methods || {}).some((rows: any) => rows.some((r: any) => r.metrics['ndcg@10'] == null));
    return <article className="study-run" key={job.id}>
      <div className="study-run-title"><strong>Comparison {job.id.slice(0,8)}</strong><span className="tag">{job.status}</span>
        {job.status === 'completed' && <a className="button" href={`/api/v1/jobs/${job.id}/export`}>Download v2 comparison JSON</a>}</div>
      {job.status === 'running' && <progress value={job.progress} max={1} aria-label="Research comparison progress"/>}
      {job.error && <p className="error">{job.error}</p>}
      {job.status === 'completed' && <details><summary>Per-query relevance results</summary>
        {missing && <p className="field-help">Relevance metrics require resolved judgments for the returned top ten. Missing values are ungraded, not zero.</p>}
        <div className="study-table"><table><caption>nDCG@10 against recorded relevance judgments</caption>
          <thead><tr><th>Method</th><th>Query</th><th>nDCG@10</th><th>Rated at 10</th></tr></thead>
          <tbody>{Object.entries(job.result.methods || {}).flatMap(([method, rows]: any) => rows.map((row: any) => <tr key={`${method}-${row.query_id}`}>
            <td>{modelName(method)}</td><td>{data?.queries.find(q => q.query_id === row.query_id)?.progression || row.query_id.slice(0,8)}</td>
            <td className="num">{row.metrics['ndcg@10'] == null ? 'Ungraded' : formatScore(row.metrics['ndcg@10'])}</td>
            <td className="num">{row.metrics.judged_at_10 ?? 0}/{row.metrics.returned_at_10 ?? 0}</td>
          </tr>))}</tbody>
        </table></div>
      </details>}
    </article>;
  };
  return <section className="study-workspace" aria-labelledby="study-heading">
    <h2 id="study-heading">Context-path comparison</h2>
    <p>Compare seven models on the same candidate set and a fixed selection of songs.</p>
    <div className="study-controls"><label>Study benchmark<select aria-label="Study benchmark" value={benchmark} onChange={e => {
      setBenchmark(e.target.value); setSongs(''); setCustomScope(false); task.reset(); upload.reset(); setPacketFile(null);
    }}><option value="">Choose a benchmark</option>{benchmarks.data?.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
      {benchmark && data?.annotation_ready && <a className="button" href={`/api/v1/benchmarks/${benchmark}/review-packet`}>Download blinded packet</a>}
    </div>
    <ErrorBox error={task.error || upload.error || report.error || benchmarks.error || jobs.error}/>
    {!benchmark ? <p className="field-help">Choose a benchmark, or create one in Benchmark lab.</p>
      : report.isLoading ? <p role="status">Checking study protocol…</p> : data && <>
        <dl className="study-readiness">
          <div><dt>Protocol</dt><dd>{data.protocol_ready ? 'Ready for comparison' : 'Needs preparation'}</dd></div>
          <div><dt>Candidate pools</dt><dd>{data.annotation_ready ? 'Ready for review' : 'Build in Benchmark lab'}</dd></div>
          <div><dt>Recorded reviews</dt><dd>{data.review_complete ? 'Complete and adjudicated' : 'Incomplete'}</dd></div>
        </dl>
        {data.synthetic && <p className="notice">Synthetic benchmark — software checks only.</p>}
        {data.issues.length > 0 && <ul>{data.issues.map(issue => <li key={issue}>{issue}</li>)}</ul>}
        {data.queries.some(q => q.issues.length) && <ul>{data.queries.flatMap(q => q.issues.map(issue => <li key={`${q.query_id}:${issue}`}>{q.progression}: {issue}</li>))}</ul>}
        <details><summary>Query and annotation coverage ({data.queries.length} queries)</summary>
          <div className="study-table"><table><thead><tr><th>Query / family</th><th>Phase</th><th>Candidates</th><th>Two reviewers</th><th>Adjudicated</th></tr></thead>
            <tbody>{data.queries.map(q => <tr key={q.query_id}><td><strong>{q.progression}</strong><small>{q.family || 'Family missing'} · {q.subtype || 'Subtype missing'}</small></td>
              <td>{q.split || '—'}</td><td className="num">{q.pool_size}</td><td className="num">{q.double_reviewed}</td><td className="num">{q.adjudicated}</td></tr>)}</tbody>
          </table></div>
        </details>
        <form onSubmit={e => {e.preventDefault(); task.mutate();}}>
          <div className="study-controls"><label>Comparison path budget<select value={budget} onChange={e => setBudget(Number(e.target.value))}>
            {[1,4,16,64].map(n => <option key={n}>{n}</option>)}</select></label>
            <p className="scope-summary">{songIds.length} {customScope ? 'selected' : 'benchmark source'} song{songIds.length === 1 ? '' : 's'}</p>
          </div>
          <details><summary>Change comparison scope</summary>
            <label className="check"><input type="checkbox" checked={customScope} onChange={e => {setCustomScope(e.target.checked); if (!songs) setSongs(sourceIds.join('\n'));}}/>Use a custom song set</label>
            {customScope && <div className="study-controls"><label>Development song IDs (1–50)<textarea required aria-label="Development song IDs" rows={2} value={songs} onChange={e => setSongs(e.target.value)}/></label>
              <button type="button" onClick={() => {setCustomScope(false); setSongs('');}}>Use source songs</button></div>}
          </details>
          {(!songIds.length || songIds.length > 50) && <p className="field-help">Choose 1–50 development songs under comparison scope.</p>}
          <button className="primary" disabled={!data.protocol_ready || !songIds.length || songIds.length > 50 || task.isPending}>
            {task.isPending ? 'Queuing…' : 'Queue context-path comparison'}</button>
        </form>
        {comparisons.length > 0 && <div className="comparison-history"><h3>Comparisons</h3>{comparisons.slice(0,3).map(comparison)}
          {comparisons.length > 3 && <details><summary>Earlier comparisons ({comparisons.length - 3})</summary>{comparisons.slice(3).map(comparison)}</details>}</div>}
        <details><summary>Import reviewer responses</summary>
          <p className="field-help">Use the completed blinded packet and its reviewer’s profile. Existing submissions stay in history.</p>
          <form onSubmit={e => {e.preventDefault(); upload.mutate();}}><div className="study-controls">
            <label>Packet reviewer<select required value={reviewer} onChange={e => setReviewer(e.target.value)}><option value="">Choose a profile</option>{annotators.data?.map(a => <option value={a.id} key={a.id}>{a.name}</option>)}</select></label>
            <label>Completed review packet<input aria-label="Completed review packet" required type="file" accept=".json,application/json" onChange={e => setPacketFile(e.target.files?.[0] || null)}/></label>
            <button disabled={!reviewer || !packetFile || upload.isPending}>Import responses</button>
          </div></form>{upload.isSuccess && <p role="status">{upload.data.imported} responses saved.</p>}
        </details>
        <details><summary>Study limitations</summary><p className="field-help">These are development comparisons. Held-out testing, qualified independent review and strong prior-work comparisons remain research requirements. Profile qualifications are self-reported.</p>
          <ul>{data.research.comparators.pending.map(c => <li key={c}>{c}</li>)}</ul>
        </details>
      </>}
  </section>;
}
