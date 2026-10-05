import { useEffect, useRef, useState } from 'react';
import { Play, Pause, SkipBack, SkipForward, Volume2 } from 'lucide-react';
import type { components } from './generated/api';

type Section = components['schemas']['CatalogSection'];

export function ChordPractice({sections, beforePlay}: {sections: Section[]; beforePlay: () => void}) {
  const [section, setSection] = useState(0);
  const [position, setPosition] = useState(0);
  const [tempo, setTempo] = useState(90);
  const [beats, setBeats] = useState(2);
  const [loop, setLoop] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState('');
  const context = useRef<AudioContext | null>(null);
  const voices = useRef<OscillatorNode[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const generation = useRef(0);
  const current = sections[section];

  function silence() {
    for (const voice of voices.current) { try { voice.stop(); } catch { /* Already ended. */ } }
    voices.current = [];
  }
  function stop() {
    generation.current++;
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    silence();
    setPlaying(false);
  }
  useEffect(() => {
    const hide = () => { if (document.hidden) stop(); };
    addEventListener('harmonygraph:stop-practice', stop);
    document.addEventListener('visibilitychange', hide);
    return () => {
      generation.current++;
      if (timer.current) clearTimeout(timer.current);
      silence();
      void context.current?.close();
      removeEventListener('harmonygraph:stop-practice', stop);
      document.removeEventListener('visibilitychange', hide);
    };
  }, []);

  async function start(at: number, continuous: boolean) {
    stop();
    beforePlay();
    const ticket = generation.current;
    try {
      if (!context.current) context.current = new AudioContext();
      await context.current.resume();
      if (ticket !== generation.current) return;
      setError('');
      setPlaying(continuous);
      const duration = beats * 60 / tempo;
      const step = (index: number) => {
        if (ticket !== generation.current) return;
        silence();
        setPosition(index);
        const ctx = context.current!;
        const notes = current.practice[index]?.notes ?? [];
        for (const note of notes) {
          const oscillator = ctx.createOscillator();
          const gain = ctx.createGain();
          oscillator.type = 'triangle';
          oscillator.frequency.value = 440 * 2 ** ((note - 69) / 12);
          gain.gain.setValueAtTime(0, ctx.currentTime);
          gain.gain.linearRampToValueAtTime(0.16 / Math.max(1, notes.length), ctx.currentTime + 0.025);
          gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration * 0.94);
          oscillator.connect(gain); gain.connect(ctx.destination);
          oscillator.start(); oscillator.stop(ctx.currentTime + duration);
          oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
          voices.current.push(oscillator);
        }
        if (continuous) timer.current = setTimeout(() => {
          if (index + 1 < current.events.length) step(index + 1);
          else if (loop) step(0);
          else stop();
        }, duration * 1000);
      };
      step(at);
    } catch {
      stop();
      setError('Sound could not start in this browser. You can still follow the chord chart below.');
    }
  }

  if (!current) return null;
  const status = current.practice[position]?.status;
  return <section className="chord-practice" aria-label="Chord practice">
    <div className="practice-heading"><Volume2/><div><h2>Hear the harmony</h2><p>Practice with generated chord tones. No Spotify account needed.</p></div></div>
    <p className="practice-note">This plays the real chart at an even practice tempo. It is not the original recording or its timing.</p>
    <div className="practice-settings">
      <label>Practice section<select value={section} onChange={e => {stop(); setSection(Number(e.target.value)); setPosition(0);}}>{sections.map((s,i)=><option value={i} key={i}>{s.label.replace(/_/g,' ')}</option>)}</select></label>
      <label>Tempo: {tempo} BPM<input aria-label="Practice tempo" type="range" min="40" max="180" step="5" value={tempo} onChange={e=>{stop();setTempo(Number(e.target.value));}}/></label>
      <label>Beats per chord<select value={beats} onChange={e=>{stop();setBeats(Number(e.target.value));}}>{[1,2,4].map(n=><option value={n} key={n}>{n}</option>)}</select></label>
      <label className="practice-loop"><input type="checkbox" checked={loop} onChange={e=>{stop();setLoop(e.target.checked);}}/>Loop section</label>
    </div>
    <div className="practice-controls">
      <button aria-label="Previous practice chord" disabled={position===0} onClick={()=>void start(position-1,false)}><SkipBack size={18}/></button>
      <button className="lime-button" onClick={()=>playing?stop():void start(position,true)}>{playing?<Pause size={18}/>:<Play size={18}/>} {playing?'Pause practice':'Play chords'}</button>
      <button aria-label="Next practice chord" disabled={position===current.events.length-1} onClick={()=>void start(position+1,false)}><SkipForward size={18}/></button>
      <span role="status">Chord {position+1} of {current.events.length}: <b>{current.events[position]}</b>{status==='unknown'?' · unsupported symbol; silent':status==='no_chord'?' · rest':''}</span>
    </div>
    {error && <p role="alert">{error}</p>}
    <div className="practice-chords" aria-label="Choose a chord to hear">{current.events.map((label,i)=><button key={i} aria-label={`Hear chord ${i+1}: ${label}`} aria-pressed={position===i} onClick={()=>void start(i,false)}>{label.replace(/(^|\/)([A-G])s(?!us)/g,'$1$2♯').replace(/min/g,'m')}</button>)}</div>
  </section>;
}
