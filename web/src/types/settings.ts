export interface SetupField {
  key: string
  label: string
  type: string
  value: unknown
  sensitive: boolean
  configured: boolean
  minimum: number | null
  maximum: number | null
  help: string
}
export interface SetupSettings {
  fields: SetupField[]
  apply_pending: boolean
  voice_restart_requested?: boolean
  voice_config_revision?: string
}
export interface DiagnosticCheck {
  id: string
  label: string
  status: 'success' | 'warning' | 'error'
  detail: string
  action: string
  group: string
  required: boolean
}
export interface DiagnosticReport {
  demo?: boolean
  ready: boolean
  checks: DiagnosticCheck[]
}
