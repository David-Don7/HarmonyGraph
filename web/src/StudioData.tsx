import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useApi } from './api';
import { ErrorBox, Field, PageTitle } from './StudioUI';

const JOB_NAMES: Record<string, string> = {
  catalog_download: 'Download catalog', catalog_import: 'Import catalog', catalog_metadata: 'Resolve song metadata',
  catalog_analyze: 'Index catalog', research_v2_compare: 'Context-path comparison', demo: 'Load synthetic fixtures',
  import: 'Import dataset', analyze: 'Analyze corpus', evaluate: 'Legacy evaluation', optimize: 'Legacy parameter search', export: 'Export report',
};

export default function StudioData() {
  const client = useQueryClient();
  const datasets = useApi<any[]>('/datasets');
  const jobs = useApi<any[]>('/jobs', 2000);
  const analyses = useApi<any[]>('/analyses', 5000);
  const [path, setPath] = useState('');
  const [source, setSource] = useState('jsonl');
  const [license, setLicense] = useState('unspecified');
  const task = useMutation({mutationFn: (body: any) => api('/jobs', body), onSuccess: () => client.invalidateQueries()});
  const cancel = useMutation({mutationFn: (id: string) => api(`/jobs/${id}/cancel`, {}), onSuccess: () => client.invalidateQueries()});
  const activate = useMutation({mutationFn: (id: string) => api(`/analyses/${id}/activate`, {}), onSuccess: () => client.invalidateQueries()});
  const [historyOpen, setHistoryOpen] = useState(false);
  const activeJobs = (jobs.data || []).filter(j => ['queued','running','failed'].includes(j.status));
  const history = (jobs.data || []).filter(j => ['completed','cancelled'].includes(j.status));
  const renderJob = (j: any) => {
      const recurring = ['catalog_analyze','catalog_metadata'].includes(j.kind);
      const scheduled = j.status === 'queued' && j.result.continue;
      const label = scheduled ? 'Waiting for next batch' : j.status;
      const active = ['queued','running'].includes(j.status);
      const processed = j.result.indexed_this_batch ?? j.result.resolved_this_batch;
      return <article className="panel job" key={j.id}>
        <div className="job-title"><strong>{JOB_NAMES[j.kind] || j.kind}</strong><span className="tag">{label}</span>
          {active && <button onClick={() => cancel.mutate(j.id)} disabled={cancel.isPending} aria-label={`Cancel ${j.kind}`}>Cancel</button>}</div>
        {j.status === 'running' && <div className="job-progress"><progress value={j.progress} max={1} aria-label={`${j.kind} progress`}/>
          <span>{recurring ? 'Current batch: ' : ''}{Math.round(j.progress * 100)}%</span></div>}
        {recurring && <p className="field-help">Repeats while records remain. Batch completion is not full catalog completion.{processed !== undefined && ` Last batch processed ${processed.toLocaleString()} records.`}</p>}
        {j.error && <p className="error" role="alert">{j.error}</p>}
        <details><summary>Job details</summary><p>Created {new Date(j.created_at).toLocaleString()} · Updated {new Date(j.updated_at).toLocaleString()}</p>
          <pre>{JSON.stringify({id: j.id, parameters: j.parameters, result: j.result}, null, 2)}</pre></details>
      </article>;
  };
  return <>
    <PageTitle title="Data & jobs" text="Monitor imports, catalog processing and research comparisons."/>
    <ErrorBox error={task.error || cancel.error || activate.error || datasets.error || jobs.error || analyses.error}/>
    {task.isSuccess && <p role="status" className="success">Job queued. Progress appears below.</p>}
    <h2>Active jobs and failures</h2>
    {jobs.isLoading ? <p role="status">Loading jobs…</p> : activeJobs.length ? activeJobs.map(renderJob) : <p className="empty">No active jobs or failures.</p>}
    {history.length > 0 && <details className="panel" onToggle={e => setHistoryOpen(e.currentTarget.open)}><summary>Completed and cancelled jobs ({history.length})</summary>{historyOpen && history.map(renderJob)}</details>}
    <details className="panel"><summary>Import or analyze a dataset</summary>
      <p>Imports read files inside the server’s data folder. Corpus analysis can take time and is not needed for each search.</p>
      <form onSubmit={e => {e.preventDefault(); task.mutate({kind: 'import', parameters: {path, source, license}});}}>
        <div className="filter-row"><Field label="Adapter"><select value={source} onChange={e => setSource(e.target.value)}>
          {['jsonl','chordonomicon','billboard','isophonics'].map(x => <option key={x}>{x}</option>)}</select></Field>
          <Field label="Path within the data folder"><input required value={path} onChange={e => setPath(e.target.value)} placeholder="imports/my-corpus.jsonl"/></Field>
          <Field label="Source license"><input value={license} onChange={e => setLicense(e.target.value)}/></Field>
        </div><div className="actions"><button disabled={task.isPending}>Queue import</button>
          <button type="button" disabled={task.isPending} onClick={() => task.mutate({kind: 'analyze', parameters: {}})}>Analyze & index corpus</button></div>
      </form>
    </details>
    <details className="panel"><summary>Datasets ({datasets.data?.length ?? 0})</summary>{datasets.data?.map(d => <div className="dataset-row" key={d.id}>
      <h3>{d.name}</h3><p>{d.source} · {d.license}{d.synthetic ? ' · Synthetic fixture' : ''}</p>
      <details><summary>Validation and source identity</summary><pre>{JSON.stringify({fingerprint: d.fingerprint, report: d.report}, null, 2)}</pre></details>
    </div>)}</details>
    <details className="panel"><summary>Analysis versions</summary>{analyses.data?.map(a => <div className="analysis-row" key={a.id}>
      <code>{a.id.slice(0,8)}</code><span>{a.status}</span><span>{a.active ? 'Active research analysis' : a.report.catalog ? 'Catalog snapshots' : `${a.report.songs ?? 'Unknown'} songs`}</span>
      {!a.active && !a.report.catalog && a.status === 'ready' && <button onClick={() => activate.mutate(a.id)} disabled={activate.isPending}>Activate</button>}
    </div>)}</details>
    <details className="panel"><summary>Synthetic test fixtures</summary><p>Adds 120 constructed songs and a demonstration benchmark. Use an isolated demo environment for repeatable software checks.</p>
      <button disabled={task.isPending} onClick={() => task.mutate({kind: 'demo', parameters: {}})}>Load synthetic demo</button>
    </details>
  </>;
}
