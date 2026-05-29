export { COPY, LANGUAGE_LABELS } from './copy'
export type { Copy, Language } from './copy'
export {
  LANGUAGE_STORAGE_KEY,
  detectDefaultLanguage,
  parseStoredLanguage,
  readStoredLanguage,
  writeStoredLanguage,
} from './language'
export { LanguageProvider, useCopy, useLanguage } from './LanguageProvider'
