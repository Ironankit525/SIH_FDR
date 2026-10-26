import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
export function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)) }
export const money = (value: number | string | undefined) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Number(value || 0))
export const compactMoney = (value: number) => value >= 1e7 ? `₹${(value / 1e7).toFixed(2)} Cr` : value >= 1e5 ? `₹${(value / 1e5).toFixed(1)} L` : money(value)
export const label = (value: string = '') => value.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase())
// Until the bank answers there is nothing to judge: say so plainly instead of implying a problem.
const VERIFICATION_TEXT: Record<string, string> = {
  pending: 'Bank has not confirmed yet', mock_pending: 'Mock · bank has not confirmed yet', officially_confirmed: 'Confirmed by the bank',
  mock_confirmed: 'Mock confirmed', mismatched: 'Bank reports a mismatch', inconclusive: 'Bank answer inconclusive', mock_inconclusive: 'Mock · inconclusive',
}
export const verificationLabel = (value: string = 'pending') => VERIFICATION_TEXT[value] ?? label(value)
export const dateLabel = (value?: string | null) => value ? new Date(value).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : 'Not recorded'
