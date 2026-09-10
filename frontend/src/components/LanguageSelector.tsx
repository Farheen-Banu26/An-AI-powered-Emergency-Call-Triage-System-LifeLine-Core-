import { useLanguage } from "../context/LanguageContext"

const languages = [
  { code: "en", name: "English" },
  { code: "ta", name: "Tamil" },
  { code: "hi", name: "Hindi" },
  { code: "te", name: "Telugu" },
  { code: "kn", name: "Kannada" },
  { code: "ml", name: "Malayalam" },
]

export function LanguageSelector() {
  const { language, setLanguage } = useLanguage()

  return (
    <div className="flex items-center gap-2 glass px-4 py-2 rounded-xl">
      <select
        value={language}
        onChange={(e) => setLanguage(e.target.value)}
        className="bg-transparent text-white text-sm outline-none cursor-pointer"
      >
        {languages.map((lang) => (
          <option
            key={lang.code}
            value={lang.code}
            className="bg-dark text-white"
          >
            {lang.name}
          </option>
        ))}
      </select>
    </div>
  )
}
