export interface EmergencyContact {
  id: string
  name: string
  phone: string
  relationship: string
  enabled: boolean
}

export interface NotificationRecord {
  id: string
  contactId: string
  contactName: string
  type: "call" | "sms" | "whatsapp" | "copied"
  status: "pending" | "sent" | "failed"
  timestamp: string
  details?: string
}

export interface ServiceContact {
  type: "primary" | "secondary"
  label: string
  phone: string
  telUrl: string
}

export interface EmergencyServiceConfig {
  id: "ambulance" | "fire" | "bluecross"
  name: string
  title: string
  iconName: string
  contacts: [ServiceContact, ServiceContact]
}

export const EMERGENCY_SERVICE_CONTACTS: Record<"ambulance" | "fire" | "bluecross", EmergencyServiceConfig> = {
  ambulance: {
    id: "ambulance",
    name: "Ambulance",
    title: "Ambulance Emergency Service",
    iconName: "Ambulance",
    contacts: [
      {
        type: "primary",
        label: "Primary Contact",
        phone: "+91 9597755699",
        telUrl: "tel:+919597755699",
      },
      {
        type: "secondary",
        label: "Secondary Contact",
        phone: "+91 9791748499",
        telUrl: "tel:+919791748499",
      },
    ],
  },
  fire: {
    id: "fire",
    name: "Fire Service",
    title: "Fire & Rescue Service",
    iconName: "Flame",
    contacts: [
      {
        type: "primary",
        label: "Primary Contact",
        phone: "+91 9597755699",
        telUrl: "tel:+919597755699",
      },
      {
        type: "secondary",
        label: "Secondary Contact",
        phone: "+91 9791748499",
        telUrl: "tel:+919791748499",
      },
    ],
  },
  bluecross: {
    id: "bluecross",
    name: "Blue Cross",
    title: "Blue Cross Emergency",
    iconName: "PlusCircle",
    contacts: [
      {
        type: "primary",
        label: "Primary Contact",
        phone: "+91 9597755699",
        telUrl: "tel:+919597755699",
      },
      {
        type: "secondary",
        label: "Secondary Contact",
        phone: "+91 9791748499",
        telUrl: "tel:+919791748499",
      },
    ],
  },
}

const CONTACTS_STORAGE_KEY = "lifeline_emergency_contacts_v1"
const NOTIFICATIONS_STORAGE_KEY = "lifeline_notifications_history_v1"

export const DEFAULT_CONTACTS: EmergencyContact[] = [
  {
    id: "c1",
    name: "Primary Family Contact",
    phone: "+91 9597755699",
    relationship: "Family / Guardian",
    enabled: true,
  },
  {
    id: "c2",
    name: "Doctor / Caregiver",
    phone: "+91 9791748499",
    relationship: "Physician / Caregiver",
    enabled: true,
  },
]

export function loadEmergencyContacts(): EmergencyContact[] {
  try {
    const raw = localStorage.getItem(CONTACTS_STORAGE_KEY)
    if (!raw) {
      saveEmergencyContacts(DEFAULT_CONTACTS)
      return DEFAULT_CONTACTS
    }
    const parsed = JSON.parse(raw) as EmergencyContact[]
    if (!Array.isArray(parsed) || parsed.length === 0) {
      saveEmergencyContacts(DEFAULT_CONTACTS)
      return DEFAULT_CONTACTS
    }
    // Update any default placeholder numbers while preserving custom user contacts
    let modified = false
    const updated = parsed.map((c) => {
      if (
        c.id === "c1" &&
        (c.phone === "+919876543210" ||
          c.phone === "+91 9876543210" ||
          c.name === "Primary Family Contact" && c.phone.includes("9876543210"))
      ) {
        modified = true
        return { ...c, phone: "+91 9597755699" }
      }
      if (
        c.id === "c2" &&
        (c.phone === "+919876543211" ||
          c.phone === "+91 9876543211" ||
          c.name === "Doctor / Caregiver" && c.phone.includes("9876543211"))
      ) {
        modified = true
        return { ...c, phone: "+91 9791748499" }
      }
      return c
    })
    if (modified) {
      saveEmergencyContacts(updated)
    }
    return updated
  } catch {
    return DEFAULT_CONTACTS
  }
}

export function saveEmergencyContacts(contacts: EmergencyContact[]): void {
  try {
    localStorage.setItem(CONTACTS_STORAGE_KEY, JSON.stringify(contacts))
  } catch {
    /* ignore localStorage errors */
  }
}

export function loadNotificationHistory(): NotificationRecord[] {
  try {
    const raw = localStorage.getItem(NOTIFICATIONS_STORAGE_KEY)
    if (!raw) return []
    return JSON.parse(raw) as NotificationRecord[]
  } catch {
    return []
  }
}

