import type { ReactNode } from 'react';

export function precisePercent(value: number) {
  if (value === 0) return '0%';
  if (value === 1) return '100%';
  const number = value * 100;
  if (number > 0 && number < 0.0001) return '<0.0001%';
  if (number < 100 && number.toFixed(4) === '100.0000') return '>99.9999%';
  return `${number.toFixed(4).replace(/\.?0+$/, '')}%`;
}

export function formatScore(value: number) {
  const rounded = value.toFixed(6);
  if (value > 0 && rounded === '0.000000') return '<0.000001';
  if (value < 1 && rounded === '1.000000') return '<1.000000';
  return rounded;
}

export const sectionName = (value: string) => value.replaceAll('_', ' ');
export const modelName = (value: string) => ({
  path_expectation: 'Context paths', hard_path: 'Deterministic path', legacy_mixture: 'Averaged keys',
  uniform_path: 'Uniform alignment costs', max_path: 'Best path only', equal_paths: 'Equal path weights',
  shuffled_paths: 'Shuffled path weights',
}[value] || sectionName(value));

export function Field({label, children}: {label: string; children: ReactNode}) {
  return <label className="field"><span>{label}</span>{children}</label>;
}
export function ErrorBox({error}: {error: unknown}) {
  return error ? <p className="error" role="alert">{error instanceof Error ? error.message : String(error)}</p> : null;
}
export function PageTitle({title, text}: {title: string; text?: string}) {
  return <div className="page-title"><h1>{title}</h1>{text && <p>{text}</p>}</div>;
}
export function Tag({children}: {children: ReactNode; purple?: boolean}) {
  return <span className="tag">{children}</span>;
}
export function Empty({title, children}: {title: string; children?: ReactNode}) {
  return <div className="empty"><h3>{title}</h3>{children && <p>{children}</p>}</div>;
}
export function Busy() {
  return <p role="status" className="busy">Loading…</p>;
}
