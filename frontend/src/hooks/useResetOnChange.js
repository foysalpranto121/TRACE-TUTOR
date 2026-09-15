import { useState } from 'react';

/**
 * Re-initialise some state when a value changes.
 *
 * This is the React-documented "adjusting state when a prop changes" pattern: compare
 * against the previous value during render and reset immediately, rather than doing it
 * in an effect. An effect runs *after* the browser has painted, so for one frame the
 * screen shows the previous problem's code, the previous item's ratings, or the
 * previous participant's profile - and React then has to render everything twice.
 *
 *   useResetOnChange(activeProblem.id, () => setCode(activeProblem.starterCode));
 */
export function useResetOnChange(value, reset) {
  const [previous, setPrevious] = useState(value);
  if (!Object.is(previous, value)) {
    setPrevious(value);
    reset();
  }
}
