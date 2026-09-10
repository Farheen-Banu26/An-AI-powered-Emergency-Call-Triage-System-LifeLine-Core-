import { Routes, Route } from "react-router-dom"
import Home from "./pages/Home"
import Dashboard from "./pages/Dashboard"
import CallPage from "./pages/CallPage"
import AdminDashboard from "./pages/AdminDashboard"

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/user" element={<CallPage />} />
      <Route path="/admin" element={<AdminDashboard />} />
    </Routes>
  )
}
