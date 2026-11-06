import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppShell } from '../src/components/Layout/AppShell';

const mocks = vi.hoisted(() => ({ language: 'en', logout: vi.fn(), desktop: null }));
vi.mock('../src/context/useAuth', () => ({ useAuth: () => ({
  user: { id: 42, username: 'QA teacher' }, role: 'EXPERT_TEACHER', arm: 'ANSWER_ONLY',
  language: mocks.language, logout: mocks.logout, toggleArm: vi.fn(), setLanguage: vi.fn(),
}) }));
vi.mock('../src/context/useTheme', () => ({ useTheme: () => ({ isDark: false, toggleTheme: vi.fn() }) }));
vi.mock('../src/components/Layout/HeaderSearch', () => ({ HeaderSearch: () => <input aria-label="Background search" /> }));

beforeEach(() => {
  mocks.language = 'en'; mocks.logout.mockReset();
  mocks.desktop = { matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() };
  vi.stubGlobal('matchMedia', vi.fn(() => mocks.desktop));
  // jsdom has no top-layer implementation. Assert that the browser's modal API
  // is used; browser-native focus containment and inertness require browser QA.
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: vi.fn(function () { this.setAttribute('open', ''); }) });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: vi.fn(function () { this.removeAttribute('open'); }) });
});
afterEach(() => {
  cleanup(); delete HTMLDialogElement.prototype.showModal; delete HTMLDialogElement.prototype.close;
  vi.unstubAllGlobals();
});

const mount = () => render(<MemoryRouter initialEntries={['/expert']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
  <AppShell><button>Page action</button></AppShell>
</MemoryRouter>);
const open = () => {
  const opener = screen.getByRole('button', { name: 'Open menu' });
  opener.focus(); fireEvent.click(opener);
  return opener;
};

it('opens a named native modal, focuses its close button, and restores focus on native Escape cancellation', () => {
  mount(); const opener = open();
  const drawer = screen.getByRole('dialog', { name: 'Main navigation' });
  expect(HTMLDialogElement.prototype.showModal).toHaveBeenCalledOnce();
  expect(document.activeElement).toBe(within(drawer).getByRole('button', { name: 'Close menu' }));
  expect(opener.getAttribute('aria-expanded')).toBe('true');
  fireEvent(drawer, new Event('cancel', { bubbles: false }));
  expect(screen.queryByRole('dialog')).toBeNull(); expect(document.activeElement).toBe(opener);
});

it('dismisses through the close button and backdrop, without treating inside clicks as backdrop clicks', () => {
  mount(); const opener = open();
  let drawer = screen.getByRole('dialog');
  fireEvent.click(within(drawer).getByRole('navigation'));
  expect(screen.getByRole('dialog')).toBe(drawer);
  fireEvent.click(within(drawer).getByRole('button', { name: 'Close menu' }));
  expect(screen.queryByRole('dialog')).toBeNull(); expect(document.activeElement).toBe(opener);
  open(); drawer = screen.getByRole('dialog'); fireEvent.click(drawer);
  expect(screen.queryByRole('dialog')).toBeNull(); expect(document.activeElement).toBe(opener);
});

it('closes the modal on route changes and desktop resize and removes the viewport listener', () => {
  mount(); open();
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('link', { name: /Profile & settings/ }));
  expect(screen.queryByRole('dialog')).toBeNull();
  open(); mocks.desktop.matches = true;
  const handler = mocks.desktop.addEventListener.mock.calls.at(-1)[1];
  // matchMedia callbacks are supplied by the browser, not jsdom.
  act(() => handler());
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(mocks.desktop.removeEventListener).toHaveBeenCalledWith('change', handler);
});

it.each(['en', 'bn'])('names both logout controls in %s even when header text is hidden', (language) => {
  mocks.language = language; mount();
  const label = language === 'bn' ? 'লগ আউট' : 'Log out';
  const header = document.querySelector('header');
  expect(within(header).getByRole('button', { name: label }).getAttribute('aria-label')).toBe(label);
  fireEvent.click(screen.getByRole('button', { name: language === 'bn' ? 'মেনু খুলুন' : 'Open menu' }));
  expect(within(screen.getByRole('dialog')).getByRole('button', { name: label })).toBeTruthy();
});
