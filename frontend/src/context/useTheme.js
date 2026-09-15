import { createContext, useContext } from 'react';

/** Theme context and hook; see authContext.js for why these live outside the provider. */
export const ThemeContext = createContext();

export const useTheme = () => useContext(ThemeContext);

/** Motion/effect intensity levels offered in profile settings. */
export const FX_LEVELS = [
  { id: 'full', bn: 'পূর্ণ', en: 'Full', desc_bn: 'কোড রেইন, গ্লো ও সেলিব্রেশন অ্যানিমেশন', desc_en: 'Code rain, ambient glow and celebrations' },
  { id: 'minimal', bn: 'সংক্ষিপ্ত', en: 'Minimal', desc_bn: 'শুধু প্রয়োজনীয় ট্রানজিশন', desc_en: 'Only essential transitions' },
  { id: 'off', bn: 'বন্ধ', en: 'Off', desc_bn: 'কোনো অ্যানিমেশন নেই (ধীর ডিভাইসের জন্য)', desc_en: 'No animation - best on slow devices' },
];
