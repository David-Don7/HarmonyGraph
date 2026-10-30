import { useState } from 'react';
import { useApi } from './api';
import { ErrorBox, PageTitle, precisePercent, sectionName } from './StudioUI';

const KEYS = ['C','C♯','D','E♭','E','F','F♯','G','A♭','A','B♭','B']; // taste-skill-ignore: musical accidentals are data, not decorative emoji
const keyName = (key: number) => `${KEYS[key % 12]} ${key >= 12 ? 'minor' : 'major'}`;

export default function StudioSong({id, analysisId, onBack}: {id: string; analysisId?: string; onBack: () => void}) {
  const song = useApi(`/songs/${id}${analysisId ? `?analysis_id=${encodeURIComponent(analysisId)}` : ''}`);
  const [selected, setSelected] = useState(0);
  if (song.isLoading) return <p role="status">Loading song analysis…</p>;
  if (!song.data) return <><button onClick={onBack}>Back to workspace</button><ErrorBox error={song.error}/></>;
  const s = song.data;
  const event = s.events[selected];
  const probabilities = event?.posterior.map((probability: number, key: number) => ({key, probability}))
    .filter((p: any) => p.probability > 0).sort((a: any, b: any) => b.probability - a.probability).slice(0, 5) || [];
  const relations = [...new Map<string, any>((s.relations || []).map((r: any) => [`${r.kind}:${r.start}:${r.end}`, r] as [string, any])).values()];
  const relationRows = (rows: any[]) => rows.map(r => <div className="relation-row" key={`${r.kind}:${r.start}:${r.end}`}>
    <span>{sectionName(r.kind)}</span><span>Chord events {r.start + 1}–{r.end + 1}</span></div>);
  return <>
    <button className="back" onClick={onBack}>← Back to workspace</button>
    <PageTitle title={s.title || s.source_id} text={`${s.artist || 'Artist unavailable'} · ${s.events.length} chord event${s.events.length === 1 ? '' : 's'} · ${s.sections.length} section${s.sections.length === 1 ? '' : 's'}`}/>
    {s.synthetic && <p className="notice">Synthetic research fixture</p>}
    <div className="panel timeline">{s.sections.map((section: any) => <section className="timeline-section" key={section.id}>
      <h2>{sectionName(section.label)} <small>Events {section.start + 1}–{section.end + 1}</small></h2>
      <div className="timeline-chords">{s.events.slice(section.start, section.end + 1).map((e: any) => <button key={e.id}
        aria-pressed={selected === e.ordinal} className={selected === e.ordinal ? 'chosen' : ''} onClick={() => setSelected(e.ordinal)}>
        <small>{e.ordinal + 1}</small><strong>{e.label}</strong><span>{keyName(e.path_key)}</span>
      </button>)}</div>
    </section>)}</div>
    {event && <section className="panel"><h2>Event {selected + 1} · {event.label}</h2>
      <div className="detail-grid">
        <div><h3>Possible keys</h3><p className="field-help">Up to five nonzero model probabilities out of 24 keys.</p>
          <div className="hypothesis-list">{probabilities.map((p: any) => <div key={p.key}>
            <span>{keyName(p.key)}</span><span>{precisePercent(p.probability)}</span>
          </div>)}</div>
        </div>
        <div><h3>Functional alternatives</h3><p className="field-help">Each reading assumes the key shown. It does not imply that key is certain.</p>
          {Object.entries(event.interpretations).filter(([key]) => event.posterior[Number(key)] > 0).map(([key, values]: any) => <div className="interpretation" key={key}>
            <div className="interpretation-heading"><strong>{keyName(Number(key))}</strong><span>{precisePercent(event.posterior[Number(key)])} key probability</span></div>
            {values.map((v: any, i: number) => <p key={i}><strong>{v.roman}</strong> · {v.function}
              {values.length > 1 && <span> · {precisePercent(v.weight)} weight given this key</span>}</p>)}
          </div>)}
        </div>
      </div>
      <p className="field-help">Key probabilities and function weights are model assumptions; musical calibration has not been established.</p>
    </section>}
    <section className="panel"><h2>Harmonic relation candidates</h2><p className="field-help">Rule-generated candidates, not verified cadences. Repeated hypotheses for the same event range are grouped.</p>
      {relations.length ? <>{relationRows(relations.slice(0, 8))}{relations.length > 8 && <details><summary>{relations.length - 8} more relation candidates</summary>{relationRows(relations.slice(8))}</details>}</>
        : <p>No relation candidates were stored for this analysis.</p>}
      {!!s.relations?.length && <details><summary>Individual hypotheses and model weights</summary><pre>{JSON.stringify(s.relations, null, 2)}</pre></details>}
    </section>
    <details className="panel"><summary>Source annotations and analysis identity</summary><p>Analysis <code>{s.analysis_id}</code></p><pre>{JSON.stringify(s.source, null, 2)}</pre></details>
  </>;
}
