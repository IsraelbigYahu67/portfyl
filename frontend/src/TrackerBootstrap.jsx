import './fonts.css';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { EditionAppFrame } from '@edition-manifest';
import App from './App';

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1 } } });

export default function TrackerBootstrap() {
  return <EditionAppFrame><QueryClientProvider client={queryClient}><BrowserRouter><App /></BrowserRouter></QueryClientProvider></EditionAppFrame>;
}
