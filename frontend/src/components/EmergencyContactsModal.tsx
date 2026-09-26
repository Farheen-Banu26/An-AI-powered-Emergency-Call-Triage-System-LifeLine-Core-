import { useState, useEffect } from "react"
import {
  Phone,
  MessageSquare,
  Share2,
  Copy,
  Plus,
  Trash2,
  CheckCircle2,
  AlertTriangle,
  X,
  User,
  Shield,
  Send,
  Info,
  Check,
} from "lucide-react"
import {
  type EmergencyContact,
  type NotificationRecord,
  loadEmergencyContacts,
  saveEmergencyContacts,
  loadNotificationHistory,
  recordNotification,
  generateEmergencyAlertText,
  triggerNativePhoneCall,
  triggerNativeSMS,
  triggerWhatsAppShare,
  copyAlertToClipboard,
} from "../lib/contacts"
import { cn } from "../lib/utils"

interface EmergencyContactsModalProps {
  isOpen: boolean
  onClose: () => void
  emergencyType?: string | null
  priorityLabel?: string | null
  location?: string | null
  guidance?: string | null
  language?: string
  sessionId?: string
  onNotificationSent?: (record: NotificationRecord) => void
}

export function EmergencyContactsModal({
  isOpen,
  onClose,
  emergencyType,
  priorityLabel,
  location,
  guidance,
  language = "en",
  sessionId,
  onNotificationSent,
}: EmergencyContactsModalProps) {
  const [contacts, setContacts] = useState<EmergencyContact[]>([])
  const [notifications, setNotifications] = useState<NotificationRecord[]>([])
  const [copied, setCopied] = useState(false)
  const [copiedPhoneId, setCopiedPhoneId] = useState<string | null>(null)
  const [desktopCallFeedback, setDesktopCallFeedback] = useState<string | null>(null)
  const [showAddContact, setShowAddContact] = useState(false)
  const [newName, setNewName] = useState("")
  const [newPhone, setNewPhone] = useState("")
  const [newRelationship, setNewRelationship] = useState("Family")

  useEffect(() => {
    if (isOpen) {
      setContacts(loadEmergencyContacts())
      setNotifications(loadNotificationHistory())
    }
  }, [isOpen])

  if (!isOpen) return null

  const alertMessage = generateEmergencyAlertText({
    emergencyType,
    priorityLabel,
    location,
    guidance,
    language,
  })

  const handleAddContact = () => {
    if (!newName.trim() || !newPhone.trim()) return
    const newContact: EmergencyContact = {
      id: "c_" + Date.now(),
      name: newName.trim(),
      phone: newPhone.trim(),
      relationship: newRelationship.trim(),
      enabled: true,
    }
    const updated = [...contacts, newContact]
    setContacts(updated)
    saveEmergencyContacts(updated)
    setNewName("")
    setNewPhone("")
    setShowAddContact(false)
  }

  const handleDeleteContact = (id: string) => {
    const updated = contacts.filter((c) => c.id !== id)
    setContacts(updated)
    saveEmergencyContacts(updated)
  }

  const handleCopyPhone = async (contact: EmergencyContact) => {
    try {
      await navigator.clipboard.writeText(contact.phone)
      setCopiedPhoneId(contact.id)
      setTimeout(() => setCopiedPhoneId(null), 2000)
    } catch {
      /* ignore */
    }
  }

  const handleCall = (contact: EmergencyContact) => {
    triggerNativePhoneCall(contact.phone)
    setDesktopCallFeedback(`Call action handed to device. If no telephony application is configured on this device, please dial ${contact.phone} directly or click Copy Number.`)
    setTimeout(() => setDesktopCallFeedback(null), 7000)
    const rec = recordNotification({
      contactId: contact.id,
      contactName: contact.name,
      type: "call",
      status: "sent",
      details: `Call action handed to device (${contact.phone})`,
    })
    setNotifications((prev) => [rec, ...prev])
    onNotificationSent?.(rec)
  }

  const handleSMS = (contact: EmergencyContact) => {
    triggerNativeSMS(contact.phone, alertMessage)
    setDesktopCallFeedback(`SMS action handed to device. If no SMS application is configured on this device, please use Copy Alert or WhatsApp.`)
    setTimeout(() => setDesktopCallFeedback(null), 7000)
    const rec = recordNotification({
      contactId: contact.id,
      contactName: contact.name,
      type: "sms",
      status: "sent",
      details: `SMS action handed to device (${contact.phone})`,
    })
    setNotifications((prev) => [rec, ...prev])
    onNotificationSent?.(rec)
  }

  const handleWhatsApp = (contact: EmergencyContact) => {
    triggerWhatsAppShare(contact.phone, alertMessage)
    const rec = recordNotification({
      contactId: contact.id,
      contactName: contact.name,
      type: "whatsapp",
      status: "sent",
      details: `WhatsApp opened for ${contact.name} (${contact.phone})`,
    })
    setNotifications((prev) => [rec, ...prev])
    onNotificationSent?.(rec)
  }

  const handleCopyAlert = async () => {
    const success = await copyAlertToClipboard(alertMessage)
    if (success) {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
      const rec = recordNotification({
        contactId: "self",
        contactName: "Clipboard",
        type: "copied",
        status: "sent",
        details: "Copied emergency alert text to clipboard",
      })
      setNotifications((prev) => [rec, ...prev])
      onNotificationSent?.(rec)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fadeIn">
      <div className="relative glass p-6 rounded-3xl w-full max-w-2xl max-h-[90vh] overflow-y-auto border border-white/20 shadow-2xl flex flex-col text-white">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-white/10 mb-4">
          <div className="flex items-center gap-2.5">
            <Shield className="h-5 w-5 text-red-500" />
            <div>
              <h3 className="text-lg font-black uppercase tracking-wider">
                Emergency Contacts & Alert Broadcast
              </h3>
              <p className="text-xs text-slate-400">
                Direct emergency contact dispatch & sharing
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-full bg-white/10 hover:bg-white/20 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Safety Disclaimer Banner */}
        <div className="p-3 mb-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
          <p>
            <strong>Personal Safety Alert:</strong> This triggers personal emergency contact notifications via your device. It does <em>not</em> automatically call public 911/112 services unless an authorized public safety integration is enabled.
          </p>
        </div>

        {/* Action Feedback Toast */}
        {desktopCallFeedback && (
          <div className="p-3 mb-3 rounded-xl bg-blue-500/20 border border-blue-500/40 text-blue-200 text-xs flex items-center justify-between gap-2 animate-fadeIn">
            <div className="flex items-center gap-2">
              <Info className="h-4 w-4 text-blue-400 shrink-0" />
              <span>{desktopCallFeedback}</span>
            </div>
            <button
              onClick={() => setDesktopCallFeedback(null)}
              className="text-slate-400 hover:text-white text-xs"
            >
              ✕
            </button>
          </div>
        )}

        {/* Generated Alert Preview */}
        <div className="mb-4 bg-black/40 p-3.5 rounded-2xl border border-white/10 flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Live Structured Emergency Alert Body
            </span>
            <button
              onClick={handleCopyAlert}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/10 hover:bg-white/20 text-xs font-bold text-white transition-colors"
            >
              {copied ? <CheckCircle2 className="h-3.5 w-3.5 text-green-400" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? "Copied!" : "Copy Alert"}
            </button>
          </div>
          <pre className="text-xs text-slate-300 whitespace-pre-wrap font-sans bg-black/20 p-2.5 rounded-xl border border-white/5 max-h-32 overflow-y-auto">
            {alertMessage}
          </pre>
        </div>

        {/* Contacts List */}
        <div className="mb-4 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Your Emergency Contacts ({contacts.length})
            </span>
            <button
              onClick={() => setShowAddContact(!showAddContact)}
              className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 font-bold"
            >
              <Plus className="h-3.5 w-3.5" />
              {showAddContact ? "Cancel" : "Add Contact"}
            </button>
          </div>

          {/* Add Contact Form */}
          {showAddContact && (
            <div className="p-3.5 rounded-2xl bg-white/5 border border-white/10 flex flex-col gap-2.5 animate-fadeIn">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <input
                  type="text"
                  placeholder="Contact Name"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="bg-black/30 border border-white/10 rounded-xl px-3 py-1.5 text-xs text-white outline-none focus:border-blue-500/50"
                />
                <input
                  type="tel"
                  placeholder="Phone Number (+91...)"
                  value={newPhone}
                  onChange={(e) => setNewPhone(e.target.value)}
                  className="bg-black/30 border border-white/10 rounded-xl px-3 py-1.5 text-xs text-white outline-none focus:border-blue-500/50"
                />
                <input
                  type="text"
                  placeholder="Relationship (e.g. Mother, Doctor)"
                  value={newRelationship}
                  onChange={(e) => setNewRelationship(e.target.value)}
                  className="bg-black/30 border border-white/10 rounded-xl px-3 py-1.5 text-xs text-white outline-none focus:border-blue-500/50"
                />
              </div>
              <button
                onClick={handleAddContact}
                disabled={!newName.trim() || !newPhone.trim()}
                className="self-end px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold transition-colors disabled:opacity-40"
              >
                Save Contact
              </button>
            </div>
          )}

          {/* Contact Cards */}
          {contacts.map((c) => (
            <div
              key={c.id}
              className="p-3.5 rounded-2xl bg-white/5 border border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
            >
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-blue-600/20 text-blue-400 border border-blue-500/30">
                  <User className="h-4 w-4" />
                </div>
                <div>
                  <p className="text-sm font-bold text-white flex items-center gap-2">
                    {c.name}
                    <span className="text-[10px] font-normal px-2 py-0.5 rounded-full bg-white/10 text-slate-300">
                      {c.relationship}
                    </span>
                  </p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-xs text-slate-300 font-mono font-semibold">{c.phone}</span>
                    <button
                      onClick={() => handleCopyPhone(c)}
                      className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-white/10 hover:bg-white/20 text-slate-300 transition-colors"
                      title="Copy Phone Number"
                    >
                      {copiedPhoneId === c.id ? (
                        <>
                          <Check className="h-3 w-3 text-green-400" />
                          <span className="text-green-400">Copied</span>
                        </>
                      ) : (
                        <>
                          <Copy className="h-3 w-3 text-slate-400" />
                          <span>Copy</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>

              {/* Action Buttons: [ Call ] [ SMS ] [ WhatsApp ] [ Delete ] */}
              <div className="flex items-center gap-2 self-end sm:self-auto flex-wrap">
                <button
                  onClick={() => handleCall(c)}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-green-600/80 hover:bg-green-600 text-white text-xs font-bold shadow-md transition-colors"
                  title="Call Contact via Phone Dialer"
                >
                  <Phone className="h-3.5 w-3.5" />
                  Call
                </button>
                <button
                  onClick={() => handleSMS(c)}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-blue-600/80 hover:bg-blue-600 text-white text-xs font-bold shadow-md transition-colors"
                  title="Send SMS Alert"
                >
                  <MessageSquare className="h-3.5 w-3.5" />
                  SMS
                </button>
                <button
                  onClick={() => handleWhatsApp(c)}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-emerald-600/80 hover:bg-emerald-600 text-white text-xs font-bold shadow-md transition-colors"
                  title="Share via WhatsApp"
                >
                  <Share2 className="h-3.5 w-3.5" />
                  WhatsApp
                </button>
                <button
                  onClick={() => handleDeleteContact(c.id)}
                  className="p-1.5 text-slate-500 hover:text-red-400 transition-colors"
                  title="Delete Contact"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* Notification History Log */}
        {notifications.length > 0 && (
          <div className="mt-2 pt-3 border-t border-white/10">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2 block">
              Recent Broadcast History ({notifications.length})
            </span>
            <div className="space-y-1.5 max-h-28 overflow-y-auto pr-1">
              {notifications.map((n) => (
                <div
                  key={n.id}
                  className="text-[11px] p-2 rounded-lg bg-black/30 border border-white/5 flex items-center justify-between"
                >
                  <div className="flex items-center gap-2">
                    <span className={cn(
                      "w-2 h-2 rounded-full",
                      n.status === "sent" ? "bg-green-400" : "bg-red-400"
                    )} />
                    <span className="font-bold text-slate-200">{n.contactName}</span>
                    <span className="text-slate-400">({n.type.toUpperCase()})</span>
                  </div>
                  <span className="text-[10px] text-slate-500 font-mono">{n.timestamp}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
