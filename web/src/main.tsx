import React, { Suspense, lazy } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
const View = lazy(() => location.pathname.startsWith('/studio') ? import('./Studio') : import('./MusicApp'));
const client = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 15000 } } });
createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={client}><Suspense fallback={<div style={{background:'#121412',color:'#f5f5ed',padding:40,minHeight:'100vh'}}>Opening HarmonyGraph…</div>}><View/></Suspense></QueryClientProvider></React.StrictMode>);
