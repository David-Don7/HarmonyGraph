import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useApi } from './api';
import './study.css';

type Readiness = {
  name: string; synthetic: boolean; protocol_ready: boolean; annotation_ready: boolean;
  review_complete: boolean; notice: string; issues: string[];
  queries: { query_id: string; progression: string; pool_size: number; double_reviewed: number;
    adjudicated: number; issues: string[]; split: string; family: string; subtype: string }[];
  research: { comparators: { pending: string[] } };
};

export default function StudyPanel() {
  const client = useQueryClient();
  const benchmarks = useApi<any[]>('/benchmarks');
  const [benchmark, setBenchmark] = useState('');
  const [songs, setSongs] = useState('');
  const [budget, setBudget] = useState(4);
  const [reviewer, setReviewer] = useState(localStorage.getItem('annotator') || '');
  const [packetFile, setPacketFile] = useState<File | null>(null);
  const annotators = useApi<any[]>('/annotators');
  const bid = benchmark || benchmarks.data?.[0]?.id;
  const report = useApi<Readiness>(bid ? `/benchmarks/${bid}/readiness` : '/research-v2/status');
  const queries = useApi<any[]>(bid ? `/benchmarks/${bid}/queries` : '/benchmarks');
  const jobs = useApi<any[]>('/jobs', 5000);
  const task = useMutation({
    mutationFn: () => api('/jobs', {kind: 'research_v2_compare', parameters: {
      benchmark_id: bid, song_ids: [...new Set(songs.split(/[\s,]+/).filter(Boolean))], path_budget: budget,
    }}),
    onSuccess: () => client.invalidateQueries({queryKey: ['/jobs']}),
  });
  const upload = useMutation({mutationFn: async () => {
    if (!packetFile || packetFile.size > 5_000_000) throw new Error('Choose a review packet smaller than 5 MB.');
    const packet = JSON.parse(await packetFile.text());
    return api(`/benchmarks/${bid}/review-responses`, {annotator_id: reviewer,
      material_hash: packet.material_hash, responses: packet.responses, minutes: packet.reviewer?.minutes ?? null});
  }, onSuccess: () => client.invalidateQueries({queryKey: [`/benchmarks/${bid}/readiness`]})});
  const data = bid ? report.data : undefined;
  const comparisons = jobs.data?.filter(j => j.kind === 'research_v2_compare' && j.parameters.benchmark_id === bid) || [];
  const error = task.error || upload.error || report.error || benchmarks.error || jobs.error;
  return <section className="study-workspace" aria-labelledby="study-heading">
    <div className="study-title"><h2 id="study-heading">Research pilot</h2>
      <span>Context paths · development comparison</span></div>
    <p>Prepare independent chord-only review, then compare seven methods on the same candidates. Held-out testing and strong prior-work comparisons remain pending.</p>
    <div className="study-controls">
      <label>Study benchmark<select aria-label="Study benchmark" value={bid || ''} onChange={e => {
        setBenchmark(e.target.value); setSongs(''); task.reset(); upload.reset(); setPacketFile(null);
      }}><option value="" disabled>Choose a benchmark</option>{benchmarks.data?.map(b =>
        <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
      {bid && <a className="button" href={`/api/v1/benchmarks/${bid}/review-packet`}>Download blinded packet</a>}
    </div>
    {error && <p className="error" role="alert">{error instanceof Error ? error.message : String(error)}</p>}
    {!bid ? <p>Create a benchmark in Benchmark lab. Add a source song, query family, subtype and development phase to each query.</p>
      : report.isLoading ? <p role="status">Checking study protocol…</p> : data && <>
        <dl className="study-readiness">
          <div><dt>Protocol</dt><dd>{data.protocol_ready ? 'Ready for comparison' : 'Needs preparation'}</dd></div>
          <div><dt>Candidate pools</dt><dd>{data.annotation_ready ? 'Ready for review' : 'Build in Benchmark lab'}</dd></div>
          <div><dt>Independent review</dt><dd>{data.review_complete ? 'Recorded and adjudicated' : 'Pending'}</dd></div>
        </dl>
        {data.synthetic && <p className="notice">This benchmark contains constructed examples. Its results are software checks, not independent real-data findings.</p>}
        {data.issues.length > 0 && <ul>{data.issues.map(issue => <li key={issue}>{issue}</li>)}</ul>}
        {data.queries.length > 0 && <div className="study-table"><table><caption>Protocol and annotation coverage</caption>
          <thead><tr><th>Query / family</th><th>Phase</th><th>Candidates</th><th>Two reviewers</th><th>Adjudicated</th></tr></thead>
          <tbody>{data.queries.map(q => <tr key={q.query_id}><td><strong>{q.progression}</strong><small>{q.family || 'Family missing'} · {q.subtype || 'Subtype missing'}</small>{q.issues.map(issue => <small className="study-issue" key={issue}>{issue}</small>)}</td>
            <td>{q.split || '—'}</td><td className="num">{q.pool_size}</td><td className="num">{q.double_reviewed}</td><td className="num">{q.adjudicated}</td></tr>)}</tbody></table></div>}
        <form onSubmit={e => {e.preventDefault(); task.mutate();}}>
          <div className="study-controls"><label>Development song IDs (1–50)
            <textarea aria-label="Development song IDs" required rows={2} value={songs} onChange={e => setSongs(e.target.value)} placeholder="Paste IDs separated by spaces or commas"/>
          </label><button type="button" onClick={() => setSongs([...new Set((queries.data || []).map(q => q.source_song_id).filter(Boolean))].join('\n'))}>Use source songs</button>
            <label>Comparison path budget<select value={budget} onChange={e => setBudget(Number(e.target.value))}>{[1,4,16,64].map(n => <option key={n}>{n}</option>)}</select></label>
          </div>
          <p>The corpus is explicitly bounded. Analysis and benchmark identities are pinned when queued. Missing judgments produce unavailable metrics.</p>
          <button className="primary" disabled={!data.protocol_ready || !songs.trim() || task.isPending}>Queue context-path comparison</button>
        </form>
        {task.isSuccess && <p role="status">Comparison queued. Progress and report appear below.</p>}
        {comparisons.map(job => <div className="study-run" key={job.id}>
          <div><strong>Comparison {job.id.slice(0,8)}</strong><span>{job.status} · {Math.round(job.progress * 100)}%</span></div>
          <progress value={job.progress} max={1} aria-label="Research comparison progress"/>
          {job.error && <p className="error">{job.error}</p>}
          {job.status === 'completed' && <><a className="button" href={`/api/v1/jobs/${job.id}/export`}>Download v2 comparison JSON</a>
            <p>{Object.keys(job.result.methods || {}).length} methods · manifest {job.result.manifest_hash?.slice(0,16)}</p>
            <div className="study-table"><table><caption>Per-query nDCG@10</caption><thead><tr><th>Method</th><th>Query</th><th>nDCG@10</th><th>Judged at 10</th></tr></thead>
              <tbody>{Object.entries(job.result.methods || {}).flatMap(([method, rows]: any) => rows.map((row: any) => <tr key={`${method}-${row.query_id}`}><td>{method.replaceAll('_',' ')}</td><td>{row.query_id.slice(0,8)}</td><td className="num">{row.metrics['ndcg@10'] == null ? 'Unavailable' : row.metrics['ndcg@10'].toFixed(3)}</td><td className="num">{row.metrics.judged_at_10 ?? 0}/{row.metrics.returned_at_10 ?? 0}</td></tr>))}</tbody></table></div>
          </>}
        </div>)}
        <details><summary>Remaining scientific evidence</summary><p>{data.notice}</p><ul>{data.research.comparators.pending.map(c => <li key={c}>{c}</li>)}</ul></details>
        <details><summary>Import independent reviewer responses</summary>
          <p>Complete the downloaded packet’s responses and reviewer minutes. Choose the reviewer’s profile; earlier submissions remain in the history. Create profiles and record qualifications in Benchmark lab.</p>
          <form onSubmit={e => {e.preventDefault(); upload.mutate();}}><div className="study-controls">
            <label>Packet reviewer<select required value={reviewer} onChange={e => setReviewer(e.target.value)}><option value="">Choose a profile</option>{annotators.data?.map(a => <option value={a.id} key={a.id}>{a.name}</option>)}</select></label>
            <label>Completed review packet<input aria-label="Completed review packet" required type="file" accept=".json,application/json" onChange={e => setPacketFile(e.target.files?.[0] || null)}/></label>
            <button disabled={!reviewer || !packetFile || upload.isPending}>Import responses</button>
          </div></form>{upload.isSuccess && <p role="status">{upload.data.imported} independent responses saved.</p>}
        </details>
      </>}
  </section>;
}
