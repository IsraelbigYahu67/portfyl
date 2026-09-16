import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import Assistant from './Assistant';

const api = vi.hoisted(() => ({ fetchAssistantConfig: vi.fn(), saveAssistantConfig: vi.fn(), deleteAssistantConfig: vi.fn(), sendAssistantMessage: vi.fn() }));
vi.mock('../api', () => api);
beforeEach(() => {
  vi.clearAllMocks();
  api.fetchAssistantConfig.mockResolvedValue({ configured: true, model: 'deepseek-chat' });
  api.sendAssistantMessage.mockImplementation((_, mode) => Promise.resolve({ reply: { role: 'assistant', content: 'Answer' }, provider: 'deepseek', model: 'deepseek-chat', context_mode: mode, context_as_of: mode === 'none' ? null : '2026-09-16T10:00:00+00:00' }));
});
async function setup() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Assistant /></QueryClientProvider>);
  await screen.findByRole('textbox', { name: 'Message' });
}
function send(text = 'Question') {
  fireEvent.change(screen.getByRole('textbox', { name: 'Message' }), { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }));
}
function summary() { fireEvent.change(screen.getByLabelText('Portfolio context'), { target: { value: 'portfolio_summary' } }); }

it('starts safe and forwards only role/content history with explicit none', async () => {
  await setup();
  expect(screen.getByLabelText('Portfolio context')).toHaveValue('none');
  send();
  await screen.findByText('Answer');
  expect(api.sendAssistantMessage).toHaveBeenCalledWith([{ role: 'user', content: 'Question' }], 'none');
  expect(screen.getByText('No portfolio data shared')).toBeInTheDocument();
  send('Second');
  await waitFor(() => expect(api.sendAssistantMessage).toHaveBeenCalledTimes(2));
  expect(api.sendAssistantMessage.mock.calls[1][0].every(message => Object.keys(message).length === 2)).toBe(true);
});

it('pauses for consent, reuses a conversation grant, and clears it on new conversation', async () => {
  await setup(); summary(); send();
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  expect(api.sendAssistantMessage).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Share for this conversation' }));
  await screen.findByText('Answer');
  expect(api.sendAssistantMessage.mock.calls[0][1]).toBe('portfolio_summary');
  expect(screen.getByText('Portfolio summary shared')).toBeInTheDocument();
  expect(screen.getByText(/Context as of/)).toBeInTheDocument();
  send('Second');
  await waitFor(() => expect(api.sendAssistantMessage).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(screen.getByRole('button', { name: 'New conversation' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'New conversation' }));
  expect(screen.queryByText('Answer')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Portfolio context')).toHaveValue('none');
  summary(); send();
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  expect(api.sendAssistantMessage).toHaveBeenCalledTimes(2);
});

it.each(['Ask without portfolio data', 'Escape', 'backdrop'])('resolves %s with no portfolio sharing', async action => {
  await setup(); summary(); send();
  if (action === 'Escape') fireEvent.keyDown(document, { key: 'Escape' });
  else if (action === 'backdrop') fireEvent.mouseDown(screen.getByTestId('assistant-context-backdrop'));
  else fireEvent.click(screen.getByRole('button', { name: action }));
  await screen.findByText('Answer');
  expect(api.sendAssistantMessage).toHaveBeenCalledTimes(1);
  expect(api.sendAssistantMessage.mock.calls[0][1]).toBe('none');
  expect(screen.getByLabelText('Portfolio context')).toHaveValue('none');
});
