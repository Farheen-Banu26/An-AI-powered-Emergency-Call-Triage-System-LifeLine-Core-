export interface OfflineIncidentAction {
  id: string
  timestamp: string
  actionType: "message" | "location" | "evidence" | "contact_notification"
  payload: any
  synced: boolean
}

const OFFLINE_QUEUE_KEY = "lifeline_offline_sync_queue_v1"

export class OfflineManager {
  private isOnline: boolean = typeof navigator !== "undefined" ? navigator.onLine : true
  private listeners: ((online: boolean) => void)[] = []

  constructor() {
    if (typeof window !== "undefined") {
      window.addEventListener("online", () => {
        this.isOnline = true
        this.notifyListeners(true)
      })
      window.addEventListener("offline", () => {
        this.isOnline = false
        this.notifyListeners(false)
      })
    }
  }

  public getOnlineStatus(): boolean {
    return this.isOnline
  }

  public onStatusChange(callback: (online: boolean) => void): () => void {
    this.listeners.push(callback)
    return () => {
      this.listeners = this.listeners.filter((l) => l !== callback)
    }
  }

  private notifyListeners(online: boolean) {
    this.listeners.forEach((l) => l(online))
  }

  public queueAction(actionType: OfflineIncidentAction["actionType"], payload: any): void {
    try {
      const queue = this.getQueue()
      const newAction: OfflineIncidentAction = {
        id: "offline_" + Date.now() + "_" + Math.random().toString(36).substring(2, 6),
        timestamp: new Date().toISOString(),
        actionType,
        payload,
        synced: false,
      }
      queue.push(newAction)
      localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(queue))
    } catch {
      /* ignore */
    }
  }

  public getQueue(): OfflineIncidentAction[] {
    try {
      const raw = localStorage.getItem(OFFLINE_QUEUE_KEY)
      return raw ? JSON.parse(raw) : []
    } catch {
      return []
    }
  }

  public clearQueue(): void {
    try {
      localStorage.removeItem(OFFLINE_QUEUE_KEY)
    } catch {
      /* ignore */
    }
  }

  /**
   * Deterministic offline first-aid guidance for critical life-safety situations.
   */
  public getOfflineGuidance(text: string, language: string = "en"): string {
    const lower = text.toLowerCase()

    if (language === "ta") {
      if (lower.includes("மூச்சு") || lower.includes("மயக்கம்") || lower.includes("மாரடைப்பு")) {
        return "⚠️ ஆஃப்லைன் பயன்முறை: நோயாளிக்கு மூச்சு இல்லை என்றால், உடனடியாக அவரை தட்டையாக படுக்க வைத்து மார்பின் மையத்தில் தொடர்ந்து 100-120 முறை வேகமாக அழுத்தவும் (CPR)."
      }
      if (lower.includes("ரத்தம்") || lower.includes("காயம்")) {
        return "⚠️ ஆஃப்லைன் பயன்முறை: ரத்தம் வழியும் இடத்தில் சுத்தமான துணியை வைத்து அழுத்தமாக அழுத்திப் பிடிக்கவும். காயத்தை இதய மட்டத்திற்கு மேலே உயர்த்தவும்."
      }
      if (lower.includes("தீ")) {
        return "⚠️ ஆஃப்லைன் பயன்முறை: உடனடியாக கட்டடத்தை விட்டு வெளியேறவும். புகைக்கு கீழே குனிந்து தவழ்ந்து செல்லவும்."
      }
      return "⚠️ ஆஃப்லைன் பயன்முறை: அவசர உதவிக்கு அமைதியாக இருங்கள். இணைய இணைப்பு திரும்பியவுடன் தகவல் சேவையகத்திற்கு அனுப்பப்படும்."
    }

    if (language === "hi") {
      if (lower.includes("सांस") || lower.includes("बेहोश") || lower.includes("दौरा")) {
        return "⚠️ ऑफलाइन मोड: यदि मरीज सांस नहीं ले रहा है, तो तुरंत सीपीआर (CPR) शुरू करें — छाती के केंद्र को 100-120 प्रति मिनट की गति से जोर से दबाएं।"
      }
      if (lower.includes("खून") || lower.includes("चोट")) {
        return "⚠️ ऑफलाइन मोड: खून बहने वाली जगह पर साफ कपड़े से सीधा दबाव डालें और घायल हिस्से को ऊपर उठाएं।"
      }
      if (lower.includes("आग")) {
        return "⚠️ ऑफलाइन मोड: तुरंत सुरक्षित स्थान पर बाहर निकलें। धुएं के नीचे झुककर आगे बढ़ें।"
      }
      return "⚠️ ऑफलाइन मोड: शांत रहें। इंटरनेट कनेक्शन वापस आने पर आपका डेटा तुरंत सिंक हो जाएगा।"
    }

    // English Default
    if (lower.includes("breath") || lower.includes("unconscious") || lower.includes("cardiac") || lower.includes("collapse")) {
      return "⚠️ OFFLINE SAFETY GUIDANCE: If patient is unresponsive and not breathing, lay flat on a hard surface and begin continuous chest compressions at 100-120 bpm (CPR)."
    }
    if (lower.includes("bleed") || lower.includes("blood") || lower.includes("wound")) {
      return "⚠️ OFFLINE SAFETY GUIDANCE: Apply firm, continuous direct pressure to the wound with a clean cloth. Elevate the injured area above the heart."
    }
    if (lower.includes("fire") || lower.includes("smoke")) {
      return "⚠️ OFFLINE SAFETY GUIDANCE: Evacuate immediately. Stay low beneath the smoke line. Do not use elevators."
    }
    return "⚠️ OFFLINE SAFETY GUIDANCE: Limited connectivity. Keep caller safe. Incident telemetry queued for automatic sync when internet returns."
  }
}

export const offlineManager = new OfflineManager()
