import { createContext, useContext, useState, type ReactNode } from "react"

interface LanguageContextValue {
  language: string
  setLanguage: (lang: string) => void
}

const LanguageContext = createContext<LanguageContextValue | null>(null)

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState("en")
  return (
    <LanguageContext.Provider value={{ language, setLanguage }}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext)
  if (!ctx) throw new Error("useLanguage must be used inside LanguageProvider")
  return ctx
}
