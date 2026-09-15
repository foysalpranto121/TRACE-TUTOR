import { createContext, useContext } from 'react';

/** Celebration context and hook; see context/authContext.js for why these are separate. */
export const CelebrateContext = createContext({ toast: () => {}, levelUp: () => {} });

export const useCelebrate = () => useContext(CelebrateContext);
