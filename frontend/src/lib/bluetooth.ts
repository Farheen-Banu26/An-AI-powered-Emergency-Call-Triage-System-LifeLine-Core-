import type { SensorTelemetry } from "../types"

// Ambient Web Bluetooth API declarations
declare global {
  interface Navigator {
    bluetooth?: {
      requestDevice(options?: {
        acceptAllDevices?: boolean
        filters?: Array<{ services?: (string | number)[]; name?: string; namePrefix?: string }>
        optionalServices?: (string | number)[]
      }): Promise<any>
    }
  }
}

/**
 * Standard Bluetooth GATT Service & Characteristic UUIDs
 */
export const BLE_SERVICES = {
  HEART_RATE: 0x180d,
  BATTERY: 0x180f,
  PULSE_OXIMETER: 0x1822,
  HEALTH_THERMOMETER: 0x1809,
} as const

export const BLE_CHARACTERISTICS = {
  HEART_RATE_MEASUREMENT: 0x2a37,
  BATTERY_LEVEL: 0x2a19,
  PLX_CONTINUOUS_MEASUREMENT: 0x2a5f,
} as const

export interface BluetoothCallbacks {
  onConnected?: (deviceName: string) => void
  onDisconnected?: () => void
  onTelemetry?: (data: SensorTelemetry) => void
  onError?: (msg: string) => void
}

/**
 * Check if the current browser and platform support the Web Bluetooth API.
 */
export function isBluetoothSupported(): boolean {
  return typeof navigator !== "undefined" && Boolean(navigator.bluetooth?.requestDevice)
}

export class BluetoothManager {
  private device: any = null
  private server: any = null
  private isConnecting = false

  constructor(
    private callbacks: BluetoothCallbacks,
    private customServiceUuid?: string | number,
    private customCharUuid?: string | number,
  ) {}

  /**
   * Request Bluetooth device, connect to GATT server, discover services,
   * subscribe to notifications, and parse incoming sensor packets.
   */
  async connect(): Promise<boolean> {
    if (!isBluetoothSupported()) {
      this.callbacks.onError?.("Web Bluetooth is not supported in this browser environment. Use Chrome/Edge over HTTPS/localhost.")
      return false
    }

    if (this.isConnecting) return false
    this.isConnecting = true

    try {
      // Build optional services list
      const optionalServices: (string | number)[] = [
        BLE_SERVICES.HEART_RATE,
        BLE_SERVICES.BATTERY,
        BLE_SERVICES.PULSE_OXIMETER,
        BLE_SERVICES.HEALTH_THERMOMETER,
      ]
      if (this.customServiceUuid) {
        optionalServices.push(this.customServiceUuid)
      }

      // 1. Request Bluetooth Device (filters with acceptAllDevices fallback)
      if (!navigator.bluetooth) {
        throw new Error("Web Bluetooth is not available in this environment.")
      }

      this.device = await navigator.bluetooth.requestDevice({
        acceptAllDevices: true,
        optionalServices,
      })

      if (!this.device) {
        throw new Error("No device was selected.")
      }

      const deviceName = this.device.name || "Emergency Bluetooth Sensor"
      this.device.addEventListener("gattserverdisconnected", this.handleDisconnect)

      // 2. Connect to GATT Server
      if (!this.device.gatt) {
        throw new Error("Device does not support GATT connectivity.")
      }
      this.server = await this.device.gatt.connect()

      // 3. Discover and subscribe to available standard or custom characteristics
      await this.discoverAndSubscribeServices()

      this.callbacks.onConnected?.(deviceName)
      this.callbacks.onTelemetry?.({
        device_name: deviceName,
        status: "Connected",
        notes: "GATT connection established and listening for telemetry.",
        timestamp: new Date().toISOString(),
      })

      return true
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Bluetooth connection failed"
      if (!msg.includes("cancelled") && !msg.includes("User cancelled")) {
        this.callbacks.onError?.(msg)
      }
      this.cleanup()
      return false
    } finally {
      this.isConnecting = false
    }
  }

  private async discoverAndSubscribeServices() {
    if (!this.server) return

    // Attempt Heart Rate Service
    try {
      const hrService = await this.server.getPrimaryService(BLE_SERVICES.HEART_RATE)
      const hrChar = await hrService.getCharacteristic(BLE_CHARACTERISTICS.HEART_RATE_MEASUREMENT)
      await hrChar.startNotifications()
      hrChar.addEventListener("characteristicvaluechanged", (event: Event) => {
        const target = event.target as any
        if (!target?.value) return
        const hr = this.parseHeartRate(target.value)
        this.callbacks.onTelemetry?.({
          heart_rate: hr,
          device_name: this.device?.name || "Heart Rate Monitor",
          status: "Streaming",
          notes: hr > 100 ? "Elevated Heart Rate (Tachycardia)" : hr < 50 ? "Low Heart Rate (Bradycardia)" : "Normal Heart Rate",
          timestamp: new Date().toISOString(),
        })
      })
    } catch {
      // Service not offered by this peripheral; continue checking others
    }

    // Attempt Battery Service
    try {
      const batService = await this.server.getPrimaryService(BLE_SERVICES.BATTERY)
      const batChar = await batService.getCharacteristic(BLE_CHARACTERISTICS.BATTERY_LEVEL)
      const val = await batChar.readValue()
      const level = val.getUint8(0)
      this.callbacks.onTelemetry?.({
        device_name: this.device?.name || "BLE Device",
        status: "Connected",
        notes: `Battery level: ${level}%`,
        timestamp: new Date().toISOString(),
      })
    } catch {
      // Optional service
    }

    // Attempt Custom Configured Service if specified
    if (this.customServiceUuid && this.customCharUuid) {
      try {
        const customService = await this.server.getPrimaryService(this.customServiceUuid)
        const customChar = await customService.getCharacteristic(this.customCharUuid)
        await customChar.startNotifications()
        customChar.addEventListener("characteristicvaluechanged", (event: Event) => {
          const target = event.target as any
          if (!target?.value) return
          // Read first byte as telemetry value / status code
          const rawVal = target.value.getUint8(0)
          this.callbacks.onTelemetry?.({
            device_name: this.device?.name || "Custom Sensor",
            status: "Streaming",
            notes: `Telemetry raw payload: ${rawVal}`,
            timestamp: new Date().toISOString(),
          })
        })
      } catch {
        // Custom service not available
      }
    }
  }

  /**
   * Parse Bluetooth SIG Standard Heart Rate Measurement format (0x2A37).
   */
  private parseHeartRate(dataView: DataView): number {
    const flags = dataView.getUint8(0)
    const rate16Bits = (flags & 0x1) !== 0
    if (rate16Bits) {
      return dataView.getUint16(1, /* littleEndian */ true)
    }
    return dataView.getUint8(1)
  }

  private handleDisconnect = () => {
    this.cleanup()
    this.callbacks.onDisconnected?.()
  }

  disconnect() {
    if (this.device?.gatt?.connected) {
      this.device.gatt.disconnect()
    }
    this.cleanup()
  }

  private cleanup() {
    if (this.device) {
      this.device.removeEventListener("gattserverdisconnected", this.handleDisconnect)
    }
    this.device = null
    this.server = null
    this.isConnecting = false
  }
}
