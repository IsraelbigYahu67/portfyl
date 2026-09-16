import { fireEvent, render, screen } from '@testing-library/react';
import AssistantContextDialog from './AssistantContextDialog';

it('names the recipient and data, traps focus, and dismisses safely', () => {
  const safe = vi.fn(), share = vi.fn();
  const view = render(<AssistantContextDialog open provider="DeepSeek" model="deepseek-chat" onWithoutContext={safe} onShare={share} />);
  expect(screen.getByRole('dialog')).toHaveTextContent(/DeepSeek.*deepseek-chat/);
  for (const text of [/tickers/i, /quantities/i, /prices/i, /values/i, /recent trade/i, /delayed/i]) expect(screen.getByRole('dialog')).toHaveTextContent(text);
  const secondary = screen.getByRole('button', { name: 'Ask without portfolio data' });
  const primary = screen.getByRole('button', { name: 'Share for this conversation' });
  expect(secondary).toHaveFocus();
  fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
  expect(primary).toHaveFocus();
  fireEvent.keyDown(document, { key: 'Tab' });
  expect(secondary).toHaveFocus();
  fireEvent.keyDown(document, { key: 'Escape' });
  expect(safe).toHaveBeenCalledTimes(1);
  expect(share).not.toHaveBeenCalled();
  fireEvent.mouseDown(screen.getByTestId('assistant-context-backdrop'));
  expect(safe).toHaveBeenCalledTimes(2);
  view.rerender(<AssistantContextDialog open={false} onWithoutContext={safe} onShare={share} />);
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});
