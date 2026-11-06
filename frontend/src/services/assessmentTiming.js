export const formatTimingDate = (value) => {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('en-GB', {
    timeZone: 'Asia/Dhaka', day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
};

export const formatElapsedDays = (days, language = 'bn') => {
  if (days == null || !Number.isFinite(Number(days))) return '—';
  const minutes = Math.round(Math.max(0, Number(days)) * 24 * 60);
  if (language === 'en') return `${Math.floor(minutes / 1440)} days ${Math.floor((minutes % 1440) / 60)} hours ${minutes % 60} minutes`;
  return `${Math.floor(minutes / 1440)} দিন ${Math.floor((minutes % 1440) / 60)} ঘণ্টা ${minutes % 60} মিনিট`;
};
