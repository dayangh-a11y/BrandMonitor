export type NavId =
  | 'dashboard'
  | 'races'
  | 'horses'
  | 'predictions'
  | 'analytics'
  | 'system'

export const NAV_ITEMS: { id: NavId; label: string; short: string }[] = [
  { id: 'dashboard', label: 'Dashboard', short: 'خانه' },
  { id: 'races', label: 'Races', short: 'مسابقات' },
  { id: 'horses', label: 'Horses', short: 'اسب‌ها' },
  { id: 'predictions', label: 'Predictions', short: 'پیش‌بینی' },
  { id: 'analytics', label: 'Analytics', short: 'تحلیل' },
  { id: 'system', label: 'System', short: 'سیستم' },
]
