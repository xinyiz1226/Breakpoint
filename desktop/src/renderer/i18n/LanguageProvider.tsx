import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import { COPY, type Copy, type Language } from './copy'
import { detectDefaultLanguage, readStoredLanguage, writeStoredLanguage } from './language'

interface LanguageContextValue {
  language: Language
  copy: Copy
  setLanguage: (language: Language) => void
}

const LanguageContext = createContext<LanguageContextValue | null>(null)

function getInitialLanguage(): Language {
  const stored = readStoredLanguage(typeof window !== 'undefined' ? window.localStorage : undefined)
  if (stored) return stored
  const locale = typeof navigator !== 'undefined' ? navigator.language : undefined
  return detectDefaultLanguage(locale)
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(getInitialLanguage)

  const value = useMemo<LanguageContextValue>(() => ({
    language,
    copy: COPY[language],
    setLanguage: (nextLanguage) => {
      setLanguageState(nextLanguage)
      writeStoredLanguage(typeof window !== 'undefined' ? window.localStorage : undefined, nextLanguage)
    },
  }), [language])

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  )
}

function useLanguageContext(): LanguageContextValue {
  const value = useContext(LanguageContext)
  if (!value) {
    throw new Error('LanguageProvider is missing')
  }
  return value
}

export function useLanguage() {
  const { language, setLanguage } = useLanguageContext()
  return { language, setLanguage }
}

export function useCopy(): Copy {
  return useLanguageContext().copy
}