export function recordNotification(entry: Omit<NotificationRecord, "id" | "timestamp">): NotificationRecord {
  const record: NotificationRecord = {
    ...entry,
    id: "notif_" + Date.now() + "_" + Math.random().toString(36).substring(2, 7),
    timestamp: new Date().toLocaleTimeString(),
  }
  try {
    const existing = loadNotificationHistory()
    const updated = [record, ...existing].slice(0, 50)
    localStorage.setItem(NOTIFICATIONS_STORAGE_KEY, JSON.stringify(updated))
  } catch {
    /* ignore */
  }
  return record
}

/**
 * Generates a structured multi-language emergency alert string for sharing via SMS / WhatsApp.
 */
export function generateEmergencyAlertText(data: {
  emergencyType?: string | null
  priorityLabel?: string | null
  location?: string | null
  guidance?: string | null
  language?: string
}): string {
  const lang = data.language || "en"
  const type = data.emergencyType || (lang === "ta" ? "அவசரநிலை" : lang === "hi" ? "आपातकाल" : "Medical Emergency")
  const priority = data.priorityLabel || (lang === "ta" ? "முக்கியமானது (P1)" : lang === "hi" ? "गंभीर (P1)" : "CRITICAL (P1)")
  const location = data.location || (lang === "ta" ? "இருப்பிடம் பெறப்படுகிறது" : lang === "hi" ? "स्थान प्राप्त किया जा रहा है" : "Location shared via GPS")
  const timeStr = new Date().toLocaleTimeString()

  if (lang === "ta") {
    return `🚨 லைஃப்லைன் அவசர எச்சரிக்கை 🚨\n\nவகை: ${type}\nஅவசரம்: ${priority}\nநேரம்: ${timeStr}\nஇருப்பிடம்: ${location}\n\nஉடனடி பாதுகாப்பு வழிமுறை:\n${data.guidance || "உடனடி மருத்துவ உதவியை நாடுங்கள்."}\n\n(லைஃப்லைன் கோர் அவசர உதவி தளத்தால் உருவாக்கப்பட்டது)`
  }

  if (lang === "hi") {
    return `🚨 लाइफलाइन आपातकालीन चेतावनी 🚨\n\nप्रकार: ${type}\nप्राथमिकता: ${priority}\nसमय: ${timeStr}\nस्थान: ${location}\n\nसुरक्षा मार्गदर्शन:\n${data.guidance || "कृपया तुरंत आपातकालीन चिकित्सा सहायता लें।"}\n\n(लाइफलाइन कोर आपातकालीन प्रणाली द्वारा निर्मित)`
  }

  return `🚨 LIFE-LINE EMERGENCY ALERT 🚨\n\nEmergency Type: ${type}\nSeverity / Priority: ${priority}\nTimestamp: ${timeStr}\nLocation: ${location}\n\nImmediate Guidance:\n${data.guidance || "Seek emergency assistance immediately."}\n\n(Generated via LifeLine-Core Emergency Coordination Platform)`
}

/**
 * Triggers native tel: call.
 * Hands the tel: URI to the browser / operating system telephony handler.
 */
export function triggerNativePhoneCall(phoneNumber: string): boolean {
  const cleanPhone = phoneNumber.replace(/[^0-9+]/g, "")
  if (!cleanPhone) return false
  window.location.href = `tel:${cleanPhone}`
  return true
}

/**
 * Triggers native SMS sharing with prefilled alert body.
 * Hands the sms: URI to the browser / operating system SMS handler.
 */
export function triggerNativeSMS(phoneNumber: string, alertBody: string): boolean {
  const cleanPhone = phoneNumber.replace(/[^0-9+]/g, "")
  const encodedBody = encodeURIComponent(alertBody)
  window.location.href = `sms:${cleanPhone}?body=${encodedBody}`
  return true
}

/**
 * Triggers WhatsApp sharing with prefilled alert body.
 */
export function triggerWhatsAppShare(phoneNumber: string, alertBody: string): void {
  const cleanPhone = phoneNumber.replace(/[^0-9]/g, "")
  const encodedBody = encodeURIComponent(alertBody)
  const url = cleanPhone
    ? `https://api.whatsapp.com/send?phone=${cleanPhone}&text=${encodedBody}`
    : `https://api.whatsapp.com/send?text=${encodedBody}`
  window.open(url, "_blank", "noopener,noreferrer")
}

/**
 * Copies the alert to the clipboard.
 */
export async function copyAlertToClipboard(alertBody: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(alertBody)
    return true
  } catch {
    return false
  }
}
