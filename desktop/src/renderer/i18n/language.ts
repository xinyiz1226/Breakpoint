import type { Language } from './copy'

export const LANGUAGE_STORAGE_KEY = 'bp-desktop-language'

interface StorageLike {
  getItem: (key: string) => string | null
  setItem: (key: string, value: string) => void
}

export function parseStoredLanguage(value: string | null | undefined): Language | null {
  return value === 'en' || value === 'zh' ? value : null
}

export function detectDefaultLanguage(locale: string | undefined): Language {
  return locale?.toLowerCase().startsWith('zh') ? 'zh' : 'en'
}

export function readStoredLanguage(storage: StorageLike | undefined): Language | null {
  if (!storage) return null
  try {
    return parseStoredLanguage(storage.getItem(LANGUAGE_STORAGE_KEY))
  } catch {
    return null
  }
}

export function writeStoredLanguage(storage: StorageLike | undefined, language: Language): boolean {
  if (!storage) return false
  try {
    storage.setItem(LANGUAGE_STORAGE_KEY, language)
    return true
  } catch {
    return false
  }
}
