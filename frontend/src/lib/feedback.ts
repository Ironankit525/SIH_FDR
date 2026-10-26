// Haptics for meaningful moments only (success, error, a sheet or drawer snapping into place), fired in the
// same frame as the visual change. Touch devices only; silently absent where the Vibration API is not.
type Kind = 'success' | 'error' | 'snap'
const PATTERNS: Record<Kind, number | number[]> = { success: 12, snap: 8, error: [24, 50, 24] }

export function haptic(kind: Kind) {
  try {
    if (!window.matchMedia?.('(pointer: coarse)').matches || !('vibrate' in navigator)) return
    navigator.vibrate(PATTERNS[kind])
  } catch {
    // Feedback is a courtesy; never let it interrupt the action.
  }
}
