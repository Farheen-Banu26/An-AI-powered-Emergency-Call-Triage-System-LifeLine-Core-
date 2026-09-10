import { useNavigate } from "react-router-dom"
import { User, ShieldAlert } from "lucide-react"
import { useLanguage } from "../context/LanguageContext"
import { translations } from "../i18n/translations"

export default function Dashboard() {
  const navigate = useNavigate()
  const { language } = useLanguage()
  const t = translations[language] ?? translations.en

  const roles = [
    {
      id: "user",
      title: t.role_user,
      icon: <User className="w-12 h-12" />,
      description: t.role_user_desc,
      color: "bg-safe/20 text-safe border-safe/30",
      path: "/user",
    },
    {
      id: "admin",
      title: t.role_admin,
      icon: <ShieldAlert className="w-12 h-12" />,
      description: t.role_admin_desc,
      color: "bg-emergency/20 text-emergency border-emergency/30",
      path: "/admin",
    },
  ]

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-6 bg-dark">
      <h2 className="text-4xl font-bold text-white mb-12 tracking-tight">
        {t.select_role}
      </h2>

      <div className="flex flex-col md:flex-row gap-8 w-full max-w-4xl">
        {roles.map((role) => (
          <div
            key={role.id}
            onClick={() => navigate(role.path)}
            className={`flex-1 glass p-10 rounded-[2rem] border-2 cursor-pointer group hover:scale-105 transition-all duration-500 ${role.color} flex flex-col items-center text-center`}
          >
            <div className="mb-6 group-hover:scale-110 transition-transform duration-500">
              {role.icon}
            </div>
            <h3 className="text-3xl font-black uppercase mb-4 tracking-wider">
              {role.title}
            </h3>
            <p className="text-slate-400 font-medium">{role.description}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
